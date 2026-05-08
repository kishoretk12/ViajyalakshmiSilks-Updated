# products/sms_utils.py
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

def send_sms(to_phone: str, message: str):
    """
    Simple Twilio wrapper. Reads credentials from settings.
    Returns True on success, False on failure.
    """
    try:
        from products.models import SiteSettings
        settings_db = SiteSettings.load()
        if not settings_db.enable_sms_notifications and not getattr(settings, "ENABLE_SMS", False):
            logger.debug("SMS is disabled in Site Settings and .env; not sending SMS.")
            return False

        sid = settings_db.twilio_account_sid or getattr(settings, "TWILIO_ACCOUNT_SID", None)
        token = settings_db.twilio_auth_token or getattr(settings, "TWILIO_AUTH_TOKEN", None)
        from_num = settings_db.twilio_phone_number or getattr(settings, "TWILIO_PHONE_NUMBER", None)

        if not (sid and token and from_num):
            logger.error("Twilio credentials missing in settings; cannot send SMS.")
            return False

        from twilio.rest import Client
        client = Client(sid, token)

        # Ensure phone number has a country code (default to +91 for India if missing)
        clean_phone = to_phone.strip().replace(" ", "")
        if not clean_phone.startswith('+'):
            if len(clean_phone) == 10:
                clean_phone = f"+91{clean_phone}"
            else:
                # Keep as is, Twilio might still handle it if it's a US number etc.
                pass

        msg = client.messages.create(body=message, from_=from_num, to=clean_phone)
        logger.info("Twilio SMS sent to %s (formatted as %s) sid=%s", to_phone, clean_phone, getattr(msg, 'sid', None))
        return True
    except Exception as e:
        logger.exception("Twilio send_sms failed: %s", e)
        return False
