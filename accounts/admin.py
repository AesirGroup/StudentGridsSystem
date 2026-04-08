from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils import timezone

from .forms import CustomUserCreationForm, CustomUserChangeForm
from .models import CustomUser, Faculty


@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    list_display = ('code', 'name')


class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = CustomUser

    list_display = ("username", "email", "first_name", "last_name", "is_active", "get_faculties", "approved_by", "approved_at")
    list_filter = ("is_active", "faculties", "is_staff")
    
    readonly_fields = ('approved_by', 'approved_at')

    fieldsets = UserAdmin.fieldsets + (
        ('UWI Authorization', {
            'fields': ('faculties',),
        }),
        ('Audit Trail', {
            'fields': ('approved_by', 'approved_at'),
            'classes': ('collapse',)
        }),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "password1", "password2"),
            },
        ),
        (
            'UWI Authorization', {
                'fields': ('faculties',),
            }
        ),
    )

    filter_horizontal = ('faculties', 'groups', 'user_permissions')

    def get_faculties(self, obj):
        return ", ".join([f.code for f in obj.faculties.all()])
    get_faculties.short_description = 'Faculties'

    def save_model(self, request, obj, form, change):
        if change:
            old_obj = CustomUser.objects.get(pk=obj.pk)
            if obj.is_active and not old_obj.is_active:
                obj.approved_by = request.user
                obj.approved_at = timezone.now()
        
        super().save_model(request, obj, form, change)


admin.site.register(CustomUser, CustomUserAdmin)