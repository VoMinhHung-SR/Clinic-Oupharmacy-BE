from django.urls import path, include, re_path
import debug_toolbar
import os
from django.conf import settings

urlpatterns = [
    path('', include('mainApp.urls')),
    re_path(r'^ckeditor/', include('ckeditor_uploader.urls')),
    re_path(r'^ckeditor/', include('ckeditor_uploader.urls')),
    path('__debug__/', include(debug_toolbar.urls)),
]