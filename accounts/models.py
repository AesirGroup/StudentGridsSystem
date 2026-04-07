from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings

# Create your models here.

class Faculty(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True)
    
    class Meta:
        verbose_name_plural = "Faculties"

    def __str__(self):
        return f"{self.name} ({self.code})"

class CustomUser(AbstractUser):
    # 1. Multi-Faculty Access
    faculties = models.ManyToManyField(
        Faculty, 
        blank=True, 
        related_name="advisors",
        help_text="Select the faculties this advisor is authorized to view."
    )
    
    # 2. The Audit Trail
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="approved_accounts",
        help_text="The administrator who activated this account."
    )
    approved_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When this account was activated."
    )