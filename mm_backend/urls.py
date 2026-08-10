"""
URL configuration for mm_backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from django.http import HttpResponse


def testfunc(request):
    return HttpResponse("this is a test api")

urlpatterns = [
    path('admin/', admin.site.urls),
    path('',testfunc,name='test'),
    path('api/v1/auth/', include('AuthManagement.urls')),
    path('api/v1/mess/', include('MessManagement.urls')),
    path('api/v1/notice/', include('MessManagement.notice_urls')),
    path('api/v1/cost/', include('CostManagement.urls')),
    path('api/v1/meal/', include('MealManagement.urls')),
    path('api/v1/fund/', include('FundManagement.urls')),
    path('api/v1/deposit/', include('DepositManagement.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
