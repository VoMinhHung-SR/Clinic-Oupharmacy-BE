from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, generics
from rest_framework.parsers import JSONParser, FormParser,MultiPartParser

from rest_framework import permissions, status, filters
from mainApp.filters import RecipientsFilter
from mainApp.models import User, Examination, Patient
from mainApp.paginator import ExaminationPaginator
from mainApp.permissions import UserPermission, OwnerExaminationPermission
from mainApp.serializers import UserSerializer, ExaminationSerializer, PatientSerializer, UserAddressSerializer
from rest_framework.decorators import action
from rest_framework.response import Response
from ..tasks import load_waiting_room

class UserViewSet(viewsets.ViewSet, generics.CreateAPIView, generics.RetrieveAPIView,
                  generics.UpdateAPIView, generics.ListAPIView):
    queryset = User.objects.filter(is_active=True)
    serializer_class = UserSerializer
    parser_classes = [JSONParser, MultiPartParser, ]
    filter_backends = [filters.OrderingFilter, DjangoFilterBackend]
    filterset_class = RecipientsFilter

    def get_permissions(self):
        if self.action in ['get_current_user']:
            return [permissions.IsAuthenticated()]
        if self.action in ['update', 'partial_update', 'get_patients',
                           'change_password', 'change_avatar']:
            return [UserPermission()]
        if self.action in ['get_examinations']:
            return [OwnerExaminationPermission()]
        return [permissions.AllowAny()]

    def get_queryset(self):
        queryset = self.queryset
        kw = self.request.query_params.get('kw')
        if kw:
            queryset = queryset.filter(username__icontains=kw)
        return queryset

    @action(methods=['get'], detail=False, url_path='current-user')
    def get_current_user(self, request):
        return Response(self.serializer_class(request.user, context={'request': request}).data,
                        status=status.HTTP_200_OK)

    @action(methods=['patch'], detail=True, url_path='change-avatar',
            parser_classes=[MultiPartParser, FormParser])
    def change_avatar(self, request, pk=None):
        user = self.get_object()
        avatar = request.FILES.get('avatar_path')
        if not avatar:
            return Response({'detail': 'No avatar file provided.'}, status=status.HTTP_400_BAD_REQUEST)
        user.avatar = avatar
        user.save()
        avatar_url = user.avatar.url if user.avatar else None
        return Response({'avatar': avatar_url}, status=status.HTTP_200_OK)

    @action(methods=['get'], detail=True, url_path='booking-list', pagination_class=ExaminationPaginator)
    def get_examinations(self, request, pk):
        examinations = Examination.objects.filter(user=pk).all()
        paginator = ExaminationPaginator()
        page_size = request.query_params.get('page_size', 10)
        paginator.page_size = page_size
        result_page = paginator.paginate_queryset(examinations, request)
        serializer = ExaminationSerializer(result_page, context={'request': request}, many=True)
        return paginator.get_paginated_response(serializer.data)

    @action(methods=['get'], detail=True, url_path='location-info')
    def get_user_location_info(self, request, pk):
        user = self.get_object()
        default = user.addresses.filter(is_default=True).first() or user.addresses.first()
        data = UserAddressSerializer(default).data if default else None
        return Response(status=status.HTTP_200_OK, data=data)

    @action(methods=['get'], detail=False, url_path='demo')
    def demo (self, request):
        try:
            load_waiting_room.delay()
        except Exception as ex:
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data=[])
        return Response(status=status.HTTP_200_OK, data=[])

    @action(methods=['post'], detail=True, url_path='change-password')
    def change_password(self, request, pk):
        user = self.get_object()
        try:
            new_password = request.data.get('new_password')
            user.set_password(new_password)
            user.save()
        except Exception as ex:
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(status=status.HTTP_200_OK)

    @action(methods=['get'], detail=True, url_path='get-patients')
    def get_patients(self, request, pk):
        user = self.get_object()
        try:
            patients = Patient.objects.filter(user=user).all()
        except Exception as ex:
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data=[])

        if patients:
            return Response(
                data=PatientSerializer(patients, context={'request': request}, many=True).data,
                status=status.HTTP_200_OK)
        return Response(data=[], status=status.HTTP_200_OK)