import logging
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

logger = logging.getLogger(__name__)

def send_html_email(subject, to_email, template_name, context, reply_to=None):
    from django.core.mail import EmailMultiAlternatives, get_connection
    from django.template.loader import render_to_string
    from django.utils.html import strip_tags
    from django.conf import settings
    from dotenv import load_dotenv
    import os

    # Force reload .env to get the latest SMTP credentials from the dashboard
    env_path = os.path.join(settings.BASE_DIR, '.env')
    load_dotenv(env_path, override=True)

    host = os.environ.get('EMAIL_HOST', settings.EMAIL_HOST)
    port = os.environ.get('EMAIL_PORT', settings.EMAIL_PORT)
    user = os.environ.get('EMAIL_HOST_USER', settings.EMAIL_HOST_USER)
    password = os.environ.get('EMAIL_HOST_PASSWORD', settings.EMAIL_HOST_PASSWORD)
    use_tls = os.environ.get('EMAIL_USE_TLS', str(settings.EMAIL_USE_TLS)).lower() == 'true'

    # Create a fresh connection with the latest credentials
    connection = get_connection(
        host=host,
        port=port,
        username=user,
        password=password,
        use_tls=use_tls
    )

    html_content = render_to_string(template_name, context)
    text_content = strip_tags(html_content)
    
    from_email = user  # Always send from the authenticated user

    msg = EmailMultiAlternatives(subject, text_content, from_email, [to_email], connection=connection)
    msg.attach_alternative(html_content, "text/html")
    
    if reply_to:
        msg.reply_to = [reply_to]
        
    try:
        msg.send()
        return True
    except Exception as e:
        return False


def send_customer_receipt(order, payment_info, base_url=None):
    from products.models import SiteSettings
    site_settings = SiteSettings.load()
    
    if not base_url:
        base_url = getattr(settings, 'SITE_URL', 'https://vijayalakshmisilk.in')
    
    customer = order.user
    addr = order.delivery_address
    
    if not customer or not customer.email:
        logger.warning(f"Skipping customer receipt for order {order.id}: No customer email.")
        return

    context = {
        "customer_name": customer.get_full_name() or customer.username,
        "order_id": order.id,
        "order_link": f"{base_url.rstrip('/')}/order/{order.id}/",
        "payment_id": payment_info.get("id", ""),
        "amount": order.amount,
        "payment_method": payment_info.get("method", "Online"),
        "payment_status": payment_info.get("status", "success"),
        "full_name": addr.full_name if addr else "Customer",
        "address_line_1": addr.address_line_1 if addr else "",
        "address_line_2": addr.address_line_2 if addr else "",
        "city": addr.city if addr else "",
        "state": addr.state if addr else "",
        "pincode": addr.pincode if addr else "",
        "phone": addr.phone if addr else "",
        "items": [{
            "name": order.saree.name,
            "qty": order.quantity or 1,
            "price": order.amount
        }],
        "site_settings": site_settings
    }

    send_html_email(
        f"Order Receipt - #{order.id}",
        customer.email,
        "email_templates/customer_receipt.html",
        context,
        reply_to=site_settings.email
    )


def send_admin_order_email(orders):
    if not orders:
        return
        
    from products.models import SiteSettings
    site_settings = SiteSettings.load()
    
    first = orders[0]
    addr = first.delivery_address

    items = [{
        "name": o.saree.name,
        "qty": o.quantity or 1,
        "price": o.amount,
    } for o in orders]

    context = {
        "order_id": first.id,
        "full_name": addr.full_name if addr else "N/A",
        "phone": addr.phone if addr else "N/A",
        "address_line_1": addr.address_line_1 if addr else "N/A",
        "address_line_2": addr.address_line_2 if addr else "",
        "city": addr.city if addr else "",
        "state": addr.state if addr else "",
        "pincode": addr.pincode if addr else "",
        "items": items,
        "total": sum(o.amount for o in orders),
        "site_settings": site_settings
    }

    # Collect all admin/staff emails to notify
    from django.contrib.auth.models import User
    admin_emails = list(User.objects.filter(is_staff=True).exclude(email='').values_list('email', flat=True))
    
    # Also include the general store email if it's different
    if site_settings.email and site_settings.email not in admin_emails:
        admin_emails.append(site_settings.email)
    
    # Fallback to system default if no emails found
    if not admin_emails:
        admin_emails = [getattr(settings, 'ADMIN_EMAIL', settings.DEFAULT_FROM_EMAIL)]

    for to_email in admin_emails:
        send_html_email(
            f"NEW ORDER RECEIVED # {first.id}",
            to_email,
            "email_templates/admin_order.html",
            context,
            reply_to=first.user.email if first.user else None
        )

