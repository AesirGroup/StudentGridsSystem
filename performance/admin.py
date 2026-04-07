from django.contrib import admin
from .models import StudentProfile, AuditRecord, BucketResult

@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ('student_number', 'name', 'programme', 'flr_exempt_verified', 'created_at')
    search_fields = ('student_number', 'name', 'programme')
    list_filter = ('flr_exempt_verified', 'programme', 'major')

@admin.register(AuditRecord)
class AuditRecordAdmin(admin.ModelAdmin):
    list_display = ('student', 'audit_date', 'can_graduate', 'total_credits_earned')
    search_fields = ('student__student_number', 'student__name')
    list_filter = ('can_graduate', 'audit_date')
    readonly_fields = ('audit_date',)

@admin.register(BucketResult)
class BucketResultAdmin(admin.ModelAdmin):
    list_display = ('audit', 'component_name', 'bucket_name', 'is_met')
    search_fields = ('audit__student__student_number', 'bucket_name')
    list_filter = ('is_met', 'component_name')
