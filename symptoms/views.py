from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Symptom, SymptomLog
from .serializers import (
    SymptomSerializer, SymptomListSerializer,
    SymptomLogSerializer, SymptomLogCreateSerializer
)


class SymptomListCreateView(generics.ListCreateAPIView):
    """View for listing and creating symptoms"""
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        return SymptomSerializer

    def get_queryset(self):
        return Symptom.objects.filter(user=self.request.user).prefetch_related('logs')


class SymptomDetailView(generics.RetrieveUpdateDestroyAPIView):
    """View for retrieving, updating, and deleting symptoms"""
    serializer_class = SymptomSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Symptom.objects.filter(user=self.request.user)


class SymptomLogListCreateView(generics.ListCreateAPIView):
    """View for listing and creating symptom logs for a specific symptom"""
    serializer_class = SymptomLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        symptom_id = self.kwargs['symptom_id']
        symptom = get_object_or_404(Symptom, id=symptom_id, user=self.request.user)
        return SymptomLog.objects.filter(symptom=symptom)

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return SymptomLogSerializer
        return SymptomLogCreateSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.request.method == 'POST':
            symptom_id = self.kwargs['symptom_id']
            context['symptom'] = get_object_or_404(Symptom, id=symptom_id, user=self.request.user)
        return context


class SymptomLogDetailView(generics.RetrieveUpdateDestroyAPIView):
    """View for retrieving, updating, and deleting symptom logs"""
    serializer_class = SymptomLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        symptom_id = self.kwargs['symptom_id']
        symptom = get_object_or_404(Symptom, id=symptom_id, user=self.request.user)
        return SymptomLog.objects.filter(symptom=symptom)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_active_symptoms(request):
    """View for getting active symptoms"""
    active_symptoms = Symptom.objects.filter(
        user=request.user,
        is_ongoing=True
    ).order_by('-onset_date')
    
    serializer = SymptomListSerializer(active_symptoms, many=True)
    return Response(serializer.data)
