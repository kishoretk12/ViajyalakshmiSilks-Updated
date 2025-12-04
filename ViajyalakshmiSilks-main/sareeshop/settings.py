import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# load .env (only used for Twilio / any env vars you put there)
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = 'django-insecure-key'
DEBUG = True
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'products',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'sareeshop.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {'context_processors': [
            'django.template.context_processors.debug',
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages',
            'products.context_processors.cart_context',
        ]},
    },
]

WSGI_APPLICATION = 'sareeshop.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'  # Indian Standard Time (IST)
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Razorpay (kept in settings as you requested)
RAZORPAY_KEY_ID = "rzp_live_7nFW0TaEJ03VGZ"
RAZORPAY_KEY_SECRET = "QHtzHfWHWQB56SDnUwgkZZlE"

# Authentication Settings
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

# Email Settings (Gmail SMTP - Free)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'kishore.kumar0728@gmail.com'  # Replace with your Gmail
EMAIL_HOST_PASSWORD = 'ixtb jmws rxah sybe'  # Replace with Gmail App Password
DEFAULT_FROM_EMAIL = 'kishore.kumar0728@gmail.com'  # Replace with your Gmail
# Admin Email for notifications
ADMIN_EMAIL = 'kishore.kumar0728@gmail.com'  # Replace with admin email

# Twilio - read from .env (you said you'll use .env only for Twilio)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")

# Admin phone for SMS notifications (fallback if not in .env)
ADMIN_PHONE = os.getenv("ADMIN_PHONE", "+919791579731")

# Setup Gmail App Password:
# Enable 2-Factor Authentication on your Gmail account
# Go to: https://myaccount.google.com/apppasswords
# Generate an App Password for "Mail"
# Use this App Password (not your regular Gmail password)
