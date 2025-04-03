"""
Django settings for OUPharmacyManagementApp project.

Generated by 'django-admin startproject' using Django 4.0.2.

For more information on this file, see
https://docs.djangoproject.com/en/4.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.0/ref/settings/
"""

from pathlib import Path

import cloudinary
import cloudinary.uploader
import cloudinary.api
import os

from decouple import config, Csv, Config, RepositoryEnv
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials

from OUPharmacyManagementApp.firebase_config import initialize_firebase

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY')

# DEBUG MODE ; SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True  # Always True for development
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']
INTERNAL_IPS = [
    '127.0.0.1'
]
CORS_ALLOW_ALL_ORIGINS = True

# Application definition
CSRF_TRUSTED_ORIGINS = [
    'https://oupharmacy-vominhhung.up.railway.app'
]

# 'debug_toolbar',
INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'mainApp.apps.MainappConfig',
    'ckeditor',
    'ckeditor_uploader',
    'rest_framework',
    'oauth2_provider',
    'drf_yasg',
    'corsheaders',
    'cloudinary',
    'django_celery_beat',
    'django_filters',
    'django_crontab',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # 'debug_toolbar.middleware.DebugToolbarMiddleware',
    'corsheaders.middleware.CorsMiddleware',
]

ROOT_URLCONF = 'OUPharmacyManagementApp.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'mainApp/templates/')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'OUPharmacyManagementApp.wsgi.application'

REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    # authentication
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'oauth2_provider.contrib.rest_framework.OAuth2Authentication',
    )
}

import pymysql

pymysql.install_as_MySQLdb()

# Database
# https://docs.djangoproject.com/en/4.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': os.getenv('DB_MYSQL_ENGINE'),
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_MYSQL_USER'),
        'PASSWORD': os.getenv('DB_MYSQL_PASSWORD'),
        'HOST': os.getenv('DB_HOST'),
        'PORT': os.getenv('DB_MYSQL_PORT')
    }
}

# Password validation
# https://docs.djangoproject.com/en/4.0/ref/settings/#auth-password-validators


AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/4.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

# TIMEZONE SETTING HERE
# READ DATA : UTC (-7H) ; WRITE DATA : UTC (OKE)

# ValueError at /admin/django_celery_beat/periodictask/ (USE_TZ=TRUE)
USE_TZ = True
TIME_ZONE = 'Asia/Bangkok'
USE_I18N = True

ADMIN_INDEX_TEMPLATE = 'admin/dashboard.html'
# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.0/howto/static-files/


STATICFILES_DIRS = [os.path.join(BASE_DIR, "mainApp", "static")]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

STATIC_URL = 'static/'

AUTH_USER_MODEL = 'mainApp.User'
MEDIA_ROOT = '%s/mainApp/static/' % BASE_DIR
CKEDITOR_UPLOAD_PATH = 'post/'


OAUTH2_INFO = {
    "client_id": "ynFBpu3oh7wJEWh1u74xrjUIFK2JswGQSidmegoH",
    "client_secret": "KzWfvl5U9B40IRATHNJXXO5S26RUQOXpec5o3jtam1SWB5gVfjTFDexVqeZQTlMv9hBsTeLp7xUrqv6n7iAanDVziwDvBKfUxlfJKwuoBOWDhjDD5NB6QQFyDyOnnxqq"
}

OAUTH2_PROVIDER = {
    'OAUTH2_BACKEND_CLASS': 'oauth2_provider.oauth2_backends.JSONOAuthLibCore',
    # TOKEN wws expired IN 30 days,
    'ACCESS_TOKEN_EXPIRE_SECONDS': 2592000,

}


# CLOUDINARY FOLDER UPLOADED
# MEDIA_URL = '/OUPharmacy/'
# DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'

cloudinary.config(
    cloud_name="dl6artkyb",
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_HOST_USER = "oupharmacymanagement@gmail.com"
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')  
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER


CELERY_BROKER_URL = "redis://default:12ru4X3ZiUglwwjxjqfVTLOHVCYy9IPe@redis-17968.c265.us-east-1-2.ec2.cloud.redislabs.com:17968/0"
CELERY_RESULT_BACKEND = "redis://default:12ru4X3ZiUglwwjxjqfVTLOHVCYy9IPe@redis-17968.c265.us-east-1-2.ec2.cloud.redislabs.com:17968/0"
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
DJANGO_CELERY_BEAT_TZ_AWARE = True
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TIMEZONE = 'Asia/Bangkok'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'



# FIREBASE
# Initialize Firebase when Django starts
initialize_firebase()

# Default primary key field type
# https://docs.djangoproject.com/en/4.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# JAZZMIN SETTING
JAZZMIN_SETTINGS = {
    # title of the window (Will default to current_admin_site.site_title if absent or None)
    "site_title": "OUPharmacy",

    # Title on the login screen (19 chars max) (defaults to current_admin_site.site_header if absent or None)
    "site_header": "OUPharmacy",

    # Title on the brand (19 chars max) (defaults to current_admin_site.site_header if absent or None)
    "site_brand": "OUPharmacy",

    # Logo to use for your site, must be present in static files, used for brand on top left
    "site_logo": "logo/logo_oupharmacy_1x1w.png",

    # CSS classes that are applied to the logo above
    "site_logo_classes": "img-rounded",

    # Relative path to a favicon for your site, will default to site_logo if absent (ideally 32x32 px)
    "site_icon": "logo/logo_oupharmacy_1x1w.png",

    # Welcome text on the login screen
    "welcome_sign": "Welcome to the OUPharmacy management.",

    # Copyright on the footer
    "copyright": "VO MINH HUNG",

    # The model admin to search from the search bar, search bar omitted if excluded
    "search_model": "mainApp.User",

    # Field name on user model that contains avatar ImageField/URLField/Charfield or a callable that receives the user
    "user_avatar": None,

    ############
    # Top Menu #
    ############

    # Links to put along the top menu
    "topmenu_links": [

        # Url that gets reversed (Permissions can be added)
        {"name": "Home", "url": "admin:index", "permissions": ["auth.view_user"]},

        # external url that opens in a new window (Permissions can be added)
        {"name": "Support", "url": "https://github.com/VoMinhHung-SR/OUPharmacyManagement", "new_window": True},

        # model admin to link to (Permissions checked against model)
        {"model": "auth.User"},

        # App with dropdown menu to all its models pages (Permissions checked against models)
        {"app": "books"},
    ],

    #############
    # User Menu #
    #############

    # Additional links to include in the user menu on the top right ("app" url type is not allowed)
    "usermenu_links": [
        {"name": "Support", "url": "https://github.com/VoMinhHung-SR/OUPharmacyManagement", "new_window": True,
         "icon": "fas fa-life-ring"},
        {"model": "auth.user"}
    ],

    #############
    # Side Menu #
    #############

    # Whether to display the side menu
    "show_sidebar": True,

    # Whether to aut expand the menu
    "navigation_expanded": True,

    # Hide these apps when generating side menu e.g (auth)
    "hide_apps": [],

    # Hide these models when generating side menu (e.g auth.user)
    "hide_models": [],

    # List of apps (and/or models) to base side menu ordering off of (does not need to contain all apps/models)

    # Custom links to append to app groups, keyed on app name
    "custom_links": {
        "stats": [{
            "name": "Statistics",
            "url": "stats",
            "icon": "fas fa-chart-bar",
            "permissions": [],  # Remove any existing permissions
            "condition": lambda user: user.is_superuser,  # Add a condition for superuser
        }]
    },
    'default_dashboard': 'admin/stats.html',
    # Custom icons for side menu apps/models See
    # https://fontawesome.com/icons?d=gallery&m=free&v=5.0.0,5.0.1,5.0.10,5.0.11,5.0.12,5.0.13,5.0.2,5.0.3,5.0.4,5.0.5,5.0.6,5.0.7,5.0.8,5.0.9,5.1.0,5.1.1,5.2.0,5.3.0,5.3.1,5.4.0,5.4.1,5.4.2,5.13.0,5.12.0,5.11.2,5.11.1,5.10.0,5.9.0,5.8.2,5.8.1,5.7.2,5.7.1,5.7.0,5.6.3,5.5.0,5.4.2
    # for the full list of 5.13.0 free icon classes
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.Group": "fas fa-users",
        "mainApp.User": "fas fa-user",
        "mainApp.Patient": "fas fa-user",
    },
    # Icons that are used when one is not manually specified
    "default_icon_parents": "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-circle",
    #################
    # Related Modal #
    #################
    # Use modals instead of popups
    "related_modal_active": True,

    #############
    # UI Tweaks #
    #############
    # Relative paths to custom CSS/JS scripts (must be present in static files)
    "custom_css": "jazzmin/custom.css",
    "custom_js": None,
    # Whether to show the UI customizer on the sidebar
    "show_ui_builder": False,

    ###############
    # Change view #
    ###############
    # Render out the change view as a single form, or in tabs, current options are
    # - single
    # - horizontal_tabs (default)
    # - vertical_tabs
    # - collapsible
    # - carousel
    "changeform_format": "horizontal_tabs",
    # override change forms on a per modeladmin basis
    "language_chooser": False,
}
