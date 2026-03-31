from django.urls import path
from .views import UploadGridView, StudentDetailView

urlpatterns = [
    path('upload/', UploadGridView.as_view(), name='upload_grid'),
    path('<str:student_number>/', StudentDetailView.as_view(), name='student_detail'),
]