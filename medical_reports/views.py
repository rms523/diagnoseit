import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .ai_review import (
    clear_review,
    PENDING, ReviewConflict, apply_suggestions, dismiss_suggestion, review_status, start_review, stop_review,
    undo_applied, visible_review,
)
from .models import MedicalReport, TestResult
from .serializers import (
    MedicalReportSerializer, MedicalReportListSerializer,
    TestResultSerializer, TestResultCreateSerializer
)
from .tasks import cancel_review_task, normalize_test_status, parse_report_task, queue_review
from lab_tests.models import LabTestType
from lab_tests.matching import alias_key, is_measurement
from lab_tests.services import normalize_test_identifier, resolve_test_type
from lab_tests.trend_units import UNCONVERTED, trend_points
from utils.private_files import private_file_token_is_valid
from utils.upload_validation import validate_medical_upload

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([AllowAny])
def download_report_file(request, report_id):
    """Stream a report to its owner or to a valid short-lived signed URL."""
    report = get_object_or_404(MedicalReport, id=report_id)
    is_owner = request.user.is_authenticated and report.user_id == request.user.id
    has_valid_token = private_file_token_is_valid(
        request.query_params.get('token', ''), report.id, report.file.name
    )
    if not is_owner and not has_valid_token:
        return Response(status=status.HTTP_404_NOT_FOUND)
    return FileResponse(
        report.file.open('rb'),
        content_type='application/pdf',
        as_attachment=False,
        filename=report.file.name.rsplit('/', 1)[-1],
    )


def _queue_pdf_parse(report: MedicalReport, review: bool | None = None) -> None:
    """Enqueue PDF parsing after the DB transaction commits.

    review is the upload's choice to review the parsed results with AI; None follows AI settings.
    """
    report_id = report.id

    def dispatch() -> None:
        try:
            parse_report_task.delay(report_id, review=review)
        except Exception as exc:
            logger.exception("Could not enqueue report %s for parsing", report_id)
            report.status = "FAILED"
            report.parse_error = f"Could not queue report for parsing: {str(exc)[:900]}"
            report.save(update_fields=["status", "parse_error"])

    transaction.on_commit(dispatch)


def _review_choice(request) -> bool | None:
    """The upload form's "review with AI after parsing" choice, or None when it sent none."""
    value = str(request.data.get('ai_review', '')).strip().lower()
    if value in ('1', 'true', 'yes', 'on'):
        return True
    if value in ('0', 'false', 'no', 'off'):
        return False
    return None


class MedicalReportListCreateView(generics.ListCreateAPIView):
    """View for listing and creating medical reports"""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return MedicalReportListSerializer
        return MedicalReportSerializer

    def get_queryset(self):
        return MedicalReport.objects.filter(user=self.request.user).prefetch_related(
            'test_results__test_type'
        )

    def perform_create(self, serializer):
        """Save report and queue async parsing for PDFs."""
        report = serializer.save()

        if report.file and report.file.name.lower().endswith('.pdf'):
            _queue_pdf_parse(report, review=_review_choice(self.request))
        else:
            # Non-PDF uploads have nothing to parse asynchronously
            report.status = 'COMPLETED'
            report.save(update_fields=['status'])


class MedicalReportDetailView(generics.RetrieveUpdateDestroyAPIView):
    """View for retrieving, updating, and deleting medical reports"""
    serializer_class = MedicalReportSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return MedicalReport.objects.filter(user=self.request.user)


class TestResultListCreateView(generics.ListCreateAPIView):
    """View for listing and creating test results for a specific report"""
    serializer_class = TestResultSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        report_id = self.kwargs['report_id']
        report = get_object_or_404(MedicalReport, id=report_id, user=self.request.user)
        return TestResult.objects.filter(report=report)

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return TestResultSerializer
        return TestResultCreateSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.request.method == 'POST':
            report_id = self.kwargs['report_id']
            context['report'] = get_object_or_404(MedicalReport, id=report_id, user=self.request.user)
        return context

    def create(self, request, *args, **kwargs):
        # Respond with the full row (id, catalog name) so clients can show and edit it immediately.
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(TestResultSerializer(result).data, status=status.HTTP_201_CREATED)


class TestResultDetailView(generics.RetrieveUpdateDestroyAPIView):
    """View for retrieving, updating, and deleting test results"""
    serializer_class = TestResultSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        report_id = self.kwargs['report_id']
        report = get_object_or_404(MedicalReport, id=report_id, user=self.request.user)
        return TestResult.objects.filter(report=report)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_status(request, report_id):
    """Check the async parsing status of a medical report."""
    report = get_object_or_404(MedicalReport, id=report_id, user=request.user)
    return Response({
        'id': report.id,
        'status': report.status,
        'is_parsed': report.is_parsed,
        'parse_error': report.parse_error,
        'ai_review_status': review_status(report),
    })


@api_view(['POST', 'DELETE'])
@permission_classes([IsAuthenticated])
def ai_review_report(request, report_id):
    """POST queues a review of the report's results in the background; DELETE clears the stored review."""
    from django_ratelimit.core import is_ratelimited

    from ai_settings.services import ROLE_OCR, ROLE_REPORT_REVIEW, get_ai_config

    report = get_object_or_404(MedicalReport, id=report_id, user=request.user)
    if request.method == 'DELETE':
        clear_review(report)
        return Response(status=status.HTTP_204_NO_CONTENT)

    # Per-review choices: read the pages with the OCR model, and send page images, whatever the setting says.
    options = {name: request.data.get(name) in (True, 'true', '1', 1) for name in ('ocr', 'images')}

    config = get_ai_config(ROLE_REPORT_REVIEW)
    if not config.is_configured:
        return Response(
            {'error': 'AI review is not configured. Set it up in AI settings.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if options['ocr'] and not get_ai_config(ROLE_OCR).is_configured:
        return Response(
            {'error': 'Report OCR is not set up. Set it up in AI settings, or review without OCR.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if review_status(report) == PENDING:
        return Response(
            {'error': 'An AI review is already running for this report. Its suggestions appear when it finishes.'},
            status=status.HTTP_409_CONFLICT,
        )
    if is_ratelimited(request, group='report-ai-review', key='user', rate='10/m', increment=True):
        return Response(
            {'error': 'Too many AI review requests. Please wait a minute and try again.'},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    # Reviewed by the Celery worker like automatic reviews, so a long report cannot hit the web request timeout.
    queue_review(report.id, start_review(report, options if any(options.values()) else None))
    return Response(visible_review(report), status=status.HTTP_202_ACCEPTED)


MAX_BULK_REVIEW_REPORTS = 50

# Bound both multipart parsing work and the number of background jobs a single request can create.
MAX_BULK_UPLOAD_REPORTS = 50


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_ai_review_reports(request):
    """Queue AI reviews for several parsed reports, in the order given.

    Reviews run on the ai_review queue, whose worker takes one task at a time, so the reports are reviewed
    one by one. Reports still parsing, already under review, or not the user's are skipped with a reason.
    """
    from django_ratelimit.core import is_ratelimited

    from ai_settings.services import ROLE_REPORT_REVIEW, get_ai_config

    ids = request.data.get('ids') if isinstance(request.data, dict) else None
    if (
        not isinstance(ids, list)
        or not 0 < len(ids) <= MAX_BULK_REVIEW_REPORTS
        or not all(isinstance(value, int) and not isinstance(value, bool) for value in ids)
    ):
        return Response(
            {'ids': [f'Send a list of 1 to {MAX_BULK_REVIEW_REPORTS} report ids.']},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not get_ai_config(ROLE_REPORT_REVIEW).is_configured:
        return Response(
            {'error': 'AI review is not configured. Set it up in AI settings.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if is_ratelimited(request, group='report-ai-review-bulk', key='user', rate='10/m', increment=True):
        return Response(
            {'error': 'Too many AI review requests. Please wait a minute and try again.'},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    reports = {report.id: report for report in MedicalReport.objects.filter(user=request.user, id__in=ids)}
    queued, skipped = [], []
    for report_id in dict.fromkeys(ids):
        report = reports.get(report_id)
        if report is None:
            skipped.append({'id': report_id, 'reason': 'Report not found.'})
        elif report.status != 'COMPLETED':
            skipped.append({'id': report_id, 'reason': 'The report has not finished parsing.'})
        elif review_status(report) == PENDING:
            skipped.append({'id': report_id, 'reason': 'An AI review is already queued or running.'})
        else:
            queue_review(report.id, start_review(report))
            queued.append(report_id)
    return Response({'queued': queued, 'skipped': skipped}, status=status.HTTP_202_ACCEPTED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def stop_ai_review(request, report_id):
    """Stop the report's queued or running AI review; nothing from it is stored or applied."""
    report = get_object_or_404(MedicalReport, id=report_id, user=request.user)
    run_id = stop_review(report)
    if run_id is None:
        return Response(
            {'error': 'No AI review is queued or running for this report.'},
            status=status.HTTP_409_CONFLICT,
        )
    if run_id:
        transaction.on_commit(lambda: cancel_review_task(run_id))
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def dismiss_ai_review_suggestion(request, report_id, suggestion_id):
    """Remove one stored AI review suggestion the user dismissed."""
    report = get_object_or_404(MedicalReport, id=report_id, user=request.user)
    dismiss_suggestion(report, suggestion_id)
    return Response(status=status.HTTP_204_NO_CONTENT)


def _review_payload(report, request):
    return {
        'review': visible_review(report),
        'test_results': TestResultSerializer(report.test_results.all(), many=True, context={'request': request}).data,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def accept_ai_review_suggestions(request, report_id):
    """Apply accepted AI review suggestions together; returns the report's results and review afterwards."""
    report = get_object_or_404(MedicalReport, id=report_id, user=request.user)
    ids = request.data.get('ids') if isinstance(request.data, dict) else None
    if not isinstance(ids, list) or not all(isinstance(value, int) and not isinstance(value, bool) for value in ids):
        return Response({'ids': ['Send a list of suggestion ids.']}, status=status.HTTP_400_BAD_REQUEST)
    applied = apply_suggestions(report, ids)
    return Response({'applied': applied, **_review_payload(report, request)})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def undo_ai_review_change(request, report_id, applied_id):
    """Revert one change applied from the AI review, unless the result was edited since."""
    report = get_object_or_404(MedicalReport, id=report_id, user=request.user)
    try:
        undo_applied(report, applied_id)
    except ReviewConflict as exc:
        return Response({'error': str(exc)}, status=status.HTTP_409_CONFLICT)
    return Response(_review_payload(report, request))


MAX_SEARCH_RESULTS = 200


def unlinked_name_key(name: object) -> str:
    """Spellings of one name not linked to the catalog ("Antibody, IgG", "ANTIBODY,IGG") share this key."""
    return alias_key(name) or normalize_test_identifier(name)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_health_trend_parameters(request):
    """Tests the user has results for: one entry per catalog test, or per printed name that matches none.

    numeric_count counts results with a number; a name with none (only "Negative", "Absent") cannot be linked.
    """
    groups: dict[str, dict] = {}
    rows = TestResult.objects.filter(report__user=request.user).values_list(
        'test_type__name', 'test_type__display_name', 'test_name', 'value'
    )
    for type_name, display_name, test_name, value in rows:
        if type_name:
            key = f'type:{type_name}'
        elif normalize_test_identifier(test_name):
            key = f'name:{unlinked_name_key(test_name)}'
        else:
            continue
        group = groups.setdefault(
            key,
            {'key': key, 'name': display_name, 'test_type': type_name, 'result_count': 0, 'numeric_count': 0,
             'printed_names': set()},
        )
        group['result_count'] += 1
        group['numeric_count'] += int(bool(str(value or '').strip()) and is_measurement(value))
        group['printed_names'].add(test_name)

    parameters = []
    for group in groups.values():
        printed_names = sorted(group['printed_names'])
        parameters.append({**group, 'name': group['name'] or printed_names[0], 'printed_names': printed_names})
    parameters.sort(key=lambda group: group['name'].casefold())
    return Response(parameters)


def _trend_series(user, *, test_type_name: str = '', unlinked_name: str = '', parameter_name: str = '') -> dict:
    """One test's results over time, with every value put into the unit most of them use.

    The test is a catalog test (test_type_name), a printed name the catalog does not know (unlinked_name),
    or a typed search (parameter_name), which is matched to the catalog when it can be. `key` is how the
    caller asked for it, so a page comparing several trends can tell them apart.
    """
    test_results = TestResult.objects.filter(report__user=user)
    if test_type_name:
        key = f'type:{test_type_name}'
        test_type = LabTestType.objects.filter(name=test_type_name).first()
        test_results = test_results.filter(test_type=test_type) if test_type else test_results.none()
    elif unlinked_name:
        # Results under this name that stayed unlinked, such as "Negative" CRP results, keep their own trend.
        key = f'name:{unlinked_name_key(unlinked_name)}'
        test_type = None
        wanted = unlinked_name_key(unlinked_name)
        unlinked = test_results.filter(test_type__isnull=True).values_list('id', 'test_name')
        test_results = test_results.filter(pk__in=[pk for pk, name in unlinked if unlinked_name_key(name) == wanted])
    else:
        test_type = resolve_test_type(parameter_name, user_id=user.pk)
        key = f'type:{test_type.name}' if test_type else f'name:{unlinked_name_key(parameter_name)}'
        name_filter = Q(test_type__isnull=True, test_name__iexact=parameter_name)
        test_results = test_results.filter(Q(test_type=test_type) | name_filter if test_type else name_filter)
    test_results = list(test_results.select_related('report').order_by('report__report_date'))

    unit, points = trend_points(test_results, test_type)
    trends = [
        {
            'date': result.report.report_date.isoformat() if result.report.report_date else '',
            'report_id': result.report_id,
            'report_title': result.report.title,
            'result_id': result.id,
            'printed_name': result.test_name,
            **point,
        }
        for result, point in zip(test_results, points)
    ]
    return {
        'key': key,
        'parameter': test_type.display_name if test_type else (unlinked_name or parameter_name),
        'test_type': test_type.name if test_type else None,
        'unit': unit,
        'unconverted_count': sum(point['unit_status'] == UNCONVERTED for point in points),
        'trends': trends,
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_health_trends(request):
    """Results over time for one test: a catalog test (test_type), a name not linked to the catalog (name),
    or a typed search (parameter), which is matched to the catalog when it can be.

    Values are put into the unit most results use (see lab_tests.trend_units); unit_status marks each point.
    """
    parameter_name = (request.GET.get('parameter') or '').strip()
    test_type_name = (request.GET.get('test_type') or '').strip()
    unlinked_name = (request.GET.get('name') or '').strip()
    if not (parameter_name or test_type_name or unlinked_name):
        return Response({'error': 'Parameter name required'}, status=status.HTTP_400_BAD_REQUEST)

    return Response(_trend_series(
        request.user,
        test_type_name=test_type_name,
        unlinked_name=unlinked_name,
        parameter_name=parameter_name,
    ))


MAX_COMPARED_TRENDS = 6


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_health_trends_multi(request):
    """Several tests' trends in one response, so they can be drawn on one time axis.

    Repeat `test_type` for catalog tests, `name` for printed names the catalog does not know, and `parameter`
    for typed searches. Each series carries its own unit: tests measured in different units are only
    comparable in shape, which is the chart's business, not this endpoint's.
    """
    asked = (
        [('test_type', value) for value in request.GET.getlist('test_type')]
        + [('name', value) for value in request.GET.getlist('name')]
        + [('parameter', value) for value in request.GET.getlist('parameter')]
    )
    asked = [(kind, value.strip()) for kind, value in asked if value.strip()]
    if not asked:
        return Response({'error': 'Name at least one test.'}, status=status.HTTP_400_BAD_REQUEST)
    if len(asked) > MAX_COMPARED_TRENDS:
        return Response(
            {'error': f'Compare at most {MAX_COMPARED_TRENDS} tests at a time.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    series = []
    seen = set()
    for kind, value in asked:
        argument = {'test_type': 'test_type_name', 'name': 'unlinked_name', 'parameter': 'parameter_name'}[kind]
        item = _trend_series(request.user, **{argument: value})
        # Asking for one test by key and again by its printed name would otherwise draw it twice.
        if item['key'] in seen:
            continue
        seen.add(item['key'])
        series.append(item)
    return Response({'series': series})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_test_results(request):
    """Results whose name or catalog test contains the query, newest report first, with the report each is in."""
    query = (request.GET.get('q') or '').strip()
    if len(query) < 2:
        return Response({'error': 'Type at least 2 characters.'}, status=status.HTTP_400_BAD_REQUEST)
    matches = list(
        TestResult.objects.filter(report__user=request.user)
        .filter(Q(test_name__icontains=query) | Q(test_type__display_name__icontains=query))
        .select_related('report', 'test_type')
        .order_by('-report__report_date', '-report__created_at', 'test_name')[:MAX_SEARCH_RESULTS + 1]
    )
    return Response({
        'results': [
            {
                'id': result.id,
                'test_name': result.test_name,
                'value': result.value,
                'unit': result.unit,
                'reference_range': result.reference_range,
                'status': result.status,
                'test_type_name': result.test_type.name if result.test_type_id else None,
                'report': {
                    'id': result.report_id,
                    'title': result.report.title,
                    'report_date': result.report.report_date.isoformat() if result.report.report_date else '',
                    'lab_name': result.report.lab_name or '',
                },
            }
            for result in matches[:MAX_SEARCH_RESULTS]
        ],
        'truncated': len(matches) > MAX_SEARCH_RESULTS,
    })


class TestResultUpdateView(generics.UpdateAPIView):
    """View for updating test results manually"""
    serializer_class = TestResultSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return TestResult.objects.filter(report__user=self.request.user)
    
    def perform_update(self, serializer):
        """Override to validate and convert units if needed"""
        # Get the old unit before saving
        old_unit = serializer.instance.unit if serializer.instance else None
        
        # If unit was changed, try to convert the value
        if 'unit' in serializer.validated_data:
            new_unit = serializer.validated_data['unit']
            
            if old_unit and new_unit != old_unit:
                try:
                    # Try to convert the value to the new unit
                    from lab_tests.models import UnitConversion, LabTestUnit
                    
                    from_unit_obj = LabTestUnit.objects.filter(name=old_unit).first()
                    to_unit_obj = LabTestUnit.objects.filter(name=new_unit).first()
                    
                    if from_unit_obj and to_unit_obj:
                        conversion = UnitConversion.objects.filter(
                            test_type=serializer.instance.test_type,
                            from_unit=from_unit_obj,
                            to_unit=to_unit_obj,
                            is_active=True
                        ).first()
                        
                        if conversion:
                            old_value = Decimal(serializer.instance.value)
                            new_value = conversion.convert_value(old_value)
                            serializer.validated_data['value'] = str(new_value)
                            
                except (ValueError, InvalidOperation, AttributeError):
                    # If conversion fails, keep the original value
                    pass
        
        # Save the instance
        instance = serializer.save()


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def convert_test_result_unit(request, test_result_id):
    """Convert a test result to a different unit"""
    # Resolve ownership before the broad handler so non-owners get 404, not 500.
    test_result = get_object_or_404(
        TestResult, id=test_result_id, report__user=request.user
    )
    try:
        target_unit = request.data.get('target_unit')
        if not target_unit:
            return Response(
                {'error': 'target_unit is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get current and target units
        from lab_tests.models import LabTestUnit, UnitConversion
        
        # Handle N/A units
        if test_result.unit == 'N/A' or not test_result.unit:
            return Response(
                {'error': 'Cannot convert from N/A unit. Please edit the unit first.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Try to find units by name first, then by symbol
        current_unit_obj = LabTestUnit.objects.filter(name=test_result.unit).first()
        if not current_unit_obj:
            current_unit_obj = LabTestUnit.objects.filter(symbol=test_result.unit).first()
            
        target_unit_obj = LabTestUnit.objects.filter(name=target_unit).first()
        if not target_unit_obj:
            target_unit_obj = LabTestUnit.objects.filter(symbol=target_unit).first()
        
        if not current_unit_obj or not target_unit_obj:
            return Response(
                {'error': 'Invalid unit specified'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Find conversion
        test_type = test_result.test_type or resolve_test_type(test_result.test_name, user_id=request.user.pk)
        if test_type is None:
            return Response(
                {'error': 'Test type is not linked to the lab catalog'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        conversion = UnitConversion.objects.filter(
            test_type=test_type,
            from_unit=current_unit_obj,
            to_unit=target_unit_obj,
            is_active=True
        ).first()
        
        if not conversion:
            return Response(
                {'error': f'No conversion available from {test_result.unit} to {target_unit}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Convert the value
        try:
            current_value = Decimal(test_result.value)
            converted_value = conversion.convert_value(current_value)
            
            # Update the test result
            test_result.value = str(converted_value)
            test_result.unit = target_unit
            test_result.save()
            
            return Response({
                'id': test_result.id,
                'value': test_result.value,
                'unit': test_result.unit,
                'original_value': str(current_value),
                'original_unit': current_unit_obj.name,
                'conversion_factor': str(conversion.conversion_factor)
            })
            
        except (ValueError, InvalidOperation):
            return Response(
                {'error': 'Invalid value for conversion'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def validate_test_result(request, test_result_id):
    """Validate a test result against reference ranges"""
    # Resolve ownership before the broad handler so non-owners get 404, not 500.
    test_result = get_object_or_404(
        TestResult, id=test_result_id, report__user=request.user
    )
    try:
        from lab_tests.models import LabTestUnit, LabTestValidationRule
        
        # Try to find the test type
        test_type = test_result.test_type or resolve_test_type(test_result.test_name, user_id=request.user.pk)
        if not test_type:
            return Response({
                'status': 'UNKNOWN',
                'message': 'Test type not found in database',
                'value': test_result.value,
                'unit': test_result.unit
            })
        
        # Get unit object - handle N/A units gracefully
        if test_result.unit == 'N/A' or not test_result.unit:
            return Response({
                'status': 'UNKNOWN',
                'message': 'Cannot validate without a valid unit',
                'value': test_result.value,
                'unit': test_result.unit
            })
        
        # Try to find unit by name first, then by symbol
        unit_obj = LabTestUnit.objects.filter(name=test_result.unit).first()
        if not unit_obj:
            unit_obj = LabTestUnit.objects.filter(symbol=test_result.unit).first()
        
        if not unit_obj:
            return Response({
                'status': 'UNKNOWN',
                'message': 'Unit not found in database',
                'value': test_result.value,
                'unit': test_result.unit
            })
        
        # Get validation rule
        validation_rule = LabTestValidationRule.objects.filter(
            test_type=test_type,
            unit=unit_obj,
            is_active=True
        ).first()
        
        if not validation_rule:
            return Response({
                'status': 'UNKNOWN',
                'message': 'No validation rules found for this test and unit',
                'value': test_result.value,
                'unit': test_result.unit
            })
        
        # Validate the value
        status_result, message = validation_rule.validate_value(test_result.value)
        
        # Update the test result status
        test_result.test_type = test_type
        test_result.status = normalize_test_status(status_result)
        test_result.save(update_fields=['test_type', 'status'])
        
        return Response({
            'status': status_result,
            'message': message,
            'value': test_result.value,
            'unit': test_result.unit,
            'normal_range': f"{validation_rule.normal_min} - {validation_rule.normal_max} {unit_obj.symbol}" if validation_rule.normal_min is not None and validation_rule.normal_max is not None else None
        })

    except Exception as e:
        logger.exception("validate_test_result failed for id=%s", test_result_id)
        return Response(
            {'error': 'Internal server error'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_upload_reports(request):
    """Bulk upload medical reports from multiple PDF files.

    Filenames that start with a date set report metadata:
      YYYY-MM-DD_labname.pdf   -> report_date and lab_name (e.g. 2026-05-14_lalpath.pdf)
      YYYY-MM-DD-anything.pdf  -> report_date only
    Files without a leading date use today's date.
    """
    files = request.FILES.getlist('files')
    if not files:
        return Response(
            {'error': 'No files provided. Use multipart/form-data with key "files".'},
            status=status.HTTP_400_BAD_REQUEST
        )
    if len(files) > MAX_BULK_UPLOAD_REPORTS:
        return Response(
            {'error': f'Upload at most {MAX_BULK_UPLOAD_REPORTS} reports at a time.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Filename stem: YYYY-MM-DD, then optionally a separator and the rest of the name
    FILENAME_RE = re.compile(r'^(\d{4}-\d{2}-\d{2})(?:([-_.])(.*))?$')

    created = []
    errors = []
    review = _review_choice(request)

    for uploaded_file in files:
        filename = uploaded_file.name
        if not filename.lower().endswith('.pdf'):
            errors.append({'file': filename, 'error': 'Only PDF files are supported'})
            continue
        try:
            validate_medical_upload(uploaded_file)
        except ValueError as exc:
            errors.append({'file': filename, 'error': str(exc)})
            continue
        lab_name = ''
        name_match = FILENAME_RE.match(filename[:-len('.pdf')])
        if name_match:
            date_str, separator, rest = name_match.groups()
            try:
                report_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                errors.append({'file': filename, 'error': f'Invalid date in filename: {date_str}'})
                continue
            if separator == '_':
                lab_name = rest.strip()[:200]
        else:
            # Fallback to today if no date found
            report_date = datetime.today().date()

        try:
            with transaction.atomic():
                report = MedicalReport.objects.create(
                    user=request.user,
                    title=filename,
                    report_type='LAB',
                    lab_name=lab_name,
                    report_date=report_date,
                    file=uploaded_file,
                )

                _queue_pdf_parse(report, review=review)

            created.append({
                'id': report.id,
                'title': report.title,
                'lab_name': report.lab_name,
                'report_date': str(report.report_date),
                'status': report.status,
                'is_parsed': report.is_parsed,
            })
        except Exception as e:
            logger.error("Error creating report for %s: %s", filename, e)
            errors.append({'file': filename, 'error': 'Failed to create report'})

    return Response({
        'total': len(files),
        'created': len(created),
        'errors': len(errors),
        'reports': created,
        'error_details': errors,
    }, status=status.HTTP_200_OK)
