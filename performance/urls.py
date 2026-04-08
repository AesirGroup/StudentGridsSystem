from django.urls import path
from .views import (
    UploadGridView,
    StudentDetailView,
    ExtractTextChunkView,
    StudentPortalView,
    EphemeralEvaluationView,
    ToggleFLRExemptionView,
)
from .views import TranscriptGridView, TranscriptStudentDetailView
from .views import ReportView, ReportStudentsView, StudentReportDataView


urlpatterns = [
    # --- WORKING BASE ROUTES ---
    path('upload/', UploadGridView.as_view(), name='upload_grid'),
    path('api/extract-chunk/', ExtractTextChunkView.as_view(), name='extract_chunk'),
    path('api/evaluate-ephemeral/', EphemeralEvaluationView.as_view(), name='evaluate_ephemeral'),
    path('portal/', StudentPortalView.as_view(), name='student_portal'),

    # --- REPORT ROUTES ---
    path('report/', ReportView.as_view(), name='report'),
    path('api/report-students/', ReportStudentsView.as_view(), name='report_students'),
    path('api/student-report-data/<int:student_number>/', StudentReportDataView.as_view(), name='student_report_data'),

    # --- NO-DB PREVIEW ROUTES ---
    path('transcript/', TranscriptGridView.as_view(), name='transcript_grid'),
    path('transcript/<int:student_number>/', TranscriptStudentDetailView.as_view(), name='transcript_student_detail'),

    # --- STUDENT ACTIONS ---
    path('<int:student_number>/toggle-flr/', ToggleFLRExemptionView.as_view(), name='toggle_flr_exemption'),

    # MUST BE LAST
    path('<int:student_number>/', StudentDetailView.as_view(), name='student_detail'),
]