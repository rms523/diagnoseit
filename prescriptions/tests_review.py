"""Reviewing the medicines a prescription was read as.

The review suggests; the user decides. Nothing is applied on its own, every accepted change records what it
replaced so it can be undone, and a dismissed suggestion is not raised again.
"""

from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from ai_settings.models import AIServiceConfig
from ai_settings.services import AIConfig
from prescriptions.ai_review import COMPLETED, PENDING, review_status
from prescriptions.models import Prescription
from prescriptions.tasks import review_prescription_task
from utils.prescription_review import clean_suggestions

User = get_user_model()

CONFIGURED = AIConfig(
    role='report_review', source='database', enabled=True, provider='openai',
    base_url='http://model.invalid/v1', api_key='k', model='review-model',
    timeout_seconds=60, max_tokens=2000,
)


class PrescriptionReviewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="checker", password="testpass123")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.user).key}")
        self.prescription = Prescription.objects.create(
            user=self.user, prescription_date=date(2026, 9, 1), file='prescriptions/rx.jpg',
            status='COMPLETED', is_parsed=True,
            parsed_data={'text': 'Tab. Amoxicillin 500mg 1-0-1 x 5 days', 'text_source': 'photo'},
        )
        self.medication = self.prescription.medications.create(
            medication_name='Amoxicilin', dosage='50 mg', frequency='1-0-1',
        )
        self.base = f"/api/prescriptions/prescriptions/{self.prescription.pk}/ai-review/"
        AIServiceConfig.objects.create(
            role='report_review', base_url=CONFIGURED.base_url, api_key=CONFIGURED.api_key,
            model=CONFIGURED.model, timeout_seconds=CONFIGURED.timeout_seconds,
            max_tokens=CONFIGURED.max_tokens,
        )

    def _run(self, outcome):
        with patch('prescriptions.tasks.queue_review'):
            started = self.client.post(self.base)
        self.assertEqual(started.status_code, 202, started.data)
        run_id = self.prescription.__class__.objects.get(pk=self.prescription.pk).ai_review['run_id']
        with patch('prescriptions.tasks.get_ai_config', return_value=CONFIGURED, create=True), \
             patch('prescriptions.tasks.review_prescription', return_value=outcome), \
             patch('prescriptions.tasks.default_storage.open', side_effect=OSError('no file')):
            review_prescription_task(self.prescription.pk, run_id)
        self.prescription.refresh_from_db()

    def test_a_queued_review_runs_and_leaves_numbered_suggestions(self):
        self._run({
            'verdict': 'changes', 'input_mode': 'text_image', 'model': 'review-model',
            'suggestions': [
                {'action': 'update', 'medication_id': self.medication.pk,
                 'changes': {'medication_name': 'Amoxicillin', 'dosage': '500 mg'}, 'reason': 'misread'},
                {'action': 'add',
                 'medication': {'medication_name': 'Omeprazole', 'dosage': '20 mg', 'frequency': '',
                                'duration': '', 'instructions': ''},
                 'reason': 'on the prescription'},
            ],
        })

        review = self.prescription.ai_review
        self.assertEqual(review['status'], COMPLETED)
        self.assertEqual([item['id'] for item in review['suggestions']], [1, 2])
        # The run id is bookkeeping, not something the page needs.
        self.assertNotIn('run_id', self.client.get(
            f"/api/prescriptions/prescriptions/{self.prescription.pk}/"
        ).data['ai_review'])

    def test_nothing_is_applied_until_the_user_accepts(self):
        self._run({'verdict': 'changes', 'suggestions': [
            {'action': 'update', 'medication_id': self.medication.pk,
             'changes': {'dosage': '500 mg'}, 'reason': 'misread'},
        ]})

        self.medication.refresh_from_db()
        self.assertEqual(self.medication.dosage, '50 mg')

        response = self.client.post(f"{self.base}accept/", {'suggestion_ids': [1]}, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.medication.refresh_from_db()
        self.assertEqual(self.medication.dosage, '500 mg')

    def test_an_accepted_change_can_be_undone(self):
        self._run({'verdict': 'changes', 'suggestions': [
            {'action': 'update', 'medication_id': self.medication.pk,
             'changes': {'medication_name': 'Amoxicillin'}, 'reason': 'misread'},
        ]})
        self.client.post(f"{self.base}accept/", {'suggestion_ids': [1]}, format='json')
        self.prescription.refresh_from_db()
        applied_id = self.prescription.ai_review['applied'][0]['id']

        response = self.client.post(f"{self.base}applied/{applied_id}/undo/")

        self.assertEqual(response.status_code, 200, response.data)
        self.medication.refresh_from_db()
        self.assertEqual(self.medication.medication_name, 'Amoxicilin')

    def test_an_added_medicine_is_removed_again_by_undo_and_a_removed_one_comes_back(self):
        self._run({'verdict': 'changes', 'suggestions': [
            {'action': 'add', 'medication': {'medication_name': 'Omeprazole', 'dosage': '20 mg',
                                             'frequency': '', 'duration': '', 'instructions': ''},
             'reason': 'missing'},
            {'action': 'remove', 'medication_id': self.medication.pk, 'reason': 'a heading, not a medicine'},
        ]})

        self.client.post(f"{self.base}accept/", {'suggestion_ids': [1, 2]}, format='json')
        self.prescription.refresh_from_db()
        names = set(self.prescription.medications.values_list('medication_name', flat=True))
        self.assertEqual(names, {'Omeprazole'})

        for record in list(self.prescription.ai_review['applied']):
            self.client.post(f"{self.base}applied/{record['id']}/undo/")
        self.prescription.refresh_from_db()
        self.assertEqual(
            set(self.prescription.medications.values_list('medication_name', flat=True)), {'Amoxicilin'}
        )

    def test_a_dismissed_suggestion_is_not_raised_by_the_next_review(self):
        suggestion = {'action': 'update', 'medication_id': self.medication.pk,
                      'changes': {'dosage': '500 mg'}, 'reason': 'misread'}
        self._run({'verdict': 'changes', 'suggestions': [suggestion]})

        self.client.delete(f"{self.base}suggestions/1/")
        self.prescription.refresh_from_db()
        self.assertEqual(self.prescription.ai_review['suggestions'], [])

        self._run({'verdict': 'changes', 'suggestions': [suggestion]})

        self.assertEqual(self.prescription.ai_review['suggestions'], [])

    def test_a_review_that_fails_says_why_and_can_be_run_again(self):
        from utils.prescription_review import PrescriptionReviewError

        with patch('prescriptions.tasks.queue_review'):
            self.client.post(self.base)
        run_id = Prescription.objects.get(pk=self.prescription.pk).ai_review['run_id']
        with patch('prescriptions.tasks.get_ai_config', return_value=CONFIGURED, create=True), \
             patch('prescriptions.tasks.review_prescription',
                   side_effect=PrescriptionReviewError('Set up the report review model in AI settings.')), \
             patch('prescriptions.tasks.default_storage.open', side_effect=OSError('no file')):
            review_prescription_task(self.prescription.pk, run_id)

        self.prescription.refresh_from_db()
        self.assertEqual(self.prescription.ai_review['status'], 'failed')
        self.assertIn('AI settings', self.prescription.ai_review['error'])

        with patch('prescriptions.tasks.queue_review'):
            self.assertEqual(self.client.post(self.base).status_code, 202)

    def test_a_second_review_is_refused_while_one_is_running(self):
        with patch('prescriptions.tasks.queue_review'):
            self.client.post(self.base)
            again = self.client.post(self.base)

        self.assertEqual(again.status_code, 409)
        self.prescription.refresh_from_db()
        self.assertEqual(review_status(self.prescription), PENDING)

    def test_a_stopped_review_stores_nothing_when_it_finishes(self):
        with patch('prescriptions.tasks.queue_review'):
            self.client.post(self.base)
        run_id = Prescription.objects.get(pk=self.prescription.pk).ai_review['run_id']

        with patch('prescriptions.tasks.cancel_review_task'):
            self.client.post(f"{self.base}stop/")
        with patch('prescriptions.tasks.get_ai_config', return_value=CONFIGURED, create=True), \
             patch('prescriptions.tasks.review_prescription',
                   return_value={'verdict': 'changes', 'suggestions': [
                       {'action': 'remove', 'medication_id': self.medication.pk, 'reason': 'x'}]}), \
             patch('prescriptions.tasks.default_storage.open', side_effect=OSError('no file')):
            review_prescription_task(self.prescription.pk, run_id)

        self.prescription.refresh_from_db()
        self.assertNotIn('suggestions', self.prescription.ai_review)
        self.assertEqual(self.prescription.medications.count(), 1)

    def test_one_user_cannot_review_or_accept_on_anothers_prescription(self):
        other = User.objects.create_user(username="not-mine", password="testpass123")
        theirs = Prescription.objects.create(
            user=other, prescription_date=date(2026, 9, 1), file='prescriptions/theirs.pdf',
        )
        base = f"/api/prescriptions/prescriptions/{theirs.pk}/ai-review/"

        with patch('prescriptions.tasks.queue_review'):
            self.assertEqual(self.client.post(base).status_code, 404)
        self.assertEqual(
            self.client.post(f"{base}accept/", {'suggestion_ids': [1]}, format='json').status_code, 404
        )
        self.assertEqual(APIClient().post(base).status_code, 401)


class SuggestionCleaningTests(TestCase):
    """The model's answer is not trusted as it stands: it names rows that exist and changes that matter."""

    def setUp(self):
        self.stored = {
            7: {'medication_id': 7, 'medication_name': 'Amoxicillin', 'dosage': '500 mg',
                'frequency': '1-0-1', 'duration': '5 days', 'instructions': 'after food'},
        }

    def test_a_change_that_only_moves_punctuation_is_dropped(self):
        kept = clean_suggestions([
            {'action': 'update', 'medication_id': 7, 'changes': {'dosage': '500mg'}},
            {'action': 'update', 'medication_id': 7, 'changes': {'medication_name': 'AMOXICILLIN'}},
        ], self.stored)

        self.assertEqual(kept, [])

    def test_a_suggestion_about_a_row_that_does_not_exist_is_dropped(self):
        kept = clean_suggestions([{'action': 'remove', 'medication_id': 99, 'reason': 'x'}], self.stored)

        self.assertEqual(kept, [])

    def test_adding_a_medicine_already_stored_is_dropped(self):
        kept = clean_suggestions(
            [{'action': 'add', 'medication': {'medication_name': 'amoxicillin'}}], self.stored
        )

        self.assertEqual(kept, [])

    def test_a_real_correction_survives_and_keeps_only_the_fields_that_change(self):
        kept = clean_suggestions([
            {'action': 'update', 'medication_id': 7,
             'changes': {'dosage': '250 mg', 'frequency': '1-0-1'}, 'reason': 'printed as 250'},
        ], self.stored)

        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]['changes'], {'dosage': '250 mg'})


class ReviewImageOptionTests(TestCase):
    """The "Page images" choice decides whether the original page goes to the model with the text."""

    def setUp(self):
        self.user = User.objects.create_user(username="picker", password="testpass123")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.user).key}")
        AIServiceConfig.objects.create(
            role='report_review', base_url=CONFIGURED.base_url, api_key=CONFIGURED.api_key,
            model=CONFIGURED.model, timeout_seconds=CONFIGURED.timeout_seconds,
            max_tokens=CONFIGURED.max_tokens,
        )

    def _prescription(self, text_source):
        prescription = Prescription.objects.create(
            user=self.user, prescription_date=date(2026, 9, 1), file='prescriptions/rx.pdf',
            status='COMPLETED', is_parsed=True,
            parsed_data={'text': 'Tab. Amoxicillin 500mg', 'text_source': text_source},
        )
        prescription.medications.create(medication_name='Amoxicillin', dosage='500 mg')
        return prescription

    def _start(self, prescription, body=None):
        with patch('prescriptions.tasks.queue_review'):
            response = self.client.post(
                f"/api/prescriptions/prescriptions/{prescription.pk}/ai-review/", body or {}, format='json'
            )
        self.assertEqual(response.status_code, 202, response.data)
        prescription.refresh_from_db()
        return prescription.ai_review['options']['images']

    def test_a_photo_is_checked_against_its_image_by_default(self):
        # The text came from OCR, so comparing it with itself would confirm its own mistakes.
        self.assertIs(self._start(self._prescription('photo')), True)
        self.assertIs(self._start(self._prescription('ocr')), True)

    def test_a_pdf_whose_text_layer_was_read_does_not_send_the_image_by_default(self):
        self.assertIs(self._start(self._prescription('pdf')), False)

    def test_the_choice_overrides_the_default_both_ways(self):
        self.assertIs(self._start(self._prescription('pdf'), {'images': True}), True)
        self.assertIs(self._start(self._prescription('photo'), {'images': False}), False)

    def test_the_choice_reaches_the_model_call(self):
        prescription = self._prescription('pdf')
        self._start(prescription, {'images': True})
        run_id = prescription.__class__.objects.get(pk=prescription.pk).ai_review['run_id']

        with patch('prescriptions.tasks.get_ai_config', return_value=CONFIGURED, create=True), \
             patch('prescriptions.tasks.review_prescription',
                   return_value={'verdict': 'correct', 'suggestions': []}) as review, \
             patch('prescriptions.tasks.default_storage.open', side_effect=OSError('no file')):
            review_prescription_task(prescription.pk, run_id)

        self.assertIs(review.call_args.kwargs['images'], True)

    def test_the_image_is_only_built_when_it_was_asked_for(self):
        from utils.prescription_review import review_prescription

        prescription = self._prescription('photo')
        with patch('utils.prescription_review._page_image', return_value=b'png') as page_image, \
             patch('utils.prescription_review.chat_json', return_value='{"suggestions": []}'):
            without = review_prescription(prescription, CONFIGURED, b'file-bytes', images=False)
            page_image.assert_not_called()

            with_image = review_prescription(prescription, CONFIGURED, b'file-bytes', images=True)
            page_image.assert_called_once()

        self.assertEqual(without['input_mode'], 'text')
        self.assertEqual(with_image['input_mode'], 'text_image')
