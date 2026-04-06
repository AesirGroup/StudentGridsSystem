from django.urls import path
from .views import UploadGridView, StudentDetailView, ExtractTextChunkView, StudentPortalView, EphemeralEvaluationView, ToggleFLRExemptionView
from .views import ReportView, ReportStudentsView, StudentReportDataView

urlpatterns = [
    path('upload/', UploadGridView.as_view(), name='upload_grid'),
    path('api/extract-chunk/', ExtractTextChunkView.as_view(), name='extract_chunk'),
    path('api/evaluate-ephemeral/', EphemeralEvaluationView.as_view(), name='evaluate_ephemeral'),
    path('portal/', StudentPortalView.as_view(), name='student_portal'),
    path('<str:student_number>/toggle-flr/', ToggleFLRExemptionView.as_view(), name='toggle_flr_exemption'),
    path('<str:student_number>/', StudentDetailView.as_view(), name='student_detail'),
     path('report/', ReportView.as_view(), name='report'),
    path('api/report-students/', ReportStudentsView.as_view(), name='report_students'),
    path('api/student-report-data/<int:student_number>/', StudentReportDataView.as_view(), name='student_report_data'),
]