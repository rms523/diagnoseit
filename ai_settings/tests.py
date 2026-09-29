"""AI settings: shared by the server and maintained by administrators, with write-only keys and runtime use."""

import json
from unittest.mock import MagicMock, patch

import httpx
import requests
from django.contrib.auth import get_user_model
from django.test import TestCase
from openai import BadRequestError
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from utils.llm_service import DIAGNOSIS_REPLY_TOKENS, LLMService
from utils.vlm_pdf_parser import _call_vlm, _use_vlm_parser, _vlm_extraction_mode
from .models import AIServiceConfig
from .services import ROLE_DIAGNOSIS, ROLE_OCR, ROLE_REPORT_REVIEW, get_ai_config

User = get_user_model()

ENVIRONMENT = {
    'OPENAI_API_KEY': 'env-cloud-key',
    'OPENAI_BASE_URL': '',
    'OPENAI_MODEL': 'gpt-4o-mini',
    'VLM_PROVIDER': 'openai',
    'VLM_API_BASE': 'http://ocr.local:8080/v1',
    'VLM_MODEL': 'PaddleOCR-VL-1.6 (Vision OCR)',
    'VLM_API_KEY': '',
    'VLM_MODE': 'auto',
    'USE_VLM_PARSER': 'true',
}


def _client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=user).key}")
    return client


def _json_response(payload):
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def _chat_completion(content):
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content=content))]
    return completion


@patch.dict('os.environ', ENVIRONMENT)
class AISettingsAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(username='staff', password='Staff-pass-123', is_staff=True)
        cls.member = User.objects.create_user(username='member', password='Member-pass-123')

    def setUp(self):
        self.staff_client = _client_for(self.staff)
        self.member_client = _client_for(self.member)

    def test_settings_require_sign_in(self):
        anonymous = APIClient()
        requests_to_check = [
            ('get', '/api/ai-settings/', {}),
            ('patch', '/api/ai-settings/diagnosis/', {'model': 'x'}),
            ('delete', '/api/ai-settings/diagnosis/', {}),
            ('post', '/api/ai-settings/diagnosis/test/', {}),
        ]
        for method, url, data in requests_to_check:
            with self.subTest(method=method, url=url):
                self.assertEqual(getattr(anonymous, method)(url, data, format='json').status_code, 401)
        self.assertFalse(AIServiceConfig.objects.exists())

    @patch('ai_settings.services.requests.get')
    def test_members_view_settings_and_administrators_change_test_and_reset_them(self, mock_get):
        mock_get.return_value = _json_response({'data': [{'id': 'qwen3-8b'}]})

        # A member could otherwise send everyone's reports to a server of their choosing, or have this
        # server request any URL.
        self.assertEqual(self.member_client.get('/api/ai-settings/').status_code, 200)
        self.assertEqual(
            self.member_client.patch('/api/ai-settings/diagnosis/', {'base_url': 'http://evil.example/v1'}, format='json').status_code,
            403,
        )
        self.assertEqual(
            self.member_client.post('/api/ai-settings/diagnosis/test/', {'base_url': 'http://db:5432'}, format='json').status_code,
            403,
        )
        self.assertEqual(self.member_client.delete('/api/ai-settings/diagnosis/').status_code, 403)
        self.assertFalse(AIServiceConfig.objects.exists())
        mock_get.assert_not_called()

        saved = self.staff_client.patch('/api/ai-settings/diagnosis/', {'model': 'qwen3-8b'}, format='json')
        self.assertEqual((saved.status_code, saved.data['source'], saved.data['updated_by']), (200, 'database', 'staff'))
        self.assertEqual(get_ai_config(ROLE_DIAGNOSIS).model, 'qwen3-8b')
        checked = self.staff_client.post('/api/ai-settings/diagnosis/test/', {}, format='json')
        self.assertEqual((checked.status_code, checked.data['ok']), (200, True))
        reset = self.staff_client.delete('/api/ai-settings/diagnosis/')
        self.assertEqual((reset.status_code, reset.data['source']), (200, 'environment'))
        self.assertFalse(AIServiceConfig.objects.exists())

    def test_unsaved_roles_use_environment_without_exposing_keys(self):
        response = self.staff_client.get('/api/ai-settings/')

        self.assertEqual(response.status_code, 200)
        services = {service['role']: service for service in response.data['services']}
        self.assertEqual(
            (services['diagnosis']['source'], services['diagnosis']['model'], services['diagnosis']['api_key_set']),
            ('environment', 'gpt-4o-mini', True),
        )
        self.assertEqual((services['report_review']['source'], services['report_review']['model']), ('diagnosis', 'gpt-4o-mini'))
        self.assertEqual(services['ocr']['base_url'], 'http://ocr.local:8080/v1')
        self.assertNotIn('env-cloud-key', response.content.decode())

    def test_saved_server_applies_immediately_and_key_is_write_only(self):
        response = self.staff_client.patch(
            '/api/ai-settings/diagnosis/',
            {'base_url': 'http://llm.local:8080/v1/', 'model': 'qwen3-8b', 'api_key': 'local-key'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.data['source'], response.data['base_url'], response.data['api_key_set']), ('database', 'http://llm.local:8080/v1', True))
        self.assertEqual(response.data['updated_by'], 'staff')
        self.assertNotIn('local-key', response.content.decode())
        config = get_ai_config(ROLE_DIAGNOSIS)
        self.assertEqual((config.base_url, config.model, config.api_key), ('http://llm.local:8080/v1', 'qwen3-8b', 'local-key'))
        # Report review follows AI diagnosis until it is configured on its own.
        self.assertEqual(get_ai_config(ROLE_REPORT_REVIEW).base_url, 'http://llm.local:8080/v1')

    def test_environment_key_is_never_sent_to_a_different_server(self):
        self.staff_client.patch('/api/ai-settings/diagnosis/', {'base_url': 'http://llm.local:8080/v1'}, format='json')

        self.assertEqual(get_ai_config(ROLE_DIAGNOSIS).api_key, '')

    def test_saved_key_is_dropped_when_the_server_changes(self):
        self.staff_client.patch(
            '/api/ai-settings/diagnosis/', {'base_url': 'http://llm.local:8080/v1', 'api_key': 'saved-key'}, format='json'
        )
        self.staff_client.patch('/api/ai-settings/diagnosis/', {'model': 'other-model'}, format='json')
        self.assertEqual(get_ai_config(ROLE_DIAGNOSIS).api_key, 'saved-key')

        moved = self.staff_client.patch(
            '/api/ai-settings/diagnosis/', {'base_url': 'http://collector.example/v1'}, format='json'
        )

        self.assertFalse(moved.data['api_key_set'])
        self.assertEqual(get_ai_config(ROLE_DIAGNOSIS).api_key, '')
        with_key = self.staff_client.patch(
            '/api/ai-settings/diagnosis/', {'base_url': 'http://llm2.local/v1', 'api_key': 'new-key'}, format='json'
        )
        self.assertTrue(with_key.data['api_key_set'])
        self.assertEqual(get_ai_config(ROLE_DIAGNOSIS).api_key, 'new-key')

    def test_clearing_key_and_resetting_to_environment(self):
        self.staff_client.patch('/api/ai-settings/diagnosis/', {'api_key': 'saved-key'}, format='json')
        self.assertEqual(get_ai_config(ROLE_DIAGNOSIS).api_key, 'saved-key')

        self.staff_client.patch('/api/ai-settings/diagnosis/', {'clear_api_key': True}, format='json')
        # Same server as the environment, so its key applies again.
        self.assertEqual(get_ai_config(ROLE_DIAGNOSIS).api_key, 'env-cloud-key')

        response = self.staff_client.delete('/api/ai-settings/diagnosis/')
        self.assertEqual((response.status_code, response.data['source']), (200, 'environment'))
        self.assertFalse(AIServiceConfig.objects.filter(role=ROLE_DIAGNOSIS).exists())

    def test_invalid_values_are_rejected(self):
        for role, data in [
            ('diagnosis', {'base_url': 'llm.local:8080'}),
            ('diagnosis', {'provider': 'ollama'}),
            ('ocr', {'timeout_seconds': 1}),
            ('ocr', {'ocr_mode': 'magic'}),
            ('report_review', {'temperature': 2.5}),
            ('ocr', {'parallel_requests': 0}),
            ('ocr', {'parallel_requests': 17}),
            ('report_review', {'temperature': -0.1}),
        ]:
            with self.subTest(role=role, data=data):
                self.assertEqual(self.staff_client.patch(f'/api/ai-settings/{role}/', data, format='json').status_code, 400)
        self.assertEqual(self.staff_client.patch('/api/ai-settings/unknown/', {}, format='json').status_code, 404)
        self.assertFalse(AIServiceConfig.objects.exists())

    def test_temperature_can_be_saved_and_cleared_to_use_the_default(self):
        saved = self.staff_client.patch('/api/ai-settings/report_review/', {'temperature': 0.25}, format='json')
        self.assertEqual((saved.status_code, saved.data['temperature'], saved.data['default_temperature']), (200, 0.25, 0.1))

        cleared = self.staff_client.patch('/api/ai-settings/report_review/', {'temperature': None}, format='json')
        self.assertEqual((cleared.status_code, cleared.data['temperature']), (200, None))

    def test_automatic_report_review_and_fixes_are_off_until_chosen_for_report_review(self):
        review = get_ai_config(ROLE_REPORT_REVIEW)
        self.assertEqual((review.auto_review, review.auto_apply), (False, False))
        # Report review inherits the diagnosis server, but not the choice to review reports or apply fixes.
        self.staff_client.patch('/api/ai-settings/diagnosis/', {'auto_review': True, 'auto_apply': True}, format='json')
        review = get_ai_config(ROLE_REPORT_REVIEW)
        self.assertEqual((review.auto_review, review.auto_apply), (False, False))

        response = self.staff_client.patch(
            '/api/ai-settings/report_review/', {'auto_review': True, 'auto_apply': True}, format='json'
        )

        self.assertEqual((response.status_code, response.data['auto_review'], response.data['auto_apply']), (200, True, True))
        review = get_ai_config(ROLE_REPORT_REVIEW)
        self.assertEqual((review.auto_review, review.auto_apply), (True, True))

    @patch('ai_settings.services.requests.get')
    def test_connection_check_lists_models_using_unsaved_values(self, mock_get):
        mock_get.return_value = _json_response({'data': [{'id': 'qwen3-8b'}, {'id': 'gemma-3'}]})

        response = self.staff_client.post(
            '/api/ai-settings/diagnosis/test/',
            {'base_url': 'http://llm.local:8080/v1', 'model': 'qwen3-8b', 'api_key': 'typed-key'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['ok'])
        self.assertEqual(response.data['models'], ['gemma-3', 'qwen3-8b'])
        self.assertNotIn('warning', response.data)
        mock_get.assert_called_once()
        self.assertEqual(mock_get.call_args.args[0], 'http://llm.local:8080/v1/models')
        self.assertEqual(mock_get.call_args.kwargs['headers'], {'Authorization': 'Bearer typed-key'})
        self.assertFalse(AIServiceConfig.objects.exists())

    @patch('ai_settings.services.requests.get')
    def test_connection_check_never_sends_saved_key_to_a_new_host(self, mock_get):
        mock_get.return_value = _json_response({'data': []})

        self.staff_client.post('/api/ai-settings/diagnosis/test/', {'base_url': 'http://other.local/v1'}, format='json')

        self.assertEqual(mock_get.call_args.kwargs['headers'], {})

    @patch('ai_settings.services.requests.get', side_effect=requests.ConnectionError('refused'))
    def test_connection_check_reports_unreachable_server(self, _get):
        response = self.staff_client.post('/api/ai-settings/ocr/test/', {}, format='json')

        self.assertFalse(response.data['ok'])
        self.assertIn('Could not reach http://ocr.local:8080/v1/models', response.data['error'])

    def test_status_endpoint_is_available_to_members(self):
        response = self.member_client.get('/api/ai-settings/status/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['report_review'], {'available': True, 'model': 'gpt-4o-mini', 'auto_review': False})
        self.assertNotIn('base_url', json.dumps(response.data))

    def test_profile_exposes_is_staff_read_only(self):
        self.member_client.patch('/api/auth/profile/', {'is_staff': True}, format='json')

        self.member.refresh_from_db()
        self.assertFalse(self.member.is_staff)
        self.assertTrue(self.staff_client.get('/api/auth/profile/').data['is_staff'])


@patch.dict('os.environ', ENVIRONMENT)
class AISettingsRuntimeTests(TestCase):
    @patch('ai_settings.client.OpenAI')
    def test_diagnosis_uses_saved_local_server(self, mock_openai):
        AIServiceConfig.objects.create(
            role=ROLE_DIAGNOSIS, base_url='http://llm.local:8080/v1', model='qwen3-8b', max_tokens=900, timeout_seconds=900,
        )
        create = mock_openai.return_value.chat.completions.create
        create.return_value = _chat_completion('```json\n{"condition_name": "Anaemia", "confidence_score": 3}\n```')

        result = LLMService().generate_diagnosis({'symptoms': [{'description': 'Fatigue'}]})

        self.assertEqual(result['condition_name'], 'Anaemia')
        self.assertEqual(mock_openai.call_args.kwargs['base_url'], 'http://llm.local:8080/v1')
        self.assertEqual(mock_openai.call_args.kwargs['api_key'], 'not-needed')
        # Web-request calls stay under the 300 s proxy limit and never retry.
        self.assertEqual((mock_openai.call_args.kwargs['timeout'], mock_openai.call_args.kwargs['max_retries']), (270, 0))
        # The saved model is used, but a differential needs room: a saved limit below the floor is raised,
        # since a reply cut off mid-object is not parseable at all (utils.llm_service.DIAGNOSIS_REPLY_TOKENS).
        self.assertEqual(create.call_args.kwargs['model'], 'qwen3-8b')
        self.assertEqual(create.call_args.kwargs['max_tokens'], DIAGNOSIS_REPLY_TOKENS)

    @patch('ai_settings.client.OpenAI')
    def test_saved_temperature_is_used_and_blank_uses_the_services_default(self, mock_openai):
        AIServiceConfig.objects.create(
            role=ROLE_DIAGNOSIS, base_url='http://llm.local:8080/v1', model='qwen3-8b', temperature=0.8,
        )
        create = mock_openai.return_value.chat.completions.create
        create.return_value = _chat_completion('{"condition_name": "Cold"}')

        LLMService().generate_diagnosis({'symptoms': [{'description': 'Cough'}]})
        self.assertEqual(create.call_args.kwargs['temperature'], 0.8)
        # Report review does not inherit the diagnosis temperature while it uses the diagnosis connection.
        self.assertIsNone(get_ai_config(ROLE_REPORT_REVIEW).temperature)

        AIServiceConfig.objects.filter(role=ROLE_DIAGNOSIS).update(temperature=None)
        LLMService().generate_diagnosis({'symptoms': [{'description': 'Cough'}]})
        self.assertEqual(create.call_args.kwargs['temperature'], 0.3)

    @patch('ai_settings.client.OpenAI')
    def test_diagnosis_retries_when_server_rejects_json_mode(self, mock_openai):
        AIServiceConfig.objects.create(role=ROLE_DIAGNOSIS, base_url='http://llm.local:8080/v1', model='qwen3-8b')
        rejected = BadRequestError(
            'response_format not supported',
            response=httpx.Response(400, request=httpx.Request('POST', 'http://llm.local:8080/v1/chat/completions')),
            body=None,
        )
        create = mock_openai.return_value.chat.completions.create
        create.side_effect = [rejected, _chat_completion('{"condition_name": "Cold"}')]

        result = LLMService().generate_diagnosis({'symptoms': [{'description': 'Cough'}]})

        self.assertEqual(result['condition_name'], 'Cold')
        self.assertEqual(create.call_count, 2)
        self.assertNotIn('response_format', create.call_args_list[1].kwargs)

    def test_unconfigured_diagnosis_returns_placeholder(self):
        AIServiceConfig.objects.create(role=ROLE_DIAGNOSIS, enabled=False, model='qwen3-8b', base_url='http://llm.local/v1')

        result = LLMService().generate_diagnosis({'symptoms': [{'description': 'Cough'}]})

        self.assertEqual(result['condition_name'], 'LLM Service Not Configured')

    @patch('utils.vlm_pdf_parser.requests.post')
    def test_ocr_parser_uses_saved_server_without_restart(self, mock_post):
        AIServiceConfig.objects.create(
            role=ROLE_OCR, provider='openai', base_url='http://new-ocr:9000/v1', model='MyVision',
            api_key='ocr-key', ocr_mode='json_vlm', timeout_seconds=90,
        )
        mock_post.return_value = _json_response({'choices': [{'message': {'content': '[]'}}]})

        self.assertEqual(_vlm_extraction_mode(), 'json_vlm')
        _call_vlm(b'png-bytes')

        self.assertEqual(mock_post.call_args.args[0], 'http://new-ocr:9000/v1/chat/completions')
        self.assertEqual(mock_post.call_args.kwargs['json']['model'], 'MyVision')
        self.assertEqual(mock_post.call_args.kwargs['headers'], {'Authorization': 'Bearer ocr-key'})
        self.assertEqual(mock_post.call_args.kwargs['timeout'][1], 90)

    def test_ocr_can_be_disabled_in_settings_and_by_environment_kill_switch(self):
        self.assertTrue(_use_vlm_parser())

        with patch.dict('os.environ', {'USE_VLM_PARSER': 'false'}):
            self.assertFalse(_use_vlm_parser())

        AIServiceConfig.objects.create(role=ROLE_OCR, enabled=False, base_url='http://ocr.local:8080/v1', model='x')
        self.assertFalse(_use_vlm_parser())
