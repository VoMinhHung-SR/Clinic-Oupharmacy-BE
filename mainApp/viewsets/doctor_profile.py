from rest_framework import viewsets, generics

from mainApp.models import DoctorProfile
from mainApp.serializers import DoctorProfileSerializer


class DoctorProfileViewSet(viewsets.ViewSet, generics.ListAPIView, generics.UpdateAPIView,
                      generics.CreateAPIView, generics.DestroyAPIView):
    queryset = DoctorProfile.objects.all()
    serializer_class = DoctorProfileSerializer
