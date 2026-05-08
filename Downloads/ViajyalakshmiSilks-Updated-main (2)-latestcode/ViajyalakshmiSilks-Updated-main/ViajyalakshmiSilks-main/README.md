# Vijayalakshmi Silks E-commerce Platform

A premium e-commerce platform for silk sarees, featuring real-time payment integration, SMS/Email notifications, and an automated order tracking system.

---

## 🚀 Quick Start (Local Development)

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment**:
   Create/Edit a `.env` file in the root directory (see **Environment Variables** section below).

3. **Initialize Database**:
   ```bash
   python manage.py migrate
   ```

4. **Run Server**:
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```
   *Access at: http://localhost:8000 or http://your-local-ip:8000*

---

## 🛠 Features

### 1. Checkout & Payments
- **Razorpay Integration**: Native Indian payment gateway support.
- **Stripe Integration**: International card payment support.
- **Cash on Delivery (COD)**: Custom flow for local orders.

### 2. Notifications System
- **SMS Confirmation**: Automatic SMS sent via Twilio to customers and admins upon order placement.
- **Email Receipts**: Professional HTML emails sent via Gmail SMTP with a "Track Your Order" button.
- **Order Tracking**: Every notification includes a unique link directly to the order's status page.

### 3. Account Portal
- **Customer Profile**: Users can update their Full Name and Mobile Number.
- **Order History**: Comprehensive list of past orders with status tracking.
- **Address Management**: Save and manage multiple delivery addresses.

### 4. Admin Dashboard (Jazzmin)
- **Luxury UI**: Powered by Jazzmin for a premium management experience.
- **Real-time Stats**: View orders, manage stock, and update site settings dynamically.

---

## 🌍 Deployment Guide (AWS)

This project is pre-configured for AWS production environments.

### 1. Database (Amazon RDS)
To use RDS, simply provide the following environment variables. The system will automatically switch to PostgreSQL:
- `DB_HOST`: Your RDS endpoint.
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`.

### 2. File Storage (Amazon S3)
To host media and static files on S3:
- Provide `AWS_STORAGE_BUCKET_NAME`, `AWS_ACCESS_KEY_ID`, and `AWS_SECRET_ACCESS_KEY`.
- The system will automatically serve all images and videos from your bucket.

### 3. Production Hosting
- **Gunicorn**: The included `Procfile` is ready for Elastic Beanstalk or App Runner.
- **Security**: Set `DJANGO_DEBUG=False` to automatically enable SSL redirects and HSTS security headers.

---

## 📋 Environment Variables (.env)

| Variable | Description |
| :--- | :--- |
| `SITE_URL` | The base URL of your site (e.g., https://vijayalakshmisilk.in) |
| `EMAIL_HOST_USER` | Gmail address for sending receipts |
| `EMAIL_HOST_PASSWORD` | Gmail App Password (16 characters) |
| `TWILIO_ACCOUNT_SID` | Twilio API SID |
| `TWILIO_AUTH_TOKEN` | Twilio API Secret |
| `RAZORPAY_KEY_ID` | Razorpay API Key |
| `STRIPE_SECRET_KEY` | Stripe API Secret |

---

## ⚠️ Troubleshooting

- **Email not sending?**: Check if your Gmail App Password is correct and ensure `.env` has no hidden characters.
- **Mobile device can't access?**: Ensure the device is on the same Wi-Fi and your PC's IP is added to `ALLOWED_HOSTS` in `.env`.
- **"Broken Pipe" errors?**: These are normal during local development when a browser tab is closed suddenly; they don't affect production.

---

*© 2026 Vijayalakshmi Silks. Developed for premium performance.*
