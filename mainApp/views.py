
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.db.models import Count
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework import viewsets, generics
from rest_framework import views

from .constant import ROLE_DOCTOR, ROLE_NURSE
from rest_framework.decorators import action, api_view, permission_classes

from rest_framework.parsers import MultiPartParser
from rest_framework.parsers import JSONParser

from .models import DoctorAvailability, CommonCity, UserRole, User, Category, Bill
from .serializers.examination import DoctorAvailabilitySerializer

# Create your views here.
wageBooking = 20000

class AuthInfo(APIView):
    def get(self, request):
        return Response(settings.OAUTH2_INFO, status=status.HTTP_200_OK)

class DoctorAvailabilityViewSet(viewsets.ViewSet, generics.ListAPIView, generics.DestroyAPIView,
                         generics.UpdateAPIView, generics.RetrieveAPIView, generics.CreateAPIView):
    queryset = DoctorAvailability.objects.all().order_by('start_time')
    serializer_class = DoctorAvailabilitySerializer
    parser_classes = [JSONParser, MultiPartParser, ]

    @action(methods=['post'], detail=False, url_path='get-doctor-availability')
    def get_doctor_availability(self, request):
        date_str = request.data.get('date')
        doctor_id = request.data.get('doctor')
        try:
            if date_str and doctor_id:
                date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                doctor_data = DoctorAvailability.objects.filter(doctor=doctor_id, day=date).all().order_by('start_time')
            else:
                return Response(status=status.HTTP_400_BAD_REQUEST,
                                data={"errMsg": "Can't get data, doctor or date is false"})

        except Exception as error:
            print(error)
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"errMsg": "Cant get data doctor or date is false"})

        if doctor_data:
            return Response(data=DoctorAvailabilitySerializer(doctor_data, context={'request': request}, many=True).data,
                            status=status.HTTP_200_OK)
        return Response(data=[], status=status.HTTP_200_OK)

class StatsView(views.APIView):
    def get(self, request):
        year = request.GET.get('year')

        stats = Bill.objects
        if year:
            year = int(year)
            stats = stats.filter(created_date__year=year)

        stats = stats.values('prescribing__diagnosis__examination__id', 'amount').annotate(
            count=Count('prescribing__diagnosis__examination__id'))
        return Response(data=stats, status=status.HTTP_200_OK)

    def post(self, request):
        quarter_one = request.POST.get('quarterOne')
        year = request.POST.get('year')

        stats = Bill.objects

        if quarter_one:
            quarter_one = int(quarter_one)
            if quarter_one == 1:
                stats = stats.filter(apply_date__month__range=[1, 3])
            elif quarter_one == 2:
                stats = stats.filter(apply_date__month__range=[4, 6])
            elif quarter_one == 3:
                stats = stats.filter(apply_date__month__range=[7, 9])
            elif quarter_one == 4:
                stats = stats.filter(apply_date__month__range=[10, 12])

        if year:
            stats = stats.filter(apply_date__year=year)
        stats = stats \
            .values('job_post__career__id', 'job_post__career__career_name') \
            .annotate(count=Count('job_post__career__id'))

        return Response(data=stats, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return Response(data={'message': "Login successfully"},
                            status=status.HTTP_202_ACCEPTED)
        else:
            return Response(data={'error_msg': "Invalid user"},
                            status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([AllowAny])
def logout_view(request):
    logout(request)
    return Response(status=status.HTTP_200_OK)

@api_view(http_method_names=["GET"])
def get_all_config(request):
    try:
        # database
        cities = CommonCity.objects.values("id", "name")
        roles = UserRole.objects.values("id", "name")
        nurses = User.objects.filter(role__name=ROLE_NURSE,is_active=True)
        doctors = User.objects.filter(role__name=ROLE_DOCTOR, is_active=True)
        categories = Category.objects.filter(active=True).values("id", "name")

        doctors_data = [
            {
                "id": doctor.id,
                "email": doctor.email,
                "first_name": doctor.first_name,
                "last_name": doctor.last_name,
                "avatar": doctor.avatar.url if doctor.avatar else None  # Get avatar URL if available
            }
            for doctor in doctors
        ]
        nurses_data = [
            {
                "id": nurse.id,
                "email": nurse.email,
                "first_name": nurse.first_name,
                "last_name": nurse.last_name,
                "avatar": nurse.avatar.url if nurse.avatar else None  # Get avatar URL if available
            }
            for nurse in nurses
        ]

        res_data = {
            "cityOptions": cities,
            "roles": roles,
            "doctors": doctors_data,
            "nurses": nurses_data,
            "categories": categories
        }

    except Exception as ex:
        return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"errMgs": "value Error"})
    else:
        return Response(data=res_data, status=status.HTTP_200_OK)