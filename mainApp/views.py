from django.shortcuts import render
from rest_framework import viewsets, status, views
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from mainApp.models import *
from mainApp.serializers import *
from mainApp.admin_views import *
from mainApp.services.statistic_views import *
import requests
import json
from django.conf import settings
from oauth2_provider.models import AccessToken
from datetime import datetime, timedelta
import random
import string
from firebase_admin import auth as firebase_auth

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

from .models import CommonCity, UserRole, User, Category, Bill, DoctorProfile
from .serializers import DoctorProfileSerializer
from .serializers import ContactSerializer
from . import cloud_context
from django.core.mail import send_mail

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

        doctor_profiles = DoctorProfile.objects.select_related(
            'user', 'user__role'
        ).prefetch_related(
            'specializations'
        ).filter(
            user__role__name=ROLE_DOCTOR,
            user__is_active=True
        )

        nurses_data = []
        nurses_queryset = User.objects.filter(
            role__name=ROLE_NURSE, 
            is_active=True
        )
        
        for nurse in nurses_queryset:
            avatar_path = None
            if nurse.avatar:
                avatar_path = "{cloud_context}{image_name}".format(
                    cloud_context=cloud_context,
                    image_name=str(nurse.avatar)
                )
            
            nurses_data.append({
                'id': nurse.id,
                'email': nurse.email,
                'first_name': nurse.first_name,
                'last_name': nurse.last_name,
                'avatar': avatar_path
            })

        res_data = {
            "cityOptions": cities,
            "roles": roles,
            "doctors": DoctorProfileSerializer(doctor_profiles, many=True).data,
            "nurses": nurses_data,
            "categories": categories
        }

    except Exception as ex:
        return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"errMgs": f"Error: {str(ex)}"})
    else:
        return Response(data=res_data, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([AllowAny])
def contact_admin(request):
    serializer = ContactSerializer(data=request.data)
    if serializer.is_valid():
        data = serializer.validated_data
        subject = data.get('subject') or 'Liên hệ từ website OUPharmacy'
        message = f"Họ tên: {data['name']}\nEmail: {data['email']}\nĐiện thoại: {data.get('phone', '')}\n\nNội dung:\n{data['message']}"
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=None, 
                recipient_list=[settings.EMAIL_HOST_USER],
                fail_silently=False,
            )
            return Response({'message': 'Gửi email thành công!'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': f'Lỗi gửi email: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    else:
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def firebase_social_login(request):
    """Handle Firebase social login (Google, Facebook, etc.)"""
    try:
        id_token = request.data.get('id_token')
        provider = request.data.get('provider', 'google')  # google, facebook, apple
        
        if not id_token:
            return Response({'error': 'ID token is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Verify Firebase ID token
        try:
            decoded_token = firebase_auth.verify_id_token(id_token)
        except Exception as e:
            return Response({'error': 'Invalid Firebase token'}, status=status.HTTP_400_BAD_REQUEST)
        
        user_id = decoded_token['uid']
        email = decoded_token.get('email')
        name = decoded_token.get('name', '')
        picture = decoded_token.get('picture')
        
        # Split name into first_name and last_name
        name_parts = name.split(' ', 1) if name else ['', '']
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ''
        
        # Check if user exists by social_id
        user = User.objects.filter(social_id=user_id, social_provider=provider).first()
        
        if not user:
            # Check if email already exists
            if email:
                existing_user = User.objects.filter(email=email).first()
                if existing_user:
                    # Link existing account to social provider
                    existing_user.social_id = user_id
                    existing_user.social_provider = provider
                    existing_user.save()
                    user = existing_user
                else:
                    # Create new user
                    user = User.objects.create(
                        email=email,
                        first_name=first_name,
                        last_name=last_name,
                        social_id=user_id,
                        social_provider=provider,
                        is_active=True
                    )
            else:
                # Create user with generated email if no email provided
                generated_email = f"{user_id}@{provider}.com"
                user = User.objects.create(
                    email=generated_email,
                    first_name=first_name,
                    last_name=last_name,
                    social_id=user_id,
                    social_provider=provider,
                    is_active=True
                )
        
        # Update user info if needed
        if not user.first_name and first_name:
            user.first_name = first_name
        if not user.last_name and last_name:
            user.last_name = last_name
        if picture and not user.avatar:
            user.avatar = picture
        user.save()
        
        # Generate OAuth2 token
        token = generate_oauth_token(user)
        
        return Response({
            'access_token': token.token,
            'refresh_token': token.refresh_token.token,
            'token_type': 'Bearer',
            'expires_in': 2592000,  # 30 days
            'user': {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'role': user.role.name if user.role else None,
                'avatar': user.avatar.url if user.avatar else None
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def google_login(request):
    """Legacy Google login - redirects to Firebase social login"""
    return firebase_social_login(request)

@api_view(['POST'])
@permission_classes([AllowAny])
def facebook_login(request):
    """Legacy Facebook login - redirects to Firebase social login"""
    return firebase_social_login(request)

def generate_oauth_token(user):
    """Generate OAuth2 token for user"""
    from oauth2_provider.models import Application, AccessToken, RefreshToken
    from datetime import datetime, timedelta
    
    # Get or create application
    app, created = Application.objects.get_or_create(
        client_id=settings.OAUTH2_INFO['client_id'],
        defaults={
            'client_secret': settings.OAUTH2_INFO['client_secret'],
            'user': user,
            'client_type': 'confidential',
            'authorization_grant_type': 'password',
            'name': 'OUPharmacy App'
        }
    )
    
    # Create access token
    token = AccessToken.objects.create(
        user=user,
        application=app,
        expires=datetime.now() + timedelta(days=30),
        token=''.join(random.choices(string.ascii_letters + string.digits, k=40)),
        scope='read write'
    )
    
    # Create refresh token
    refresh_token = RefreshToken.objects.create(
        user=user,
        application=app,
        token=''.join(random.choices(string.ascii_letters + string.digits, k=40))
    )
    
    token.refresh_token = refresh_token
    token.save()
    
    return token