from django.core.mail import send_mail
import logging

logger = logging.getLogger(__name__)


def send_async_email(subject, message, from_email, recipient_list, html_message=None):
    """
    Sends an email using whatever backend is configured in settings.
    Called asynchronously via Django-Q2's async_task().
    In DEBUG mode → console backend prints to terminal.
    In production → Anymail/Resend sends a real email.
    """
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=recipient_list,
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(f"Successfully sent async email to {recipient_list}")
    except Exception as e:
        logger.error(f"Failed to send async email to {recipient_list}: {e}")
        raise  # Django-Q2 will retry based on max_attempts
