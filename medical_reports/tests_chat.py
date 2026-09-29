"""Asking the AI about one report.

What reaches the model matters twice over: it must carry the report, and it must not carry the account
holder's name, phone number, or email.
"""

from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from ai_settings.services import AIConfig
from medical_reports.ai_chat import MAX_QUESTION_CHARS, MAX_STORED_MESSAGES, build_messages, report_context
from medical_reports.models import MedicalReport, TestResult

User = get_user_model()

CONFIGURED = AIConfig(
    role='diagnosis', source='database', enabled=True, provider='openai',
    base_url='http://model.invalid/v1', api_key='k', model='test-model',
    timeout_seconds=60, max_tokens=1000,
)
UNCONFIGURED = AIConfig(
    role='diagnosis', source='environment', enabled=False, provider='openai',
    base_url='', api_key='', model='', timeout_seconds=60, max_tokens=1000,
)


class ReportChatTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="asker", password="testpass123", first_name="Rahul", last_name="Mehta",
            email="rahul@example.com",
        )
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.user).key}")
        self.report = MedicalReport.objects.create(
            user=self.user, title="Lipid Panel", report_date=date(2026, 5, 1), lab_name="City Labs",
            file="medical_reports/lipids.pdf", status="COMPLETED",
        )
        TestResult.objects.create(
            report=self.report, test_name="LDL Cholesterol", value="164", unit="mg/dL",
            reference_range="0 - 100", status="HIGH",
        )
        self.url = f"/api/medical-reports/reports/{self.report.pk}/chat/"

    def test_the_report_reaches_the_model_and_the_patients_details_do_not(self):
        self.report.parsed_data = {
            'text': "Patient Name : Rahul Mehta\nPhone: +91 98765 43210\nrahul@example.com\n"
                    "LDL Cholesterol 164 mg/dL (0 - 100)\nComment: repeat after 3 months.",
        }
        self.report.save()

        context = report_context(self.report)

        self.assertIn("LDL Cholesterol", context)
        self.assertIn("164", context)
        self.assertIn("0 - 100", context)
        self.assertIn("repeat after 3 months", context)
        for personal in ("Rahul", "Mehta", "98765", "rahul@example.com"):
            self.assertNotIn(personal, context)

    def test_asking_stores_the_exchange_and_sends_the_report_with_the_question(self):
        question = 'I am Rahul; email rahul@example.com or call +1 212 555 0199. What does my LDL mean?'
        with patch('utils.ai_chat.get_ai_config', return_value=CONFIGURED), \
             patch('utils.ai_chat.chat_text', return_value='Your LDL is above its range.') as ask:
            response = self.client.post(self.url, {'question': question}, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            [(item['role'], item['content']) for item in response.data['messages']],
            [('user', question), ('assistant', 'Your LDL is above its range.')],
        )

        sent = ask.call_args.args[1]
        self.assertEqual(sent[0]['role'], 'system')
        self.assertIn('LDL Cholesterol', sent[1]['content'])
        self.assertEqual(sent[-1]['role'], 'user')
        for personal in ('Rahul', 'rahul@example.com', '212 555 0199'):
            self.assertNotIn(personal, sent[-1]['content'])

        # The conversation is on the report, so it is there on the next visit.
        self.assertEqual(len(self.client.get(self.url).data['messages']), 2)

    def test_a_follow_up_question_carries_the_earlier_turns(self):
        with patch('utils.ai_chat.get_ai_config', return_value=CONFIGURED), \
             patch('utils.ai_chat.chat_text', return_value='Answer one.'):
            self.client.post(self.url, {'question': 'First question?'}, format='json')

        with patch('utils.ai_chat.get_ai_config', return_value=CONFIGURED), \
             patch('utils.ai_chat.chat_text', return_value='Answer two.') as ask:
            self.client.post(self.url, {'question': 'And why is that?'}, format='json')

        sent = [(item['role'], item['content']) for item in ask.call_args.args[1]]
        self.assertIn(('user', 'First question?'), sent)
        self.assertIn(('assistant', 'Answer one.'), sent)
        self.assertEqual(sent[-1], ('user', 'And why is that?'))

    def test_a_model_failure_says_so_and_stores_nothing(self):
        with patch('utils.ai_chat.get_ai_config', return_value=CONFIGURED), \
             patch('utils.ai_chat.chat_text', side_effect=RuntimeError('boom')):
            response = self.client.post(self.url, {'question': 'What does my LDL mean?'}, format='json')

        self.assertEqual(response.status_code, 502)
        self.assertIn('did not respond', response.data['error'])
        self.report.refresh_from_db()
        self.assertEqual(self.report.ai_chat, {})

    def test_an_unconfigured_model_points_at_ai_settings_without_calling_out(self):
        with patch('utils.ai_chat.get_ai_config', return_value=UNCONFIGURED), \
             patch('utils.ai_chat.chat_text') as ask:
            response = self.client.post(self.url, {'question': 'What does my LDL mean?'}, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('AI settings', response.data['error'])
        ask.assert_not_called()

    def test_an_empty_or_overlong_question_is_refused(self):
        with patch('utils.ai_chat.get_ai_config', return_value=CONFIGURED), \
             patch('utils.ai_chat.chat_text') as ask:
            blank = self.client.post(self.url, {'question': '   '}, format='json')
            long = self.client.post(self.url, {'question': 'x' * (MAX_QUESTION_CHARS + 1)}, format='json')

        self.assertEqual(blank.status_code, 400)
        self.assertEqual(long.status_code, 400)
        ask.assert_not_called()

    def test_the_conversation_can_be_cleared_and_stays_within_its_limit(self):
        self.report.ai_chat = {'messages': [
            {'role': 'user' if index % 2 == 0 else 'assistant', 'content': f'line {index}'}
            for index in range(MAX_STORED_MESSAGES)
        ]}
        self.report.save()

        with patch('utils.ai_chat.get_ai_config', return_value=CONFIGURED), \
             patch('utils.ai_chat.chat_text', return_value='Newest answer.'):
            response = self.client.post(self.url, {'question': 'Newest question?'}, format='json')

        messages = response.data['messages']
        self.assertEqual(len(messages), MAX_STORED_MESSAGES)
        self.assertEqual(messages[-1]['content'], 'Newest answer.')
        self.assertNotIn('line 0', [item['content'] for item in messages])

        with patch('utils.ai_chat.get_ai_config', return_value=CONFIGURED):
            cleared = self.client.delete(self.url)
        self.assertEqual(cleared.data['messages'], [])

    def test_one_user_cannot_chat_about_anothers_report(self):
        other = User.objects.create_user(username="someone-else", password="testpass123")
        theirs = MedicalReport.objects.create(
            user=other, title="Theirs", report_date=date(2026, 5, 1),
            file="medical_reports/theirs.pdf", status="COMPLETED",
        )

        with patch('utils.ai_chat.get_ai_config', return_value=CONFIGURED), \
             patch('utils.ai_chat.chat_text') as ask:
            response = self.client.post(
                f"/api/medical-reports/reports/{theirs.pk}/chat/", {'question': 'What is this?'}, format='json'
            )

        self.assertEqual(response.status_code, 404)
        ask.assert_not_called()
        self.assertEqual(APIClient().get(f"/api/medical-reports/reports/{self.report.pk}/chat/").status_code, 401)

    def test_a_report_with_no_results_still_makes_a_prompt(self):
        self.report.test_results.all().delete()

        messages = build_messages(self.report, 'What is in this report?')

        self.assertIn('No results were read from this report.', messages[1]['content'])
