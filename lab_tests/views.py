"""
Views for lab test management
"""
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Count, Q
from decimal import Decimal, InvalidOperation

from .catalog import LabTestTypeWriteSerializer, relink_everyone, remove_test_type, suggest_key, sync_default_unit
from .models import (
    LabTestType, LabTestUnit, LabTestTypeUnit, UnitConversion,
    LabTestPattern, LabTestValidationRule
)
from .serializers import (
    LabTestTypeSerializer, LabTestUnitSerializer, LabTestTypeUnitSerializer,
    UnitConversionSerializer, LabTestPatternSerializer, LabTestValidationRuleSerializer,
    UnitConversionRequestSerializer, UnitConversionResponseSerializer,
    TestValueValidationSerializer, TestValueValidationResponseSerializer
)
from .services import resolve_test_type


class LabTestTypeListView(generics.ListCreateAPIView):
    """Lists catalog tests, and adds one.

    The catalog is shared by everyone on the server, and any signed-in user can add a test. `active` picks which
    entries are listed: "true" (the default) the ones in use, "false" only the removed ones, "all" both.
    """
    def get_serializer_class(self):
        return LabTestTypeWriteSerializer if self.request.method == 'POST' else LabTestTypeSerializer

    def get_queryset(self):
        queryset = LabTestType.objects.annotate(result_count=Count('test_results'))

        active = (self.request.query_params.get('active') or 'true').casefold()
        if active != 'all':
            queryset = queryset.filter(is_active=active != 'false')

        # Filter by category if provided
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category__iexact=category)
        
        # Search by name or aliases
        search = self.request.query_params.get('q')
        if search:
            queryset = queryset.filter(
                Q(display_name__icontains=search) |
                Q(name__icontains=search) |
                Q(aliases__icontains=search)
            )
        
        return queryset.order_by('category', 'display_name')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Added here, so populate_lab_tests never overwrites or removes it.
        test_type = serializer.save(source=LabTestType.SOURCE_USER, edited_by_user=True)
        sync_default_unit(test_type)
        # A new name or alias can claim results that were unlinked or under another test.
        relinked = relink_everyone()
        return Response(
            {**LabTestTypeWriteSerializer(test_type).data, 'relinked': relinked},
            status=status.HTTP_201_CREATED,
        )


class LabTestTypeDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Reads, changes, or removes one catalog test, by its key.

    An entry changed here is marked so `populate_lab_tests` stops overwriting it on the next deploy. Removing
    deletes an entry someone added here, and deactivates a built-in one, which the loader would restore.
    Either way the results stay: they lose the link and go back to their printed name.
    """
    lookup_field = 'name'

    def get_serializer_class(self):
        return LabTestTypeSerializer if self.request.method == 'GET' else LabTestTypeWriteSerializer

    def get_queryset(self):
        # Removed entries are readable and editable here, so one can be put back.
        return LabTestType.objects.annotate(result_count=Count('test_results'))

    def update(self, request, *args, **kwargs):
        test_type = self.get_object()
        serializer = self.get_serializer(test_type, data=request.data, partial=kwargs.pop('partial', False))
        serializer.is_valid(raise_exception=True)
        test_type = serializer.save(edited_by_user=True)
        sync_default_unit(test_type)
        relinked = relink_everyone()
        return Response({**serializer.data, 'relinked': relinked})

    def destroy(self, request, *args, **kwargs):
        test_type = self.get_object()
        outcome = remove_test_type(test_type)
        unlinked = relink_everyone()
        return Response({'removed': outcome, 'unlinked': unlinked})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def suggest_test_type_key(request):
    """A catalog key for a display name, free of the keys already used, for the add form."""
    base = suggest_key(request.query_params.get('display_name'))
    if not base:
        return Response({'key': ''})
    taken = set(LabTestType.objects.filter(name__startswith=base).values_list('name', flat=True))
    key = base
    suffix = 2
    while key in taken:
        key = f'{base}_{suffix}'
        suffix += 1
    return Response({'key': key})


class LabTestUnitListView(generics.ListAPIView):
    """View for listing all lab test units"""
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_serializer_class(self):
        """Return appropriate serializer based on whether test_type is provided"""
        if self.request.query_params.get('test_type'):
            return LabTestTypeUnitSerializer
        return LabTestUnitSerializer

    def get_queryset(self):
        test_type = self.request.query_params.get('test_type')

        if test_type:
            test_type_obj = resolve_test_type(test_type)
            if test_type_obj is None:
                return LabTestTypeUnit.objects.none()
            # Return LabTestTypeUnit objects for the specific test type
            return LabTestTypeUnit.objects.filter(
                test_type=test_type_obj,
                is_active=True
            ).select_related('test_type', 'unit').order_by('unit__category', 'unit__name')
        else:
            # Return all LabTestUnit objects
            queryset = LabTestUnit.objects.filter(is_active=True)

            # Filter by category if provided
            category = self.request.query_params.get('category')
            if category:
                queryset = queryset.filter(category__iexact=category)

            return queryset.order_by('category', 'name')


class LabTestTypeUnitsView(generics.ListAPIView):
    """View for listing units supported by a specific test type"""
    serializer_class = LabTestTypeUnitSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    
    def get_queryset(self):
        test_type_name = self.kwargs['test_type']
        test_type = resolve_test_type(test_type_name)
        if test_type is None:
            return LabTestTypeUnit.objects.none()
        return LabTestTypeUnit.objects.filter(
            test_type=test_type,
            is_active=True
        ).select_related('test_type', 'unit')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def convert_units(request):
    """Convert a value from one unit to another"""
    serializer = UnitConversionRequestSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    data = serializer.validated_data
    value = data['value']
    from_unit_name = data['from_unit']
    to_unit_name = data['to_unit']
    
    try:
        # Get the units
        test_type_obj = data['test_type_obj']
        from_unit = data['from_unit_obj']
        to_unit = data['to_unit_obj']
        
        # Get the conversion
        conversion = UnitConversion.objects.get(
            test_type=test_type_obj,
            from_unit=from_unit,
            to_unit=to_unit,
            is_active=True
        )
        
        # Perform the conversion
        converted_value = conversion.convert_value(value)
        
        response_data = {
            'original_value': value,
            'original_unit': from_unit.display_name,
            'converted_value': Decimal(str(converted_value)).quantize(Decimal('0.0001')),
            'converted_unit': to_unit.display_name,
            'conversion_factor': conversion.conversion_factor,
            'formula': conversion.formula or f"{from_unit.symbol} × {conversion.conversion_factor} = {to_unit.symbol}"
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except LabTestUnit.DoesNotExist:
        return Response(
            {'error': 'One or both units not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except UnitConversion.DoesNotExist:
        return Response(
            {'error': f'No conversion available from {from_unit_name} to {to_unit_name}'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except (InvalidOperation, ValueError) as e:
        return Response(
            {'error': f'Invalid value for conversion: {str(e)}'}, 
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_unit_conversions(request):
    """Get available unit conversions for a test type"""
    test_type = request.query_params.get('test_type')
    
    if not test_type:
        return Response(
            {'error': 'test_type parameter is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Get the test type
        test_type_obj = resolve_test_type(test_type)
        if test_type_obj is None:
            raise LabTestType.DoesNotExist
        
        # Get all supported units for this test type
        supported_units = LabTestTypeUnit.objects.filter(
            test_type=test_type_obj,
            is_active=True
        ).select_related('unit')
        
        # Get all possible conversions between these units
        unit_ids = [su.unit.id for su in supported_units]
        conversions = UnitConversion.objects.filter(
            test_type=test_type_obj,
            from_unit_id__in=unit_ids,
            to_unit_id__in=unit_ids,
            is_active=True
        ).select_related('from_unit', 'to_unit')
        
        serializer = UnitConversionSerializer(conversions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except LabTestType.DoesNotExist:
        return Response(
            {'error': f'Test type "{test_type}" not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def validate_test_value(request):
    """Validate a test value against reference ranges"""
    serializer = TestValueValidationSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    data = serializer.validated_data
    test_type = data['test_type']
    value = data['value']
    unit_name = data['unit']
    
    try:
        # Get the test type and unit
        test_type_obj = resolve_test_type(test_type)
        if test_type_obj is None:
            raise LabTestType.DoesNotExist
        unit_obj = LabTestUnit.objects.get(name=unit_name)
        
        # Get validation rule
        try:
            validation_rule = LabTestValidationRule.objects.get(
                test_type=test_type_obj,
                unit=unit_obj,
                is_active=True
            )
        except LabTestValidationRule.DoesNotExist:
            # Fallback to test type unit relationship
            try:
                test_type_unit = LabTestTypeUnit.objects.get(
                    test_type=test_type_obj,
                    unit=unit_obj,
                    is_active=True
                )
                validation_rule = LabTestValidationRule(
                    test_type=test_type_obj,
                    unit=unit_obj,
                    normal_min=test_type_unit.normal_min,
                    normal_max=test_type_unit.normal_max,
                )
            except LabTestTypeUnit.DoesNotExist:
                return Response(
                    {'error': f'No validation rules found for {test_type} with unit {unit_name}'}, 
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Validate the value
        status_result, message = validation_rule.validate_value(value)
        
        # Prepare response
        response_data = {
            'status': status_result,
            'message': message,
            'value': value,
            'unit': unit_obj.display_name,
            'normal_range': None,
            'critical_range': None
        }
        
        # Add range information if available
        if validation_rule.normal_min is not None and validation_rule.normal_max is not None:
            response_data['normal_range'] = f"{validation_rule.normal_min} - {validation_rule.normal_max} {unit_obj.symbol}"
        
        if (
            validation_rule.critical_low_min is not None
            or validation_rule.critical_high_max is not None
        ):
            critical_parts = []
            if validation_rule.critical_low_min is not None:
                critical_parts.append(f"< {validation_rule.critical_low_min}")
            if validation_rule.critical_high_max is not None:
                critical_parts.append(f"> {validation_rule.critical_high_max}")
            response_data['critical_range'] = " or ".join(critical_parts) + f" {unit_obj.symbol}"
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except LabTestType.DoesNotExist:
        return Response(
            {'error': f'Test type "{test_type}" not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except LabTestUnit.DoesNotExist:
        return Response(
            {'error': f'Unit "{unit_name}" not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except (InvalidOperation, ValueError) as e:
        return Response(
            {'error': f'Invalid value for validation: {str(e)}'}, 
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_test_types(request):
    """Search for lab test types"""
    query = request.query_params.get('q', '')
    
    if not query:
        return Response(
            {'error': 'Search query parameter "q" is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Search in name, display_name, and aliases
    test_types = LabTestType.objects.filter(
        Q(display_name__icontains=query) |
        Q(name__icontains=query) |
        Q(aliases__icontains=query),
        is_active=True
    ).order_by('category', 'display_name')[:20]  # Limit to 20 results
    
    serializer = LabTestTypeSerializer(test_types, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_test_categories(request):
    """Get all available test categories"""
    categories = LabTestType.objects.filter(
        is_active=True
    ).values_list('category', flat=True).distinct().order_by('category')
    
    return Response(list(categories), status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_unit_categories(request):
    """Get all available unit categories"""
    categories = LabTestUnit.objects.filter(
        is_active=True
    ).values_list('category', flat=True).distinct().order_by('category')
    
    return Response(list(categories), status=status.HTTP_200_OK)
