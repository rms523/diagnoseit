"""The differential a diagnosis is built from, and what survives the model's answer.

The model's reply is not trusted as it stands: it is trimmed to the shape the app stores, and the fields
the rest of the app already relied on are filled from its leading candidate.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from ai_settings.services import AIConfig
from diagnosis.models import Diagnosis
from utils.llm_service import (
    DIAGNOSIS_REPLY_FORMAT,
    DIAGNOSIS_TASK,
    MAX_DIFFERENTIAL,
    normalize_diagnosis,
    LLMService,
    prepare_timeline_prompt,
)

User = get_user_model()

CONFIGURED = AIConfig(
    role='diagnosis', source='database', enabled=True, provider='openai',
    base_url='http://model.invalid/v1', api_key='k', model='test-model',
    timeout_seconds=60, max_tokens=1000,
)

FULL_REPLY = {
    'summary': 'Iron stores have fallen steadily since May.',
    'differential': [
        {'condition': 'Iron deficiency anaemia', 'likelihood': 'most likely', 'confidence': 4,
         'reasoning': 'Ferritin 8 ng/mL on 2026-05-01, below the 30-400 range.',
         'supporting': ['Ferritin 8'], 'against': ['MCV normal at 84'],
         'confirm_with': ['Repeat ferritin'], 'rule_out_with': ['Normal iron studies']},
        {'condition': 'Anaemia of chronic disease', 'likelihood': 'possible', 'confidence': 2,
         'reasoning': 'CRP mildly raised.', 'supporting': ['CRP 8'], 'against': ['Ferritin low, not high'],
         'confirm_with': [], 'rule_out_with': []},
    ],
    'false_positives': [
        {'condition': 'Anaemia of chronic disease',
         'why_it_might_be_wrong': 'One mildly raised CRP could be an unrelated infection.',
         'how_to_tell': 'Repeat CRP when well.'},
    ],
    'patterns': ['Haemoglobin and ferritin fell together across three reports.'],
    'cautions': ['A single ferritin is not enough to start treatment on.'],
    'red_flags': [],
    'recommendations': 'Repeat ferritin and a full blood count in 8 weeks.',
    'follow_up_required': True,
    'follow_up_notes': 'Discuss iron studies with your doctor.',
}


class DiagnosisPromptTests(TestCase):
    def test_the_prompt_asks_for_a_ranked_differential_and_its_own_false_positives(self):
        prompt = prepare_timeline_prompt(41, 'Male', 'Tired for months', ['fatigue'], 'TIMELINE')

        self.assertIn(DIAGNOSIS_TASK, prompt)
        self.assertIn(DIAGNOSIS_REPLY_FORMAT, prompt)
        for asked_for in ('differential', 'false_positives', 'patterns', 'cautions', 'red_flags',
                          'supporting', 'against', 'confirm_with', 'rule_out_with', 'reasoning'):
            self.assertIn(asked_for, prompt)
        # The data still has to reach the model.
        self.assertIn('TIMELINE', prompt)
        self.assertIn('Tired for months', prompt)
        self.assertIn('healthcare professional', prompt)

    def test_free_text_in_structured_diagnosis_input_is_redacted_recursively(self):
        with patch('utils.llm_service.get_ai_config', return_value=CONFIGURED):
            result = LLMService().anonymize_health_data({
                '_redaction_names': ['Rahul', 'Mehta'],
                'symptoms': [{'description': 'Rahul is tired; rahul@example.com; phone +1 212 555 0199'}],
                'medical_history': ['Call Mehta at +91 98765 43210'],
            })

        text = str(result)
        for personal in ('Rahul', 'Mehta', 'rahul@example.com', '212 555 0199', '98765 43210'):
            self.assertNotIn(personal, text)
        self.assertIn('[REDACTED]', text)


class NormalizeDiagnosisTests(TestCase):
    def test_the_leading_candidate_fills_the_fields_the_rest_of_the_app_reads(self):
        result = normalize_diagnosis(FULL_REPLY)

        self.assertEqual(result['condition_name'], 'Iron deficiency anaemia')
        self.assertEqual(result['description'], 'Iron stores have fallen steadily since May.')
        self.assertEqual(result['confidence_score'], 4)
        self.assertEqual(len(result['analysis']['differential']), 2)
        self.assertEqual(result['analysis']['red_flags'], [])
        self.assertEqual(result['analysis']['patterns'][0][:20], 'Haemoglobin and ferr')

    def test_the_differential_is_capped_and_junk_entries_are_dropped(self):
        reply = {'differential': [{'condition': f'Condition {n}'} for n in range(12)] + ['nonsense', {}, None]}

        differential = normalize_diagnosis(reply)['analysis']['differential']

        self.assertEqual(len(differential), MAX_DIFFERENTIAL)
        self.assertEqual(differential[0]['condition'], 'Condition 0')
        # An entry with no likelihood still gets a usable one.
        self.assertEqual(differential[0]['likelihood'], 'possible')

    def test_a_confidence_outside_the_scale_is_brought_back_onto_it(self):
        self.assertEqual(normalize_diagnosis({'confidence_score': 99})['confidence_score'], 5)
        self.assertEqual(normalize_diagnosis({'confidence_score': -4})['confidence_score'], 1)
        self.assertEqual(normalize_diagnosis({'confidence_score': 'high'})['confidence_score'], 3)

    def test_an_answer_with_no_differential_still_produces_a_diagnosis(self):
        result = normalize_diagnosis({'condition_name': 'Vitamin D deficiency', 'description': 'Low.'})

        self.assertEqual(result['condition_name'], 'Vitamin D deficiency')
        self.assertEqual(result['analysis']['differential'], [])


class TimelineDiagnosisStorageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="patient", password="testpass123")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.user).key}")

    def test_a_generated_diagnosis_keeps_its_differential_and_its_red_flags(self):
        reply = {**FULL_REPLY, 'red_flags': ['Haemoglobin below 8 would need urgent review']}
        with patch('utils.llm_service.get_ai_config', return_value=CONFIGURED), \
             patch('utils.llm_service.chat_json', return_value=__import__('json').dumps(reply)):
            response = self.client.post(
                '/api/diagnosis/diagnoses/generate/',
                {'mode': 'timeline', 'period': '1y', 'summary': 'Tired'},
                format='json',
            )

        self.assertEqual(response.status_code, 201, response.data)
        stored = Diagnosis.objects.get(pk=response.data['id'])
        self.assertEqual(stored.condition_name, 'Iron deficiency anaemia')
        self.assertEqual(
            [item['condition'] for item in stored.analysis['differential']],
            ['Iron deficiency anaemia', 'Anaemia of chronic disease'],
        )
        # Red flags were asked for by the old prompt and then thrown away; they are kept now.
        self.assertEqual(stored.analysis['red_flags'], ['Haemoglobin below 8 would need urgent review'])
        self.assertEqual(stored.analysis['false_positives'][0]['condition'], 'Anaemia of chronic disease')
        self.assertEqual(response.data['analysis']['cautions'], FULL_REPLY['cautions'])

    def test_a_differential_is_given_room_to_be_written(self):
        """The service default of 1000 tokens truncates a five-way differential into unparseable JSON."""
        from utils.llm_service import DIAGNOSIS_REPLY_TOKENS, LLMService

        with patch('utils.llm_service.get_ai_config', return_value=CONFIGURED), \
             patch('utils.llm_service.chat_json', return_value='{"differential": []}') as ask:
            LLMService().generate_timeline_diagnosis('prompt')

        self.assertEqual(ask.call_args.kwargs['max_tokens'], DIAGNOSIS_REPLY_TOKENS)
        self.assertGreater(DIAGNOSIS_REPLY_TOKENS, CONFIGURED.max_tokens)
