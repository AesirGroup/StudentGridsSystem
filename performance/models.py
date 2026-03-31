from django.db import models


class StudentProfile(models.Model):
    """Stores the static identity of the student."""

    student_number = models.CharField(max_length=20, primary_key=True)
    name = models.CharField(max_length=255)
    programme = models.CharField(max_length=255, blank=True, default="")
    major = models.CharField(max_length=255, blank=True, default="")
    overall_gpa = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.student_number})"


class AuditRecord(models.Model):
    """Represents an immutable single run of the evaluation engine."""

    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="audits"
    )
    audit_date = models.DateTimeField(auto_now_add=True)

    # Context Preservation: What were they studying on the day this was run?
    evaluated_programme = models.CharField(max_length=255, blank=True, default="")
    evaluated_major = models.CharField(max_length=255, blank=True, default="")

    can_graduate = models.BooleanField(default=False)
    total_credits_earned = models.FloatField(default=0.0)
    total_credits_required = models.FloatField(default=0.0)
    overall_progress = models.CharField(max_length=255, blank=True, default="")

    # Store the engine's list outputs natively
    unmet_requirements_json = models.JSONField(default=list)
    next_steps_json = models.JSONField(default=list)

    def __str__(self):
        return f"Audit for {self.student.student_number} on {self.audit_date.strftime('%Y-%m-%d')}"


class BucketResult(models.Model):
    """Stores the specific pass/fail state of an individual requirement bucket."""

    audit = models.ForeignKey(
        AuditRecord, on_delete=models.CASCADE, related_name="bucket_results"
    )

    # E.g., "Computer Science" or "General Requirements"
    component_name = models.CharField(max_length=255, default="General")
    bucket_name = models.CharField(max_length=255)

    is_met = models.BooleanField(default=False)
    credits_earned = models.FloatField(default=0.0)
    credits_required = models.FloatField(default=0.0)
    is_all_required = models.BooleanField(default=False)

    # Store the exact courses they took, and what they still need
    courses_completed_json = models.JSONField(default=list)
    courses_needed_json = models.JSONField(default=list)

    def __str__(self):
        return f"{self.bucket_name}: {'MET' if self.is_met else 'UNMET'}"
