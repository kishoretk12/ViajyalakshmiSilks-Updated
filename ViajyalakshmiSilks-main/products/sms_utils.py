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
        if not getattr(settings, "ENABLE_SMS", False):
            logger.debug("ENABLE_SMS is False; not sending SMS.")
            return False

        sid = getattr(settings, "TWILIO_ACCOUNT_SID", None)
        token = getattr(settings, "TWILIO_AUTH_TOKEN", None)
        from_num = getattr(settings, "TWILIO_PHONE_NUMBER", None)

        if not (sid and token and from_num):
            logger.error("Twilio credentials missing in settings; cannot send SMS.")
            return False

        from twilio.rest import Client
        client = Client(sid, token)
        msg = client.messages.create(body=message, from_=from_num, to=to_phone)
        logger.info("Twilio SMS sent to %s sid=%s", to_phone, getattr(msg, 'sid', None))
        return True
    except Exception as e:
        logger.exception("Twilio send_sms failed: %s", e)
        return False
