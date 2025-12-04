# sms_utils.py
import logging
from twilio.rest import Client
from django.conf import settings

logger = logging.getLogger(__name__)

def _normalize_phone(phone):
    if not phone:
        return phone
    phone = phone.strip()
    # if local 10-digit Indian number provided, prefix +91
    digits = ''.join(ch for ch in phone if ch.isdigit())
    if len(digits) == 10:
        return f"+91{digits}"
    if phone.startswith('+'):
        return phone
    if len(digits) >= 11:
        return f"+{digits}"
    return phone

def send_sms(to_phone, message):
    try:
        sid = getattr(settings, 'TWILIO_ACCOUNT_SID', None)
        token = getattr(settings, 'TWILIO_AUTH_TOKEN', None)
        from_number = getattr(settings, 'TWILIO_PHONE_NUMBER', None)

        if not (sid and token and from_number):
            logger.error("Twilio settings missing. SMS not sent.")
            return False

        client = Client(sid, token)
        to_phone = _normalize_phone(to_phone)
        if not to_phone:
            logger.error("Invalid recipient phone number.")
            return False

        client.messages.create(
            body=message,
            from_=from_number,
            to=to_phone
        )
        logger.info("SMS sent to %s", to_phone)
        return True
    except Exception as e:
        logger.exception("SMS Error: %s", e)
        return False
