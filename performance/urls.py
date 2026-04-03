from django.urls import path
from .views import UploadGridView, StudentDetailView, ExtractTextChunkView, StudentPortalView, EphemeralEvaluationView

urlpatterns = [
    path('upload/', UploadGridView.as_view(), name='upload_grid'),
    path('api/extract-chunk/', ExtractTextChunkView.as_view(), name='extract_chunk'),
    path('api/evaluate-ephemeral/', EphemeralEvaluationView.as_view(), name='evaluate_ephemeral'),
    path('portal/', StudentPortalView.as_view(), name='student_portal'),
    path('<str:student_number>/', StudentDetailView.as_view(), name='student_detail'),
]