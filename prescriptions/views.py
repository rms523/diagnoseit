import mimetypes

from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from django.http import FileResponse
from .models import Prescription, Medication
from .serializers import (
    PrescriptionSerializer, PrescriptionListSerializer,
    MedicationSerializer, MedicationCreateSerializer
)
from utils.private_files import private_file_token_is_valid
from . import ai_review as review_state
from .tasks import cancel_review_task, queue_parse, queue_review


@api_view(['GET'])
@permission_classes([AllowAny])
def download_prescription_file(request, prescription_id):
    """Stream a prescription to its owner or via a short-lived signed URL."""
    prescription = get_object_or_404(Prescription, id=prescription_id)
    is_owner = (
        request.user.is_authenticated
        and prescription.user_id == request.user.id
    )
    has_valid_token = private_file_token_is_valid(
        request.query_params.get('token', ''),
        prescription.id,
        prescription.file.name,
    )
    if not is_owner and not has_valid_token:
        return Response(status=status.HTTP_404_NOT_FOUND)
    name = prescription.file.name.rsplit('/', 1)[-1]
    # A prescription may be a photograph, so the type follows the file rather than always being a PDF.
    content_type = mimetypes.guess_type(name)[0] or 'application/octet-stream'
    return FileResponse(
        prescription.file.open('rb'),
        content_type=content_type,
        as_attachment=False,
        filename=name,
    )


class PrescriptionListCreateView(generics.ListCreateAPIView):
    """View for listing and creating prescriptions"""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_serializer_class(self):
        return PrescriptionSerializer

    def get_queryset(self):
        return Prescription.objects.filter(user=self.request.user).prefetch_related(
            'medications'
        )

    def perform_create(self, serializer):
        """Store the upload and read it in the background, as a medical report is read."""
        prescription = serializer.save()
        if prescription.file:
            queue_parse(prescription)
        else:
            prescription.status = 'COMPLETED'
            prescription.save(update_fields=['status', 'updated_at'])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def prescription_status(request, prescription_id):
    """Check the background reading of a prescription, polled by the prescriptions page."""
    prescription = get_object_or_404(Prescription, id=prescription_id, user=request.user)
    return Response({
        'id': prescription.id,
        'status': prescription.status,
        'is_parsed': prescription.is_parsed,
        'parse_error': prescription.parse_error,
        'medication_count': prescription.medications.count(),
        'ai_review_status': review_state.review_status(prescription),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reparse_prescription(request, prescription_id):
    """Read the prescription again, after the OCR or review model has been set up or changed."""
    prescription = get_object_or_404(Prescription, id=prescription_id, user=request.user)
    if not prescription.file:
        return Response({'error': 'This prescription has no file to read.'}, status=status.HTTP_400_BAD_REQUEST)
    if prescription.status in ('PENDING', 'PROCESSING'):
        return Response({'error': 'This prescription is already being read.'}, status=status.HTTP_409_CONFLICT)
    prescription.status = 'PENDING'
    prescription.parse_error = ''
    prescription.save(update_fields=['status', 'parse_error', 'updated_at'])
    queue_parse(prescription)
    return Response({'id': prescription.id, 'status': prescription.status})


def _review_payload(prescription):
    return {
        'id': prescription.id,
        'ai_review': review_state.visible_review(prescription),
        'medications': MedicationSerializer(prescription.medications.all(), many=True).data,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def review_prescription_with_ai(request, prescription_id):
    """Queue an AI review of this prescription's medicines against the prescription itself."""
    from django_ratelimit.core import is_ratelimited

    from ai_settings.services import ROLE_REPORT_REVIEW, get_ai_config

    prescription = get_object_or_404(Prescription, id=prescription_id, user=request.user)
    if review_state.review_status(prescription) == review_state.PENDING:
        return Response({'error': 'A review of this prescription is already running.'},
                        status=status.HTTP_409_CONFLICT)
    if not get_ai_config(ROLE_REPORT_REVIEW).is_configured:
        return Response(
            {'error': 'AI review is not configured. Set it up in AI settings.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if is_ratelimited(request, group='prescription-ai-review', key='user', rate='30/m', increment=True):
        return Response(
            {'error': 'Too many AI review requests. Please wait a minute and try again.'},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    images = request.data.get('images')
    options = {'images': images} if isinstance(images, bool) else None
    run_id = review_state.start_review(prescription, options)
    queue_review(prescription.id, run_id)
    return Response(_review_payload(prescription), status=status.HTTP_202_ACCEPTED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def stop_prescription_review(request, prescription_id):
    """Discard a queued or running review so nothing from it is stored."""
    prescription = get_object_or_404(Prescription, id=prescription_id, user=request.user)
    run_id = review_state.stop_review(prescription)
    if run_id:
        cancel_review_task(run_id)
    return Response(_review_payload(prescription))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def accept_prescription_suggestions(request, prescription_id):
    """Apply the chosen suggestions to the medicines; each records what it replaced, so it can be undone."""
    prescription = get_object_or_404(Prescription, id=prescription_id, user=request.user)
    raw = request.data.get('suggestion_ids')
    try:
        suggestion_ids = [int(value) for value in raw] if isinstance(raw, list) else []
    except (TypeError, ValueError):
        return Response({'error': 'suggestion_ids must be numbers.'}, status=status.HTTP_400_BAD_REQUEST)
    if not suggestion_ids:
        return Response({'error': 'Choose at least one suggestion.'}, status=status.HTTP_400_BAD_REQUEST)
    accepted = review_state.accept_suggestions(prescription, suggestion_ids)
    return Response({**_review_payload(prescription), 'accepted': accepted})


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def dismiss_prescription_suggestion(request, prescription_id, suggestion_id):
    """Drop a suggestion and remember it, so a later review does not raise the same one."""
    prescription = get_object_or_404(Prescription, id=prescription_id, user=request.user)
    review_state.dismiss_suggestion(prescription, suggestion_id)
    return Response(_review_payload(prescription))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def undo_prescription_change(request, prescription_id, applied_id):
    """Put back what an accepted suggestion changed."""
    prescription = get_object_or_404(Prescription, id=prescription_id, user=request.user)
    review_state.undo_applied(prescription, applied_id)
    return Response(_review_payload(prescription))


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def close_prescription_review(request, prescription_id):
    """Close the review panel, keeping which suggestions were dismissed."""
    prescription = get_object_or_404(Prescription, id=prescription_id, user=request.user)
    review_state.clear_review(prescription)
    return Response(_review_payload(prescription))


class PrescriptionDetailView(generics.RetrieveUpdateDestroyAPIView):
    """View for retrieving, updating, and deleting prescriptions"""
    serializer_class = PrescriptionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Prescription.objects.filter(user=self.request.user)


class MedicationListCreateView(generics.ListCreateAPIView):
    """View for listing and creating medications for a specific prescription"""
    serializer_class = MedicationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        prescription_id = self.kwargs['prescription_id']
        prescription = get_object_or_404(Prescription, id=prescription_id, user=self.request.user)
        return Medication.objects.filter(prescription=prescription)

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return MedicationSerializer
        return MedicationCreateSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.request.method == 'POST':
            prescription_id = self.kwargs['prescription_id']
            context['prescription'] = get_object_or_404(Prescription, id=prescription_id, user=self.request.user)
        return context


class MedicationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """View for retrieving, updating, and deleting medications"""
    serializer_class = MedicationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        prescription_id = self.kwargs['prescription_id']
        prescription = get_object_or_404(Prescription, id=prescription_id, user=self.request.user)
        return Medication.objects.filter(prescription=prescription)
