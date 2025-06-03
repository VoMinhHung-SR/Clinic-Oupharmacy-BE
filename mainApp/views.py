
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

from .models import CommonCity, UserRole, User, Category, Bill

# Create your views here.
wageBooking = 20000

class AuthInfo(APIView):
    def get(self, request):
        return Response(settings.OAUTH2_INFO, status=status.HTTP_200_OK)

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
        cities = list(CommonCity.objects.values("id", "name"))
        roles = list(UserRole.objects.values("id", "name"))
        categories = list(Category.objects.filter(active=True).values("id", "name"))

        doctors = User.objects.filter(role__name=ROLE_DOCTOR, is_active=True).values(
            "id", "email", "first_name", "last_name", "avatar"
        )
        nurses = User.objects.filter(role__name=ROLE_NURSE, is_active=True).values(
            "id", "email", "first_name", "last_name", "avatar"
        )

        def process_avatar(user):
            avatar = user["avatar"]
            if hasattr(avatar, 'url'):
                avatar = avatar.url
            elif not avatar or avatar == "null":
                avatar = None
            return {
                **user,
                "avatar": avatar
            }

        doctors_data = [process_avatar(doc) for doc in doctors]
        nurses_data = [process_avatar(nurse) for nurse in nurses]

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