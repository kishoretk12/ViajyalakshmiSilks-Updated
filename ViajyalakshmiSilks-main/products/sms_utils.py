from twilio.rest import Client
from django.conf import settings

def send_sms(to_phone, message):
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=message,
            from_=settings.TWILIO_PHONE_NUMBER,
            to=to_phone
        )
        return True
    except Exception as e:
        print("SMS Error:", e)
        return False
