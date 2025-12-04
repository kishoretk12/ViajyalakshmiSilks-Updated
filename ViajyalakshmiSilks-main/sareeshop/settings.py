import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

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

# EMAIL_HOST_USER = 'kishore.kumar0728@gmail.com'  # Replace with your Gmail
# EMAIL_HOST_PASSWORD = 'ixtb jmws rxah sybe'  # Replace with Gmail App Password
# DEFAULT_FROM_EMAIL = 'kishore.kumar0728@gmail.com'  # Replace with your Gmail
# # Admin Email for notifications
# ADMIN_EMAIL = 'vijayalakshmisilks96@gmail.com'  # Replace with admin email

TWILIO_ACCOUNT_SID = "AC942785d49b5b5f843b5dc62a15eceadc"
TWILIO_AUTH_TOKEN = "0f7796c4fc7c983e77ca52c731631c92"
TWILIO_PHONE_NUMBER = "+13203226780"  # Your Twilio number
ADMIN_PHONE_NUMBER = "+919791579731"  # Your number


# Setup Gmail App Password:
# Enable 2-Factor Authentication on your Gmail account
# Go to: https://myaccount.google.com/apppasswords
# Generate an App Password for "Mail"
# Use this App Password (not your regular Gmail password)
