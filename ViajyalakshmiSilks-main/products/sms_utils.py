# products/sms_utils.py
import logging
from twilio.rest import Client
from django.conf import settings

logger = logging.getLogger(__name__)

def _twilio_client():
    """Return a Twilio client or raise ValueError if creds missing."""
    sid = getattr(settings, "TWILIO_ACCOUNT_SID", None)
    token = getattr(settings, "TWILIO_AUTH_TOKEN", None)
    if not sid or not token:
        raise ValueError("Twilio credentials not configured in settings.")
    return Client(sid, token)

def send_sms(to_phone: str, message: str, from_phone: str = None) -> bool:
    """
    Send SMS using Twilio.
    Returns True on success, False on failure (logged).
    """
    try:
        client = _twilio_client()
        from_number = from_phone or getattr(settings, "TWILIO_PHONE_NUMBER", None)
        if not from_number:
            raise ValueError("TWILIO_PHONE_NUMBER not configured in settings.")

        # Ensure phone numbers are strings
        to_phone = str(to_phone)
        from_number = str(from_number)

        msg = client.messages.create(
            body=message,
            from_=from_number,
            to=to_phone
        )
        logger.info("Sent SMS to %s (sid=%s)", to_phone, getattr(msg, 'sid', 'n/a'))
        return True
    except ValueError as ve:
        logger.error("SMS config error: %s", ve)
        return False
    except Exception as e:
        # Twilio errors typically include HTTP status and message
        logger.exception("Failed to send SMS to %s: %s", to_phone, e)
        return False
