from django.urls import path
from .views import UploadGridView, StudentDetailView, ToggleFLRExemptionView

urlpatterns = [
    path('upload/', UploadGridView.as_view(), name='upload_grid'),
    path('<str:student_number>/toggle-flr/', ToggleFLRExemptionView.as_view(), name='toggle_flr_exemption'),
    path('<str:student_number>/', StudentDetailView.as_view(), name='student_detail'),
]