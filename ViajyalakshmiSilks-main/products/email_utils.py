from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


def send_order_notification_to_admin(orders):
    """
    Send email notification to admin when new order(s) are placed
    """
    try:
        if not orders:
            return False
            
        # Handle QuerySet or list of orders
        if hasattr(orders, '__iter__') and not isinstance(orders, str):
            # It's a QuerySet or list
            orders_list = list(orders)  # Convert QuerySet to list
        else:
            # It's a single order
            orders_list = [orders]
        
        first_order = orders_list[0]
        
        # Calculate total amount
        total_amount = sum(order.amount for order in orders_list)
        
        # Prepare context for email template
        context = {
            'orders': orders_list,
            'total_orders': len(orders_list),
            'total_amount': total_amount,
            'customer': first_order.user if first_order.user else 'Guest Customer',
            'customer_profile': None
        }
        
        # Get customer profile if user exists
        if first_order.user:
            try:
                context['customer_profile'] = first_order.user.userprofile
            except:
                context['customer_profile'] = None
        
        # Email subject
        if len(orders_list) == 1:
            subject = f'New Order #{first_order.id} - ViajyalakshmiSilks'
        else:
            subject = f'New Orders ({len(orders_list)} items) - ViajyalakshmiSilks'
        
        # Create email content
        message = f"""
NEW ORDER NOTIFICATION - ViajyalakshmiSilks
{'='*50}

Order Details:
"""
        
        for order in orders_list:
            customer_info = ""
            if order.user:
                # Get delivery address from order
                if order.delivery_address:
                    customer_info = f"""
Customer: {order.delivery_address.full_name}
Email: {order.user.email}
Phone: {order.delivery_address.phone}
Address: {order.delivery_address.get_full_address()}
"""
                else:
                    # Fallback for orders without delivery address
                    try:
                        profile = order.user.userprofile
                        customer_info = f"""
Customer: {order.user.get_full_name() or order.user.username}
Email: {order.user.email}
Phone: {profile.mobile_number}
Address: No delivery address provided
"""
                    except:
                        customer_info = f"""
Customer: {order.user.get_full_name() or order.user.username}
Email: {order.user.email}
Phone: Not available
Address: Not available
"""
            else:
                customer_info = f"""
Customer: Guest
Email: {order.guest_email or 'Not provided'}
Phone: {order.guest_phone or 'Not provided'}
Address: {order.guest_address or 'Not provided'}
"""
            
            message += f"""
Order ID: {order.id}
Product: {order.saree.name}
Quantity: {order.quantity}
Amount: ₹{order.amount}
Payment ID: {order.razorpay_payment_id}
Order Date: {timezone.localtime(order.created_at).strftime('%d %B %Y at %I:%M %p IST')}

{customer_info}
{'='*30}
"""
        
        message += f"""
TOTAL AMOUNT: ₹{total_amount}

Please process these orders and arrange for shipping.

Best regards,
ViajyalakshmiSilks System
"""
        
        # Send email
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.ADMIN_EMAIL],
            fail_silently=False,
        )
        
        logger.info(f"Order notification email sent successfully for {len(orders_list)} orders")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send order notification email: {str(e)}")
        return False

def send_order_confirmation_to_customer(order):
    """
    Send order confirmation email to customer
    """
    try:
        if not order.user or not order.user.email:
            return False
            
        subject = f'Order Confirmation #{order.id} - ViajyalakshmiSilks'
        
        message = f"""
Dear {order.user.get_full_name() or order.user.username},

Thank you for your order! Your order has been confirmed.

ORDER DETAILS:
{'='*30}
Order ID: {order.id}
Product: {order.saree.name}
Quantity: {order.quantity}
Amount: ₹{order.amount}
Order Date: {timezone.localtime(order.created_at).strftime('%d %B %Y at %I:%M %p IST')}

SHIPPING INFORMATION:
"""
        
        # Get delivery address from the order
        if order.delivery_address:
            message += f"""
Name: {order.delivery_address.full_name}
Phone: {order.delivery_address.phone}
Address: {order.delivery_address.get_full_address()}
"""
        else:
            # Fallback: try to get from user profile (for backward compatibility)
            try:
                profile = order.user.userprofile
                message += f"""
Name: {order.user.get_full_name() or order.user.username}
Phone: {profile.mobile_number}
Address: Please add delivery address to your account.
"""
            except:
                message += """
Please update your profile with shipping address.
"""
        
        message += f"""

Your order will be processed and shipped soon.
You will receive a tracking notification once your order is dispatched.

Thank you for shopping with ViajyalakshmiSilks!

Best regards,
ViajyalakshmiSilks Team
"""
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.user.email],
            fail_silently=False,
        )
        
        logger.info(f"Order confirmation email sent to customer for order {order.id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send customer confirmation email: {str(e)}")
        return False
