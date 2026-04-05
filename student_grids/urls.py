"""
URL configuration for student_grids project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
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
from django.urls import path, include
from django.contrib.auth import views as auth_views

from accounts.forms import AsyncPasswordResetForm
from accounts.decorators import ratelimit


# Rate-limited, async password reset view.
# Limits a single IP to 5 reset requests per hour.
rate_limited_reset = ratelimit(key="ip", rate="5/h", block=True)(
    auth_views.PasswordResetView.as_view(form_class=AsyncPasswordResetForm)
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    # Override the default password_reset BEFORE including auth.urls
    path("accounts/password_reset/", rate_limited_reset, name="password_reset"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("pages.urls")),
    path("performance/", include("performance.urls")),
]

