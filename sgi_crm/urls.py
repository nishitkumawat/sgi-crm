"""
URL configuration for SGI-CRM project.
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('sgi_erp/', include('SGIERP.urls')),
    path('', include('SGIERP.urls')),
]
