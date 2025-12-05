from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

def send_html_email(subject, to_email, html_template, context):
    html_content = render_to_string(html_template, context)
    msg = EmailMultiAlternatives(subject, "", settings.DEFAULT_FROM_EMAIL, [to_email])
    msg.attach_alternative(html_content, "text/html")
    msg.send()


def send_customer_receipt(order, payment_info):
    customer = order.user
    addr = order.delivery_address

    context = {
        "customer_name": customer.get_full_name(),
        "order_id": order.id,
        "payment_id": payment_info.get("id", ""),
        "amount": order.amount,
        "payment_method": payment_info.get("method", "Online"),
        "payment_status": payment_info.get("status", "success"),
        "full_name": addr.full_name,
        "address_line_1": addr.address_line_1,
        "address_line_2": addr.address_line_2,
        "city": addr.city,
        "state": addr.state,
        "pincode": addr.pincode,
        "phone": addr.phone,
        "items": [{
            "name": order.saree.name,
            "qty": order.quantity or 1,
            "price": order.amount
        }]
    }

    send_html_email(
        f"Order Receipt - #{order.id}",
        customer.email,
        "email_templates/customer_receipt.html",
        context
    )


def send_admin_order_email(orders):
    first = orders[0]
    addr = first.delivery_address

    items = [{
        "name": o.saree.name,
        "qty": o.quantity or 1,
        "price": o.amount,
    } for o in orders]

    context = {
        "order_id": first.id,
        "full_name": addr.full_name,
        "phone": addr.phone,
        "address_line_1": addr.address_line_1,
        "address_line_2": addr.address_line_2,
        "city": addr.city,
        "state": addr.state,
        "pincode": addr.pincode,
        "items": items,
        "total": sum(o.amount for o in orders),
    }

    send_html_email(
        f"NEW ORDER RECEIVED # {first.id}",
        settings.ADMIN_EMAIL,
        "email_templates/admin_order.html",
        context
    )

