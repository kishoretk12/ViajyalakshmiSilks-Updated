# products/views.py
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST

# SMS util (optional, controlled by settings.ENABLE_SMS)
try:
    from .sms_utils import send_sms
except Exception:
    # If sms_utils missing, define a stub to avoid import errors
    def send_sms(to_phone, message, from_phone=None):
        logging.getLogger(__name__).warning("send_sms not available; SMS skipped.")
        return False

import razorpay
from .models import Saree, Order, UserProfile, Cart, CartItem, Address

logger = logging.getLogger(__name__)

client = razorpay.Client(auth=(getattr(settings, 'RAZORPAY_KEY_ID', None),
                               getattr(settings, 'RAZORPAY_KEY_SECRET', None)))


def home_view(request):
    return render(request, 'home.html')


def shop_view(request):
    sarees = Saree.objects.filter(available=True)

    cart_items = []
    if request.user.is_authenticated:
        try:
            cart = Cart.objects.get(user=request.user)
            cart_items = cart.items.values_list('saree_id', flat=True)
        except Cart.DoesNotExist:
            cart_items = []

    return render(request, 'shop.html', {
        'sarees': sarees,
        'cart_items': cart_items
    })


@login_required
def buy_now(request, product_id):
    # Redirect to address selection first
    return redirect('select_address_buy_now', product_id=product_id)


@login_required
def payment_complete(request):
    """Handle Razorpay payment verification, mark orders paid, send notifications."""
    if request.method != 'POST':
        return redirect('shop')

    payment_id = request.POST.get('razorpay_payment_id')
    order_id = request.POST.get('razorpay_order_id')
    signature = request.POST.get('razorpay_signature')

    orders = Order.objects.filter(razorpay_order_id=order_id)
    if not orders.exists():
        return render(request, 'payment_failed.html')

    params = {
        'razorpay_order_id': order_id,
        'razorpay_payment_id': payment_id,
        'razorpay_signature': signature
    }

    try:
        # verify payment signature
        client.utility.verify_payment_signature(params)

        # mark orders paid
        for order in orders:
            order.paid = True
            order.razorpay_payment_id = payment_id
            order.razorpay_signature = signature
            order.save()

        # -------------------------
        # Try fetch payment details from Razorpay (used for receipt)
        # -------------------------
        payment_info = None
        try:
            if payment_id:
                payment_info = client.payment.fetch(payment_id)
        except Exception as e:
            # Don't fail overall flow if fetch fails
            logger.warning("Could not fetch Razorpay payment details: %s", e)
            payment_info = None

        # -------------------------
        # Email notifications
        # -------------------------
        try:
            from .email_utils import send_order_notification_to_admin, send_order_confirmation_to_customer
        except Exception as e:
            logger.warning("Custom email utilities not present or failed to import: %s", e)
            send_order_notification_to_admin = None
            send_order_confirmation_to_customer = None

        # Send admin notification via your function (if exists), else fallback to send_mail
        try:
            if callable(send_order_notification_to_admin):
                send_order_notification_to_admin(orders)
            else:
                # fallback: send a simple admin email
                first_order = orders.first()
                if first_order and getattr(first_order, 'delivery_address', None):
                    addr = first_order.delivery_address
                    product_list = ", ".join([f"{o.saree.name} (x{o.quantity or 1})" for o in orders])
                    total_amount = sum(o.amount for o in orders)
                    admin_subject = f"NEW ORDER #{first_order.id}"
                    admin_body = (
                        f"Name: {addr.full_name}\n"
                        f"Phone: {addr.phone}\n"
                        f"Address: {addr.address_line_1}"
                        + (f", {addr.address_line_2}" if addr.address_line_2 else "") +
                        f", {addr.city}, {addr.state} - {addr.pincode}\n\n"
                        f"Items: {product_list}\nAmount: Rs.{total_amount}\n"
                        f"Payment ID: {payment_id or 'N/A'}\n"
                    )
                    admin_email = getattr(settings, 'ADMIN_EMAIL', None)
                    if admin_email:
                        try:
                            send_mail(admin_subject, admin_body, settings.DEFAULT_FROM_EMAIL, [admin_email])
                        except Exception as e:
                            logger.error("Failed to send fallback admin email: %s", e)
        except Exception as e:
            logger.error("Admin notification error: %s", e)

        # Send confirmation emails to customers
        for order in orders:
            try:
                # Use your custom email function if present
                if callable(send_order_confirmation_to_customer):
                    try:
                        send_order_confirmation_to_customer(order)
                    except Exception as e:
                        logger.error("send_order_confirmation_to_customer failed for order %s: %s", order.id, e)
                # Additionally send a short payment receipt email (direct) to customer email
                customer_email = None
                if order.user and getattr(order.user, 'email', None):
                    customer_email = order.user.email

                # Fallback: try delivery address email if you store it (not assumed here)
                if customer_email:
                    try:
                        subject = f"Payment Receipt for Order #{order.id}"
                        body_lines = [
                            f"Hello {order.delivery_address.full_name if order.delivery_address else order.user.get_full_name() or order.user.username},",
                            "",
                            f"Thank you for your order #{order.id}. Below are your payment details:",
                            f"Payment ID: {payment_id or order.razorpay_payment_id or 'N/A'}",
                        ]
                        if payment_info:
                            body_lines += [
                                f"Amount (INR): {int(payment_info.get('amount', 0)) / 100 if payment_info.get('amount') else order.amount}",
                                f"Method: {payment_info.get('method', 'N/A')}",
                                f"Status: {payment_info.get('status', 'N/A')}",
                                f"Created at (epoch): {payment_info.get('created_at', 'N/A')}",
                            ]
                        body_lines += [
                            "",
                            "This is an automated receipt from Vijayalakshmi Silks.",
                            "If you have any questions reply to this email."
                        ]
                        body = "\n".join(body_lines)
                        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [customer_email])
                    except Exception as e:
                        logger.error("Failed to send direct payment receipt email for order %s: %s", order.id, e)
            except Exception as e:
                logger.error("Customer email error for order %s: %s", order.id, e)

        # -------------------------
        # Optional SMS notifications (controlled by settings.ENABLE_SMS)
        # -------------------------
        try:
            if getattr(settings, "ENABLE_SMS", False):
                # Admin SMS
                first_order = orders.first()
                if first_order and getattr(first_order, 'delivery_address', None):
                    addr = first_order.delivery_address
                    product_list = ", ".join([f"{o.saree.name} (x{o.quantity or 1})" for o in orders])
                    total_amount = sum(o.amount for o in orders)
                    admin_phone = getattr(settings, "ADMIN_PHONE", None)
                    admin_msg = (
                        f"NEW ORDER #{first_order.id}\n"
                        f"{addr.full_name}, {addr.phone}\n"
                        f"{addr.address_line_1}{', ' + addr.address_line_2 if addr.address_line_2 else ''}, "
                        f"{addr.city} - {addr.pincode}\nItems: {product_list}\nAmount: Rs.{total_amount}"
                    )
                    try:
                        if admin_phone:
                            send_sms(admin_phone, admin_msg)
                    except Exception as e:
                        logger.error("Admin SMS send failed: %s", e)

                # Customer SMS(s)
                for order in orders:
                    try:
                        ca = order.delivery_address
                        if not ca or not getattr(ca, 'phone', None):
                            continue
                        cust_msg = (
                            f"Dear {ca.full_name}, your order #{order.id} for Rs.{order.amount} is confirmed. "
                            "We'll pack & ship soon. Tracking details will be sent once dispatched. - Vijayalakshmi Silks"
                        )
                        send_sms(ca.phone, cust_msg)
                    except Exception as e:
                        logger.error("Customer SMS failed for order %s: %s", order.id, e)
        except Exception as e:
            logger.error("SMS notification section failed: %s", e)

        # clear cart for logged-in user
        if request.user.is_authenticated:
            try:
                cart = Cart.objects.get(user=request.user)
                cart.items.all().delete()
            except Cart.DoesNotExist:
                pass

        return render(request, 'thankyou.html', {
            'orders': orders,
            'total_amount': sum(order.amount for order in orders)
        })

    except Exception as e:
        logger.exception("Payment verification failed: %s", e)
        return render(request, 'payment_failed.html')


@login_required
def cart_view(request):
    cart, created = Cart.objects.get_or_create(user=request.user)
    cart_items = cart.items.all().select_related('saree')

    context = {
        'cart': cart,
        'cart_items': cart_items,
        'total_price': cart.get_total_price(),
        'total_items': cart.get_total_items(),
    }
    return render(request, 'cart.html', context)


@login_required
@require_POST
def add_to_cart(request, product_id):
    saree = get_object_or_404(Saree, id=product_id, available=True)
    cart, created = Cart.objects.get_or_create(user=request.user)

    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        saree=saree,
        defaults={'quantity': 1}
    )

    # If item already exists, return appropriate message
    if not created:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'already_in_cart': True,
                'message': f'{saree.name} is already in your cart!',
                'cart_total_items': cart.get_total_items(),
                'cart_items_count': cart.get_items_count()
            })
        messages.info(request, f'{saree.name} is already in your cart!')
        return redirect('shop')

    # Item successfully added
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': f'{saree.name} added to cart!',
            'cart_total_items': cart.get_total_items(),
            'cart_items_count': cart.get_items_count()
        })

    messages.success(request, f'{saree.name} has been added to your cart!')
    return redirect('shop')


# update_cart_item view removed since quantity is always 1


@login_required
@require_POST
def remove_from_cart(request, item_id):
    cart_item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
    saree_name = cart_item.saree.name
    cart_item.delete()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': f'{saree_name} removed from cart!',
            'cart_total_items': cart_item.cart.get_total_items(),
            'cart_total': cart_item.cart.get_total_price()
        })

    messages.success(request, f'{saree_name} has been removed from your cart!')
    return redirect('cart')


@login_required
def checkout_cart(request):
    # Redirect to address selection first
    return redirect('select_address_checkout')


@login_required
def clear_cart_after_payment(request):
    """Clear cart after successful payment"""
    try:
        cart = Cart.objects.get(user=request.user)
        cart.items.all().delete()
        messages.success(request, 'Your order has been placed successfully!')
    except Cart.DoesNotExist:
        pass
    return redirect('profile')


# Authentication Views
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.GET.get('next', '/')
            messages.success(request, f'Welcome back, {user.get_full_name() or user.username}!')
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid username or password.')

    return render(request, 'auth/login.html')


def signup_view(request):
    if request.method == 'POST':
        # Get form data
        full_name = request.POST.get('full_name')
        username = request.POST.get('username')
        email = request.POST.get('email')
        mobile_number = request.POST.get('mobile_number')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')

        # Validation
        if password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'auth/signup.html')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
            return render(request, 'auth/signup.html')

        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already exists.')
            return render(request, 'auth/signup.html')

        try:
            with transaction.atomic():
                # Create user
                name_parts = full_name.split(' ', 1)
                first_name = name_parts[0]
                last_name = name_parts[1] if len(name_parts) > 1 else ''

                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name
                )

                # Create user profile
                UserProfile.objects.create(
                    user=user,
                    mobile_number=mobile_number
                )

                # Log the user in
                login(request, user)
                messages.success(request, f'Welcome to Vijayalakshmi Silks, {full_name}!')
                return redirect('/')

        except Exception as e:
            messages.error(request, 'An error occurred while creating your account. Please try again.')

    return render(request, 'auth/signup.html')


def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('/')


@login_required
def profile_view(request):
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        # Create profile if it doesn't exist
        profile = UserProfile.objects.create(
            user=request.user,
            mobile_number=''
        )

    user_orders = Order.objects.filter(user=request.user).order_by('-created_at')

    context = {
        'user': request.user,
        'profile': profile,
        'orders': user_orders
    }
    return render(request, 'auth/profile.html', context)


# Address Management Views
@login_required
def select_address_buy_now(request, product_id):
    """Address selection page for single product purchase"""
    saree = get_object_or_404(Saree, id=product_id, available=True)
    user_addresses = Address.objects.filter(user=request.user)

    if request.method == 'POST':
        address_id = request.POST.get('address_id')
        if address_id:
            address = get_object_or_404(Address, id=address_id, user=request.user)
            # Store address in session for payment
            request.session['selected_address_id'] = address.id
            request.session['product_id'] = product_id
            return redirect('process_buy_now_payment')

    context = {
        'saree': saree,
        'addresses': user_addresses,
        'is_buy_now': True
    }
    return render(request, 'address/select_address.html', context)


@login_required
def select_address_checkout(request):
    """Address selection page for cart checkout"""
    cart = get_object_or_404(Cart, user=request.user)

    if not cart.items.exists():
        messages.warning(request, 'Your cart is empty!')
        return redirect('cart')

    user_addresses = Address.objects.filter(user=request.user)

    if request.method == 'POST':
        address_id = request.POST.get('address_id')
        if address_id:
            address = get_object_or_404(Address, id=address_id, user=request.user)
            # Store address in session for payment
            request.session['selected_address_id'] = address.id
            return redirect('process_checkout_payment')

    context = {
        'cart': cart,
        'addresses': user_addresses,
        'is_checkout': True
    }
    return render(request, 'address/select_address.html', context)


@login_required
def add_address(request):
    """Add new address"""
    if request.method == 'POST':
        name = request.POST.get('name')
        full_name = request.POST.get('full_name')
        phone = request.POST.get('phone')
        address_line_1 = request.POST.get('address_line_1')
        address_line_2 = request.POST.get('address_line_2', '')
        city = request.POST.get('city')
        state = request.POST.get('state')
        pincode = request.POST.get('pincode')
        is_default = request.POST.get('is_default') == 'on'

        # Validation
        if not all([name, full_name, phone, address_line_1, city, state, pincode]):
            messages.error(request, 'Please fill in all required fields.')
            return render(request, 'address/add_address.html')

        try:
            Address.objects.create(
                user=request.user,
                name=name,
                full_name=full_name,
                phone=phone,
                address_line_1=address_line_1,
                address_line_2=address_line_2,
                city=city,
                state=state,
                pincode=pincode,
                is_default=is_default
            )
            messages.success(request, 'Address added successfully!')

            # Redirect based on where user came from
            action = request.GET.get('action')
            if action == 'buy_now':
                product_id = request.GET.get('product_id')
                if product_id:
                    return redirect('select_address_buy_now', product_id=int(product_id))
            elif action == 'checkout':
                return redirect('select_address_checkout')

            # Fallback to manage addresses
            return redirect('manage_addresses')

        except Exception as e:
            messages.error(request, 'Error adding address. Please try again.')

    return render(request, 'address/add_address.html')


@login_required
def manage_addresses(request):
    """Manage user addresses"""
    addresses = Address.objects.filter(user=request.user)
    context = {
        'addresses': addresses
    }
    return render(request, 'address/manage_addresses.html', context)


@login_required
def edit_address(request, address_id):
    """Edit existing address"""
    address = get_object_or_404(Address, id=address_id, user=request.user)

    if request.method == 'POST':
        address.name = request.POST.get('name')
        address.full_name = request.POST.get('full_name')
        address.phone = request.POST.get('phone')
        address.address_line_1 = request.POST.get('address_line_1')
        address.address_line_2 = request.POST.get('address_line_2', '')
        address.city = request.POST.get('city')
        address.state = request.POST.get('state')
        address.pincode = request.POST.get('pincode')
        address.is_default = request.POST.get('is_default') == 'on'

        # Validation
        if not all([address.name, address.full_name, address.phone, address.address_line_1, address.city, address.state, address.pincode]):
            messages.error(request, 'Please fill in all required fields.')
            return render(request, 'address/edit_address.html', {'address': address})

        try:
            address.save()
            messages.success(request, 'Address updated successfully!')
            return redirect('manage_addresses')
        except Exception as e:
            messages.error(request, 'Error updating address. Please try again.')

    return render(request, 'address/edit_address.html', {'address': address})


@login_required
def delete_address(request, address_id):
    """Delete address"""
    address = get_object_or_404(Address, id=address_id, user=request.user)

    if request.method == 'POST':
        address.delete()
        messages.success(request, 'Address deleted successfully!')
        return redirect('manage_addresses')

    return render(request, 'address/delete_address.html', {'address': address})


@login_required
def process_buy_now_payment(request):
    """Process payment for single product with selected address"""
    address_id = request.session.get('selected_address_id')
    product_id = request.session.get('product_id')

    if not address_id or not product_id:
        messages.error(request, 'Session expired. Please try again.')
        return redirect('shop')

    address = get_object_or_404(Address, id=address_id, user=request.user)
    saree = get_object_or_404(Saree, id=product_id, available=True)

    amount = saree.price * 100  # paise
    razorpay_order = client.order.create({'amount': amount, 'currency': 'INR', 'payment_capture': '1'})

    # Create order with selected address
    order = Order.objects.create(
        saree=saree,
        amount=saree.price,
        razorpay_order_id=razorpay_order['id'],
        user=request.user,
        delivery_address=address
    )

    # Clear session data
    del request.session['selected_address_id']
    del request.session['product_id']

    return render(request, 'payment.html', {
        'order': order,
        'order_id': razorpay_order['id'],
        'amount': amount,
        'razorpay_key': settings.RAZORPAY_KEY_ID,
        'saree': saree,
        'address': address
    })


@login_required
def process_checkout_payment(request):
    """Process payment for cart checkout with selected address"""
    address_id = request.session.get('selected_address_id')

    if not address_id:
        messages.error(request, 'Session expired. Please try again.')
        return redirect('cart')

    address = get_object_or_404(Address, id=address_id, user=request.user)
    cart = get_object_or_404(Cart, user=request.user)

    if not cart.items.exists():
        messages.warning(request, 'Your cart is empty!')
        return redirect('cart')

    # Calculate total amount
    total_amount = cart.get_total_price()
    razorpay_amount = total_amount * 100  # Convert to paise

    # Create Razorpay order
    razorpay_order = client.order.create({
        'amount': razorpay_amount,
        'currency': 'INR',
        'payment_capture': '1'
    })

    # Create orders for each cart item with selected address
    orders = []
    for cart_item in cart.items.all():
        order = Order.objects.create(
            saree=cart_item.saree,
            user=request.user,
            quantity=cart_item.quantity,
            amount=cart_item.get_total_price(),
            razorpay_order_id=razorpay_order['id'],
            delivery_address=address
        )
        orders.append(order)

    # Clear session data
    del request.session['selected_address_id']

    context = {
        'orders': orders,
        'cart': cart,
        'order_id': razorpay_order['id'],
        'amount': razorpay_amount,
        'total_amount': total_amount,
        'razorpay_key': settings.RAZORPAY_KEY_ID,
        'user': request.user,
        'address': address
    }
    return render(request, 'checkout.html', context)
