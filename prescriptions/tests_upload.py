"""Uploading a prescription and reading it in the background.

The upload must accept what people actually have — a clinic PDF or a photograph — return at once, and say
why when it cannot. Reading happens on the worker afterwards, so these tests drive the task directly.
"""

from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from ai_settings.services import AIConfig
from prescriptions.models import Prescription
from prescriptions.tasks import parse_prescription_task
from utils.prescription_parser import PrescriptionReadError, extract_medications

User = get_user_model()

CONFIGURED = AIConfig(
    role='report_review', source='database', enabled=True, provider='openai',
    base_url='http://model.invalid/v1', api_key='k', model='test-model',
    timeout_seconds=60, max_tokens=2000,
)
UNCONFIGURED = AIConfig(
    role='report_review', source='environment', enabled=False, provider='openai',
    base_url='', api_key='', model='', timeout_seconds=60, max_tokens=2000,
)

PRESCRIPTION_TEXT = """Dr A. Sharma, City Clinic
Tab. Amoxicillin 500mg 1-0-1 x 5 days after food
Cap. Omeprazole 20mg once daily before breakfast
Review after 1 week"""


class PrescriptionUploadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="patient", password="testpass123")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.user).key}")

    def _upload(self, upload, **fields):
        data = {'file': upload, 'prescription_date': '2026-09-01', **fields}
        # Queueing waits for the upload's transaction to commit, which a TestCase never does on its own.
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post('/api/prescriptions/prescriptions/', data, format='multipart')

    @staticmethod
    def _pdf(name='rx.pdf'):
        return SimpleUploadedFile(name, b'%PDF-1.4 fake', content_type='application/pdf')

    @staticmethod
    def _photo(name='rx.jpg'):
        return SimpleUploadedFile(name, b'\xff\xd8\xff\xe0 fake jpeg', content_type='image/jpeg')

    def test_an_upload_returns_at_once_and_is_read_in_the_background(self):
        with patch('prescriptions.tasks.parse_prescription_task.delay') as queued:
            response = self._upload(self._pdf(), doctor_name='Dr A. Sharma')

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['status'], 'PENDING')
        queued.assert_called_once_with(response.data['id'])

    def test_a_photograph_of_a_prescription_is_accepted(self):
        with patch('prescriptions.tasks.parse_prescription_task.delay'):
            response = self._upload(self._photo())

        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(Prescription.objects.get(pk=response.data['id']).file.name.endswith('.jpg'))

    def test_a_file_type_that_cannot_be_read_says_which_ones_can(self):
        response = self._upload(SimpleUploadedFile('notes.txt', b'hello', content_type='text/plain'))

        self.assertEqual(response.status_code, 400)
        self.assertIn('pdf', str(response.data['file']).lower())

    def test_an_extension_cannot_disguise_non_image_content(self):
        response = self._upload(SimpleUploadedFile('fake.jpg', b'not an image', content_type='image/jpeg'))

        self.assertEqual(response.status_code, 400)
        self.assertIn('content', str(response.data['file']).lower())

    def test_a_missing_date_is_refused_by_field_so_the_form_can_say_which(self):
        with patch('prescriptions.tasks.parse_prescription_task.delay'):
            response = self.client.post(
                '/api/prescriptions/prescriptions/', {'file': self._pdf()}, format='multipart'
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('prescription_date', response.data)

    def test_reading_stores_the_medicines_and_the_text(self):
        with patch('prescriptions.tasks.parse_prescription_task.delay'):
            prescription_id = self._upload(self._pdf()).data['id']

        read = {
            'text': PRESCRIPTION_TEXT,
            'text_source': 'pdf',
            'read_by': 'ai',
            'parsed_successfully': True,
            'medications': [
                {'medication_name': 'Amoxicillin', 'dosage': '500 mg', 'frequency': '1-0-1',
                 'duration': '5 days', 'instructions': 'after food'},
                {'medication_name': 'Omeprazole', 'dosage': '20 mg', 'frequency': 'once daily',
                 'duration': '', 'instructions': 'before breakfast'},
            ],
        }
        with patch('prescriptions.tasks.parse_prescription', return_value=read):
            parse_prescription_task(prescription_id)

        prescription = Prescription.objects.get(pk=prescription_id)
        self.assertEqual(prescription.status, 'COMPLETED')
        self.assertTrue(prescription.is_parsed)
        self.assertEqual(
            [(m.medication_name, m.dosage, m.frequency) for m in prescription.medications.all()],
            [('Amoxicillin', '500 mg', '1-0-1'), ('Omeprazole', '20 mg', 'once daily')],
        )
        self.assertEqual(prescription.parsed_data['text'], PRESCRIPTION_TEXT)

    def test_reading_twice_replaces_the_medicines_rather_than_doubling_them(self):
        with patch('prescriptions.tasks.parse_prescription_task.delay'):
            prescription_id = self._upload(self._pdf()).data['id']
        read = {'text': 't', 'text_source': 'pdf', 'read_by': 'ai', 'parsed_successfully': True,
                'medications': [{'medication_name': 'Amoxicillin', 'dosage': '', 'frequency': '',
                                 'duration': '', 'instructions': ''}]}

        with patch('prescriptions.tasks.parse_prescription', return_value=read):
            parse_prescription_task(prescription_id)
            parse_prescription_task(prescription_id)

        self.assertEqual(Prescription.objects.get(pk=prescription_id).medications.count(), 1)

    def test_a_prescription_that_cannot_be_read_keeps_the_reason(self):
        with patch('prescriptions.tasks.parse_prescription_task.delay'):
            prescription_id = self._upload(self._photo()).data['id']

        with patch(
            'prescriptions.tasks.parse_prescription',
            side_effect=PrescriptionReadError('Reading a photographed prescription needs the report OCR model.'),
        ):
            parse_prescription_task(prescription_id)

        prescription = Prescription.objects.get(pk=prescription_id)
        self.assertEqual(prescription.status, 'FAILED')
        self.assertIn('report OCR model', prescription.parse_error)

        status_response = self.client.get(f'/api/prescriptions/prescriptions/{prescription_id}/status/')
        self.assertEqual(status_response.data['status'], 'FAILED')
        self.assertIn('report OCR model', status_response.data['parse_error'])

    def test_a_failed_prescription_can_be_read_again(self):
        with patch('prescriptions.tasks.parse_prescription_task.delay'):
            prescription_id = self._upload(self._pdf()).data['id']
        Prescription.objects.filter(pk=prescription_id).update(status='FAILED', parse_error='no OCR')

        with patch('prescriptions.tasks.parse_prescription_task.delay') as queued, \
             self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f'/api/prescriptions/prescriptions/{prescription_id}/reparse/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'PENDING')
        queued.assert_called_once_with(prescription_id)

    def test_one_user_cannot_read_or_reparse_anothers_prescription(self):
        other = User.objects.create_user(username="someone-else", password="testpass123")
        theirs = Prescription.objects.create(
            user=other, prescription_date=date(2026, 9, 1), file='prescriptions/theirs.pdf'
        )

        self.assertEqual(
            self.client.get(f'/api/prescriptions/prescriptions/{theirs.pk}/status/').status_code, 404
        )
        self.assertEqual(
            self.client.post(f'/api/prescriptions/prescriptions/{theirs.pk}/reparse/').status_code, 404
        )
        self.assertEqual(
            APIClient().get(f'/api/prescriptions/prescriptions/{theirs.pk}/status/').status_code, 401
        )


class MedicationReadingTests(TestCase):
    def test_the_model_reads_the_medicines_and_its_answer_is_trimmed_to_the_fields_kept(self):
        reply = (
            '{"medications": [{"medication_name": "Amoxicillin", "dosage": "500 mg", "frequency": "1-0-1",'
            ' "duration": "5 days", "instructions": "after food", "ignored": "x"},'
            ' {"medication_name": "", "dosage": "10 mg"}]}'
        )
        with patch('utils.prescription_parser.get_ai_config', return_value=CONFIGURED), \
             patch('utils.prescription_parser.chat_json', return_value=reply):
            medications, read_by = extract_medications(PRESCRIPTION_TEXT)

        self.assertEqual(read_by, 'ai')
        # The nameless row is dropped, and no field the database does not hold survives.
        self.assertEqual(len(medications), 1)
        self.assertEqual(medications[0], {
            'medication_name': 'Amoxicillin', 'dosage': '500 mg', 'frequency': '1-0-1',
            'duration': '5 days', 'instructions': 'after food',
        })

    def test_without_a_model_the_older_pattern_matching_still_runs(self):
        with patch('utils.prescription_parser.get_ai_config', return_value=UNCONFIGURED), \
             patch('utils.prescription_parser.chat_json') as ask:
            medications, read_by = extract_medications(PRESCRIPTION_TEXT)

        ask.assert_not_called()
        self.assertEqual(read_by, 'patterns')
        self.assertIn('Amoxicillin', ' '.join(item['medication_name'] for item in medications))

    def test_a_model_failure_falls_back_instead_of_losing_the_upload(self):
        with patch('utils.prescription_parser.get_ai_config', return_value=CONFIGURED), \
             patch('utils.prescription_parser.chat_json', side_effect=RuntimeError('boom')):
            medications, read_by = extract_medications(PRESCRIPTION_TEXT)

        self.assertEqual(read_by, 'patterns')
        self.assertTrue(medications)


class PrescriptionChatTests(TestCase):
    """The chat must carry the prescription and not the account holder's details."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="reader", password="testpass123", first_name="Rahul", last_name="Mehta",
        )
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.user).key}")
        self.prescription = Prescription.objects.create(
            user=self.user, prescription_date=date(2026, 9, 1), hospital_clinic='City Clinic',
            file='prescriptions/rx.pdf', status='COMPLETED', is_parsed=True,
            parsed_data={'text': 'Patient : Rahul Mehta\nPhone 98765 43210\nTab. Amoxicillin 500mg after food'},
        )
        self.prescription.medications.create(
            medication_name='Amoxicillin', dosage='500 mg', frequency='1-0-1', duration='5 days',
            instructions='after food',
        )
        self.url = f"/api/prescriptions/prescriptions/{self.prescription.pk}/chat/"

    def test_the_prescription_reaches_the_model_and_the_patients_details_do_not(self):
        from prescriptions.ai_chat import prescription_context

        context = prescription_context(self.prescription)

        self.assertIn('Amoxicillin', context)
        self.assertIn('after food', context)
        for personal in ('Rahul', 'Mehta', '98765'):
            self.assertNotIn(personal, context)

    def test_asking_stores_the_exchange(self):
        chat_config = AIConfig(
            role='diagnosis', source='database', enabled=True, provider='openai',
            base_url='http://model.invalid/v1', api_key='k', model='test-model',
            timeout_seconds=60, max_tokens=1000,
        )
        with patch('utils.ai_chat.get_ai_config', return_value=chat_config), \
             patch('utils.ai_chat.chat_text', return_value='Amoxicillin is an antibiotic.') as ask:
            response = self.client.post(self.url, {'question': 'What is this medicine for?'}, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data['messages']), 2)
        self.assertIn('Amoxicillin', ask.call_args.args[1][1]['content'])
        self.prescription.refresh_from_db()
        self.assertEqual(len(self.prescription.ai_chat['messages']), 2)

    def test_one_user_cannot_chat_about_anothers_prescription(self):
        other = User.objects.create_user(username="not-me", password="testpass123")
        theirs = Prescription.objects.create(
            user=other, prescription_date=date(2026, 9, 1), file='prescriptions/theirs.pdf'
        )
        response = self.client.post(
            f"/api/prescriptions/prescriptions/{theirs.pk}/chat/", {'question': 'What is this?'}, format='json'
        )
        self.assertEqual(response.status_code, 404)


class OcrImageSizeTests(TestCase):
    """A phone photo costs a vision model by its area, so it is scaled down before it is sent."""

    @staticmethod
    def _photo(width, height):
        import io
        from PIL import Image
        buffer = io.BytesIO()
        Image.new('RGB', (width, height), 'white').save(buffer, format='JPEG')
        return buffer.getvalue()

    @staticmethod
    def _size(png_bytes):
        import io
        from PIL import Image
        with Image.open(io.BytesIO(png_bytes)) as image:
            return image.size

    def test_a_phone_photo_is_scaled_down_to_the_longest_edge_allowed(self):
        from utils.prescription_parser import MAX_IMAGE_EDGE, _png_bytes

        # A 12-megapixel photo held the wrong way up, as a phone takes it.
        width, height = self._size(_png_bytes(self._photo(3024, 4032)))

        self.assertEqual(max(width, height), MAX_IMAGE_EDGE)
        # Scaling keeps the shape of the page, or the text distorts.
        self.assertAlmostEqual(width / height, 3024 / 4032, places=2)

    def test_an_image_already_small_enough_is_left_alone(self):
        from utils.prescription_parser import _png_bytes

        self.assertEqual(self._size(_png_bytes(self._photo(1200, 900))), (1200, 900))

    def test_the_reply_is_bounded_so_a_repeating_model_cannot_run_on(self):
        from utils.prescription_parser import OCR_REPLY_TOKENS, read_text
        from ai_settings.services import AIConfig

        ocr = AIConfig(
            role='ocr', source='database', enabled=True, provider='openai',
            base_url='http://ocr.invalid/v1', api_key='', model='ocr-model',
            timeout_seconds=60, max_tokens=16000,
        )
        with patch('utils.vlm_pdf_parser._ocr_config', return_value=ocr), \
             patch('utils.vlm_pdf_parser.transcribe_page', return_value='Tab. Amoxicillin 500mg') as read:
            text, source = read_text(self._photo(2000, 1500), 'rx.jpg')

        self.assertEqual((text, source), ('Tab. Amoxicillin 500mg', 'photo'))
        # The OCR setting allows 16000 tokens; one prescription page is held to far less.
        self.assertEqual(read.call_args.kwargs['max_tokens'], OCR_REPLY_TOKENS)
        self.assertLess(OCR_REPLY_TOKENS, ocr.max_tokens)


class MedicationEditingTests(TestCase):
    """What OCR read is a start, not a record: every medicine can be corrected, added, or removed."""

    def setUp(self):
        self.user = User.objects.create_user(username="editor", password="testpass123")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.user).key}")
        self.prescription = Prescription.objects.create(
            user=self.user, prescription_date=date(2026, 9, 1), file='prescriptions/rx.pdf', status='COMPLETED',
        )
        self.medication = self.prescription.medications.create(
            medication_name='Amoxicilin', dosage='500mg', frequency='1-0-1',
        )
        self.url = f"/api/prescriptions/prescriptions/{self.prescription.pk}/medications/"

    def test_a_medicine_can_be_added_and_comes_back_with_its_id(self):
        response = self.client.post(self.url, {
            'medication_name': 'Omeprazole', 'dosage': '20 mg', 'frequency': 'once daily',
            'duration': '', 'instructions': 'before breakfast',
        }, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        # Without the id the page could not edit or remove the row it just added.
        self.assertIn('id', response.data)
        self.assertEqual(
            self.prescription.medications.get(pk=response.data['id']).instructions, 'before breakfast'
        )

    def test_a_name_the_model_misread_can_be_corrected(self):
        response = self.client.patch(
            f"{self.url}{self.medication.pk}/", {'medication_name': 'Amoxicillin'}, format='json'
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.medication.refresh_from_db()
        self.assertEqual(self.medication.medication_name, 'Amoxicillin')
        # Correcting one field leaves the rest as they were.
        self.assertEqual(self.medication.dosage, '500mg')

    def test_a_medicine_the_model_invented_can_be_removed(self):
        response = self.client.delete(f"{self.url}{self.medication.pk}/")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.prescription.medications.count(), 0)

    def test_a_medicine_needs_a_name(self):
        response = self.client.post(self.url, {'medication_name': '', 'dosage': '5 mg'}, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('medication_name', response.data)

    def test_one_user_cannot_touch_the_medicines_on_anothers_prescription(self):
        other = User.objects.create_user(username="not-mine", password="testpass123")
        theirs = Prescription.objects.create(
            user=other, prescription_date=date(2026, 9, 1), file='prescriptions/theirs.pdf',
        )
        their_medication = theirs.medications.create(medication_name='Metformin')
        their_url = f"/api/prescriptions/prescriptions/{theirs.pk}/medications/"

        self.assertEqual(self.client.get(their_url).status_code, 404)
        self.assertEqual(
            self.client.post(their_url, {'medication_name': 'Injected'}, format='json').status_code, 404
        )
        self.assertEqual(
            self.client.patch(f"{their_url}{their_medication.pk}/", {'dosage': '1 g'}, format='json').status_code,
            404,
        )
        self.assertEqual(self.client.delete(f"{their_url}{their_medication.pk}/").status_code, 404)
        their_medication.refresh_from_db()
        self.assertEqual((their_medication.medication_name, their_medication.dosage), ('Metformin', ''))
