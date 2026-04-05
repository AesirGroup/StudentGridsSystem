from django.contrib.auth.forms import UserCreationForm, UserChangeForm, PasswordResetForm
from django.template.loader import render_to_string
from django.conf import settings
from django_q.tasks import async_task
from .models import CustomUser
from .tasks import send_async_email


class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = (
            "username",
            "email",
        )


class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = CustomUser
        fields = (
            "username",
            "email",
        )


class AsyncPasswordResetForm(PasswordResetForm):
    """
    Overrides Django's default PasswordResetForm to dispatch the
    reset email through Django-Q2's background task queue instead
    of sending it synchronously during the request cycle.
    """

    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        # Render the subject and body from Django's built-in templates
        subject = render_to_string(subject_template_name, context)
        subject = "".join(subject.splitlines())  # Remove newlines
        body = render_to_string(email_template_name, context)

        html_email = None
        if html_email_template_name:
            html_email = render_to_string(html_email_template_name, context)

        # Dispatch to the database queue instead of sending immediately
        async_task(
            send_async_email,
            subject=subject,
            message=body,
            from_email=from_email or settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            html_message=html_email,
            task_name=f"password_reset_{to_email}",
        )
