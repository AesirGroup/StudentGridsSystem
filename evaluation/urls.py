from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),  # root endpoint is dashboard
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path("grid/", views.upload_grid, name="upload_grid"),
    path("grid/<str:student_number>/", views.student_detail, name="student_detail"),
]