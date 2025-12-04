# products/sms_utils.py
import time
import logging
from typing import Optional
from twilio.rest import Client
from django.conf import settings

logger = logging.getLogger(__name__)

def send_sms(to_phone: str, message: str, retries: int = 3, backoff: float = 1.0) -> bool:
    """
    Send SMS via Twilio. Retries a few times on failure.
    Returns True if sent (Twilio accepted), False otherwise.
    """
    if not all([settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_PHONE_NUMBER]):
        logger.error("Twilio credentials missing in settings; SMS not sent.")
        return False

    # Normalize phone (Twilio needs full +<country> format)
    to_phone = to_phone.strip()
    if not to_phone.startswith("+"):
        logger.warning("send_sms: phone does not start with '+': %s", to_phone)

    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

    attempt = 0
    while attempt < retries:
        try:
            attempt += 1
            msg = client.messages.create(
                body=message,
                from_=settings.TWILIO_PHONE_NUMBER,
                to=to_phone
            )
            logger.info("SMS sent (sid=%s) to %s", getattr(msg, 'sid', '<no-sid>'), to_phone)
            return True
        except Exception as e:
            logger.error("Twilio SMS attempt %d/%d failed for %s: %s", attempt, retries, to_phone, e)
            if attempt >= retries:
                break
            time.sleep(backoff * attempt)
    return False
