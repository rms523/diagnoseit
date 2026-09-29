from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from dataclasses import dataclass
from datetime import date
from .models import Diagnosis, DiagnosisHistory, HealthTrend
from .serializers import (
    DiagnosisSerializer, DiagnosisListSerializer,
    DiagnosisHistorySerializer, HealthTrendSerializer
)
from utils.llm_service import (
    GENDER_LABELS, LLMError, LLMService, analyze_health_trends, calculate_age, generate_diagnosis,
    prepare_timeline_prompt,
)
from utils.report_redaction import Redactor
from .timeline import DEFAULT_PERIOD, PERIOD_DAYS, Timeline, build_timeline

MAX_SUMMARY_CHARS = 4000
MAX_CURRENT_SYMPTOMS = 20


@dataclass
class TimelineInputs:
    period: str
    summary: str
    symptoms: list


def _timeline_inputs(request):
    """The period, summary, and symptoms asked about now, or a 400 response explaining what is wrong."""
    period = str(request.data.get('period') or DEFAULT_PERIOD)
    if period not in PERIOD_DAYS:
        return None, Response(
            {'error': 'Choose a period: 3m, 6m, 1y, 2y, or all.'}, status=status.HTTP_400_BAD_REQUEST
        )
    summary = str(request.data.get('summary') or '').strip()
    if len(summary) > MAX_SUMMARY_CHARS:
        return None, Response(
            {'error': f'Keep the summary under {MAX_SUMMARY_CHARS} characters.'}, status=status.HTTP_400_BAD_REQUEST
        )
    raw = request.data.get('symptoms') or []
    items = raw if isinstance(raw, list) else [raw]
    texts = (str(item.get('description', '') if isinstance(item, dict) else item).strip() for item in items)
    return TimelineInputs(period, summary, [text for text in texts if text][:MAX_CURRENT_SYMPTOMS]), None


def _timeline_prompt(user, inputs: TimelineInputs) -> tuple[Timeline, str]:
    timeline = build_timeline(user, inputs.period)
    redactor = Redactor([user.first_name, user.last_name])
    prompt = prepare_timeline_prompt(
        age=calculate_age(user.date_of_birth) if getattr(user, 'date_of_birth', None) else None,
        gender=GENDER_LABELS.get(getattr(user, 'gender', None) or ''),
        summary='\n'.join(redactor.line(line) for line in inputs.summary.splitlines()),
        symptoms=[redactor.line(symptom) for symptom in inputs.symptoms],
        timeline_text=timeline.text,
    )
    return timeline, prompt


def _timeline_context(inputs: TimelineInputs, timeline: Timeline) -> dict:
    return {
        'mode': 'timeline',
        'period': inputs.period,
        'since': timeline.since.isoformat() if timeline.since else None,
        'until': timeline.until.isoformat(),
        'counts': timeline.counts,
        'omitted_dates': timeline.omitted_dates,
        'summary_included': bool(inputs.summary),
    }


def _confidence(value) -> int:
    try:
        return min(5, max(1, round(float(value))))
    except (TypeError, ValueError):
        return 3


class DiagnosisListCreateView(generics.ListCreateAPIView):
    """View for listing and creating diagnoses"""
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        return DiagnosisSerializer

    def get_queryset(self):
        return Diagnosis.objects.filter(user=self.request.user).prefetch_related('history')


class DiagnosisDetailView(generics.RetrieveUpdateDestroyAPIView):
    """View for retrieving, updating, and deleting diagnoses"""
    serializer_class = DiagnosisSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Diagnosis.objects.filter(user=self.request.user)


class HealthTrendListCreateView(generics.ListCreateAPIView):
    """View for listing and creating health trends"""
    serializer_class = HealthTrendSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return HealthTrend.objects.filter(user=self.request.user)


class HealthTrendDetailView(generics.RetrieveUpdateDestroyAPIView):
    """View for retrieving, updating, and deleting health trends"""
    serializer_class = HealthTrendSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return HealthTrend.objects.filter(user=self.request.user)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_diagnosis_view(request):
    """View for generating AI diagnosis based on symptoms and test results"""
    if request.data.get('mode') == 'timeline':
        return _generate_timeline_diagnosis(request)
    symptoms = request.data.get('symptoms', [])
    test_results = request.data.get('test_results', [])
    medications = request.data.get('medications', [])
    include_test_results = request.data.get('include_test_results', False)
    include_medical_history = request.data.get('include_medical_history', False)
    
    if not symptoms and not test_results:
        return Response(
            {'error': 'At least one symptom or test result is required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    from django_ratelimit.core import is_ratelimited

    if is_ratelimited(request, group='ai-diagnosis', key='user', rate='5/m', increment=True):
        return Response(
            {'error': 'Too many AI diagnosis requests. Please wait a minute and try again.'},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    
    # Gather test results from user's reports if requested
    if include_test_results and not test_results:
        from medical_reports.models import TestResult as MedicalTestResult
        recent_results = MedicalTestResult.objects.filter(
            report__user=request.user
        ).order_by('-report__report_date')[:20]
        test_results = [
            {
                'test_name': tr.test_name,
                'value': tr.value,
                'unit': tr.unit or '',
                'status': tr.status or '',
                'reference_range': tr.reference_range or '',
            }
            for tr in recent_results
        ]
    
    # Gather past symptom history if requested
    medical_history = []
    if include_medical_history:
        from symptoms.models import Symptom as SymptomModel
        past_symptoms = SymptomModel.objects.filter(
            user=request.user
        ).order_by('-onset_date')[:10]
        medical_history = [
            {
                'description': s.description,
                'severity': s.severity,
                'duration': s.duration,
                'onset_date': str(s.onset_date),
                'is_ongoing': s.is_ongoing,
            }
            for s in past_symptoms
        ]
    
    # Safely calculate age — date_of_birth may be null
    user_age = None
    if hasattr(request.user, 'date_of_birth') and request.user.date_of_birth:
        user_age = calculate_age(request.user.date_of_birth)
    
    user_gender = getattr(request.user, 'gender', None)
    
    # Prepare user data for LLM
    user_data = {
        'age': user_age,
        'gender': user_gender,
        'symptoms': symptoms,
        'test_results': test_results,
        'medications': medications,
        'medical_history': medical_history,
        '_redaction_names': [request.user.first_name, request.user.last_name],
    }
    
    # Generate diagnosis using LLM service
    llm_response = generate_diagnosis(user_data)
    
    # Create diagnosis object
    diagnosis_data = {
        'condition_name': llm_response.get('condition_name', 'Unknown Condition'),
        'description': llm_response.get('description', ''),
        'confidence_score': llm_response.get('confidence_score', 1),
        'symptoms_considered': symptoms,
        'test_results_considered': test_results,
        'recommendations': llm_response.get('recommendations', ''),
        'follow_up_required': llm_response.get('follow_up_required', False),
        'follow_up_notes': llm_response.get('follow_up_notes', '')
    }
    
    serializer = DiagnosisSerializer(data=diagnosis_data, context={'request': request})
    if serializer.is_valid():
        # analysis is read-only on the serializer, so the differential is stored after saving.
        diagnosis = serializer.save(analysis=llm_response.get('analysis') or {})
        
        # Create diagnosis history entry
        DiagnosisHistory.objects.create(
            diagnosis=diagnosis,
            condition_name=diagnosis.condition_name,
            description=diagnosis.description,
            confidence_score=diagnosis.confidence_score,
            recommendations=diagnosis.recommendations
        )
        
        return Response(DiagnosisSerializer(diagnosis).data, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


def _generate_timeline_diagnosis(request):
    """A diagnosis from the user's whole health timeline for a period, plus their own summary."""
    inputs, error = _timeline_inputs(request)
    if error:
        return error
    from django_ratelimit.core import is_ratelimited

    if is_ratelimited(request, group='ai-diagnosis', key='user', rate='5/m', increment=True):
        return Response(
            {'error': 'Too many AI diagnosis requests. Please wait a minute and try again.'},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    user = request.user
    # Kept even if the model fails, so the user does not lose what they wrote.
    if user.health_summary != inputs.summary:
        user.health_summary = inputs.summary
        user.save(update_fields=['health_summary'])

    timeline, prompt = _timeline_prompt(user, inputs)
    try:
        reply = LLMService().generate_timeline_diagnosis(prompt)
    except LLMError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    diagnosis = Diagnosis.objects.create(
        user=user,
        condition_name=str(reply.get('condition_name') or 'Unknown Condition')[:200],
        description=str(reply.get('description') or ''),
        confidence_score=_confidence(reply.get('confidence_score')),
        symptoms_considered=inputs.symptoms,
        test_results_considered=[],
        recommendations=str(reply.get('recommendations') or ''),
        follow_up_required=bool(reply.get('follow_up_required')),
        follow_up_notes=str(reply.get('follow_up_notes') or ''),
        # The differential, and the red flags the earlier code asked the model for and then threw away.
        analysis=reply.get('analysis') or {},
        context=_timeline_context(inputs, timeline),
    )
    DiagnosisHistory.objects.create(
        diagnosis=diagnosis,
        condition_name=diagnosis.condition_name,
        description=diagnosis.description,
        confidence_score=diagnosis.confidence_score,
        recommendations=diagnosis.recommendations,
    )
    return Response(DiagnosisSerializer(diagnosis).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def preview_timeline_diagnosis(request):
    """The prompt a health timeline diagnosis would send, so the user can read it before sending."""
    inputs, error = _timeline_inputs(request)
    if error:
        return error
    timeline, prompt = _timeline_prompt(request.user, inputs)
    context = _timeline_context(inputs, timeline)
    return Response({
        'prompt': prompt,
        'since': context['since'],
        'until': context['until'],
        'counts': context['counts'],
        'omitted_dates': context['omitted_dates'],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_diagnosis_history(request, diagnosis_id):
    """View for getting diagnosis history"""
    diagnosis = get_object_or_404(Diagnosis, id=diagnosis_id, user=request.user)
    history = DiagnosisHistory.objects.filter(diagnosis=diagnosis)
    serializer = DiagnosisHistorySerializer(history, many=True)
    return Response(serializer.data)
