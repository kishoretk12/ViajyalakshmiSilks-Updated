# products/email_utils.py
import logging
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

def send_order_notification_to_admin(orders):
    """
    orders: queryset/list of Order objects
    Sends a detailed admin email
    """
    try:
        if not orders:
            return False
        first = orders[0]
        order_ids = ", ".join(str(o.id) for o in orders)
        total_amount = sum(o.amount for o in orders)
        addr = getattr(first, 'delivery_address', None)

        lines = [
            f"New order(s): {order_ids}",
            "",
            "Customer details:"
        ]
        if addr:
            lines += [
                f"Name: {addr.full_name}",
                f"Phone: {addr.phone}",
                f"Address: {addr.address_line_1}" + (f", {addr.address_line_2}" if addr.address_line_2 else ""),
                f"{addr.city}, {addr.state} - {addr.pincode}",
                ""
            ]
        else:
            lines.append(f"User: {first.user.get_full_name() or first.user.username}")

        lines += ["Items:"]
        for o in orders:
            qty = getattr(o, 'quantity', 1) or 1
            lines.append(f"- {o.saree.name if getattr(o,'saree',None) else 'Item'} (x{qty}): Rs.{o.amount}")

        lines += [
            "",
            f"Total amount: Rs.{total_amount}",
            f"Payment ID: {first.razorpay_payment_id or 'N/A'}",
            "",
            f"Admin panel: {getattr(settings, 'SITE_URL', 'http://example.com')}/admin/",
            "",
            "Regards,",
            "Vijayalakshmi Silks"
        ]

        admin_email = getattr(settings, 'ADMIN_EMAIL', None)
        if admin_email:
            send_mail(f"[Vijayalakshmi Silks] New Order(s) #{order_ids}", "\n".join(lines),
                      settings.DEFAULT_FROM_EMAIL, [admin_email])
            logger.info("Admin order notification email sent to %s", admin_email)
            return True
        logger.warning("ADMIN_EMAIL not configured; cannot send admin email.")
        return False
    except Exception as e:
        logger.exception("send_order_notification_to_admin failed: %s", e)
        return False


def send_order_confirmation_to_customer(order):
    """
    Sends per-order confirmation email with receipt details.
    """
    try:
        user_email = order.user.email if order.user and getattr(order.user, 'email', None) else None
        if not user_email:
            logger.warning("Order %s has no user email; skipping confirmation", order.id)
            return False

        addr = getattr(order, 'delivery_address', None)
        lines = [
            f"Hello {addr.full_name if addr else (order.user.get_full_name() or order.user.username)},",
            "",
            f"Thank you for your order #{order.id}. Details below:",
            "",
            f"Item: {order.saree.name if getattr(order,'saree',None) else 'Item'}",
            f"Quantity: {order.quantity or 1}",
            f"Amount: Rs.{order.amount}",
            "",
            f"Payment ID: {order.razorpay_payment_id or 'N/A'}",
            "",
        ]
        if addr:
            lines += [
                "Delivery Address:",
                f"{addr.full_name}",
                f"{addr.address_line_1}" + (f", {addr.address_line_2}" if addr.address_line_2 else ""),
                f"{addr.city}, {addr.state} - {addr.pincode}",
                ""
            ]
        lines += [
            "We will pack & ship soon. For queries reply to this email.",
            "",
            "Regards,",
            "Vijayalakshmi Silks"
        ]

        subject = f"Order Confirmation & Receipt - Order #{order.id}"
        send_mail(subject, "\n".join(lines), settings.DEFAULT_FROM_EMAIL, [user_email])
        logger.info("Order confirmation email sent to %s for order %s", user_email, order.id)
        return True
    except Exception as e:
        logger.exception("send_order_confirmation_to_customer failed for %s: %s", getattr(order,'id', 'N/A'), e)
        return False
