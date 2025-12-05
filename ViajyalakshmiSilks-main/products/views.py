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

import razorpay
from .models import Saree, Order, UserProfile, Cart, CartItem, Address

logger = logging.getLogger(__name__)

# ------------------------
# Try to import external utils; otherwise provide safe fallbacks
# ------------------------
try:
    from .sms_utils import send_sms as send_sms_util
except Exception:
    send_sms_util = None
    logger.warning("products.sms_utils not found; SMS calls will use fallback or be skipped.")

try:
    from .email_utils import send_order_notification_to_admin as EMAIL_notify_admin, \
                             send_order_confirmation_to_customer as EMAIL_notify_customer
except Exception:
    EMAIL_notify_admin = None
    EMAIL_notify_customer = None
    logger.warning("products.email_utils not found; using inline fallback email senders.")


def _send_sms(to_phone: str, message: str) -> bool:
    """Unified SMS send wrapper. Returns True on success, False otherwise."""
    try:
        if not getattr(settings, "ENABLE_SMS", False):
            logger.debug("ENABLE_SMS is False; skipping SMS to %s", to_phone)
            return False

        # Use provided sms_utils if available
        if send_sms_util:
            resp = send_sms_util(to_phone, message)
            # send_sms_util may return Twilio dict/object or True/False
            if isinstance(resp, dict) or getattr(resp, 'sid', None):
                return True
            return bool(resp)

        # Fallback: try Twilio directly (in-case sms_utils missing)
        sid = getattr(settings, "TWILIO_ACCOUNT_SID", None)
        token = getattr(settings, "TWILIO_AUTH_TOKEN", None)
        from_num = getattr(settings, "TWILIO_PHONE_NUMBER", None)
        if not (sid and token and from_num):
            logger.error("Twilio creds not configured properly; cannot send SMS.")
            return False

        from twilio.rest import Client
        client = Client(sid, token)
        msg = client.messages.create(body=message, from_=from_num, to=to_phone)
        logger.info("SMS sent via fallback Twilio to %s, sid=%s", to_phone, getattr(msg, 'sid', None))
        return True
    except Exception as e:
        logger.exception("SMS send failed to %s: %s", to_phone, e)
        return False


def _send_email(subject: str, body: str, to_list: list) -> bool:
    """Wrapper to send email via Django send_mail. Returns True on success."""
    try:
        if not to_list:
            logger.warning("No recipients provided for email: %s", subject)
            return False
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, to_list)
        logger.info("Email sent: %s -> %s", subject, to_list)
        return True
    except Exception as e:
        logger.exception("Failed to send email '%s' to %s: %s", subject, to_list, e)
        return False


# Razorpay client - uses keys from settings (you keep them directly in settings.py)
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
    return redirect('select_address_buy_now', product_id=product_id)


@login_required
def payment_complete(request):
    """
    Full payment verification, detailed email + SMS for admin & customers.
    """
    if request.method != 'POST':
        return redirect('shop')

    payment_id = request.POST.get('razorpay_payment_id')
    order_id = request.POST.get('razorpay_order_id')
    signature = request.POST.get('razorpay_signature')

    orders = Order.objects.filter(razorpay_order_id=order_id)
    if not orders.exists():
        logger.warning("payment_complete called with unknown razorpay_order_id=%s", order_id)
        return render(request, 'payment_failed.html')

    params = {
        'razorpay_order_id': order_id,
        'razorpay_payment_id': payment_id,
        'razorpay_signature': signature
    }

    try:
        # verify signature (raises if invalid)
        client.utility.verify_payment_signature(params)
    except Exception as e:
        logger.exception("Razorpay signature verification failed: %s", e)
        return render(request, 'payment_failed.html')

    # mark orders paid & store payment ids
    for o in orders:
        o.paid = True
        o.razorpay_payment_id = payment_id
        o.razorpay_signature = signature
        o.save()

    # Try to fetch payment details from Razorpay for richer receipts (non-fatal)
    payment_info = None
    try:
        if payment_id:
            payment_info = client.payment.fetch(payment_id)
    except Exception as e:
        logger.warning("Could not fetch Razorpay payment details for payment_id=%s: %s", payment_id, e)
        payment_info = None

    # --- Prepare shared details ---
    def _format_order_line(o):
        qty = getattr(o, 'quantity', 1) or 1
        name = o.saree.name if getattr(o, 'saree', None) else "Item"
        return f"{name} (x{qty}) - Rs.{o.amount}"

    order_lines = [ _format_order_line(o) for o in orders ]
    total_amount = sum(o.amount for o in orders)
    order_ids = ", ".join(str(o.id) for o in orders)
    payment_display = payment_id or orders.first().razorpay_payment_id or "N/A"

    # -------------------------
    # SEND ADMIN EMAIL (DETAILED)
    # -------------------------
    try:
        admin_email = getattr(settings, 'ADMIN_EMAIL', None)
        if admin_email:
            first = orders.first()
            addr = getattr(first, 'delivery_address', None)
            admin_subject = f"[Vijayalakshmi Silks] New Order(s) #{order_ids}"
            admin_body_lines = [
                f"New order(s) received: {order_ids}",
                "",
                "Customer details:",
            ]
            if addr:
                admin_body_lines += [
                    f"Name: {addr.full_name}",
                    f"Phone: {addr.phone}",
                    f"Address: {addr.address_line_1}" + (f", {addr.address_line_2}" if addr.address_line_2 else ""),
                    f"{addr.city}, {addr.state} - {addr.pincode}",
                    ""
                ]
            else:
                admin_body_lines.append(f"User: {first.user.get_full_name() or first.user.username} (no address object)")

            admin_body_lines += [
                "Items:",
                *order_lines,
                "",
                f"Total amount: Rs.{total_amount}",
                f"Payment ID: {payment_display}",
                "",
                f"Admin panel: {getattr(settings, 'SITE_URL', 'http://example.com')}/admin/",
                "",
                "Please process this order from the admin dashboard.",
                "",
                "Regards,",
                "Vijayalakshmi Silks"
            ]
            _send_email(admin_subject, "\n".join(admin_body_lines), [admin_email])
        else:
            logger.warning("ADMIN_EMAIL not set; skipping admin email.")
    except Exception as e:
        logger.exception("Failed to send admin email: %s", e)

    # If you have custom email function, call it (best-effort)
    try:
        if EMAIL_notify_admin:
            try:
                EMAIL_notify_admin(orders)
            except Exception as e:
                logger.exception("Custom EMAIL_notify_admin failed: %s", e)
    except Exception:
        pass

    # -------------------------
    # SEND CUSTOMER EMAILS (DETAILED RECEIPT)
    # -------------------------
    for o in orders:
        try:
            user_email = o.user.email if o.user and getattr(o.user, 'email', None) else None
            if not user_email:
                logger.warning("Order %s has no user email; skipping customer email.", o.id)
            else:
                cust_subject = f"Order Confirmation & Receipt - Order #{o.id}"
                addr = getattr(o, 'delivery_address', None)
                cust_lines = [
                    f"Hello {addr.full_name if addr else (o.user.get_full_name() or o.user.username)},",
                    "",
                    f"Thank you for your order #{o.id}. Here are the details:",
                    "",
                    f"Item: {o.saree.name if getattr(o,'saree',None) else 'Item'}",
                    f"Quantity: {o.quantity or 1}",
                    f"Amount: Rs.{o.amount}",
                    "",
                    f"Payment ID: {payment_display}",
                ]
                if payment_info:
                    # include some payment_info fields safely
                    try:
                        amount_paid = int(payment_info.get('amount', 0)) / 100 if payment_info.get('amount') else o.amount
                        method = payment_info.get('method', 'N/A')
                        status = payment_info.get('status', 'N/A')
                        cust_lines += [
                            f"Payment details: Amount: Rs.{amount_paid}, Method: {method}, Status: {status}"
                        ]
                    except Exception:
                        pass

                if addr:
                    cust_lines += [
                        "",
                        "Delivery Address:",
                        f"{addr.full_name}",
                        f"{addr.address_line_1}" + (f", {addr.address_line_2}" if addr.address_line_2 else ""),
                        f"{addr.city}, {addr.state} - {addr.pincode}",
                    ]

                cust_lines += [
                    "",
                    "We will pack & ship soon. Tracking details will be emailed/smsed once dispatched.",
                    "",
                    f"For queries reply to {settings.DEFAULT_FROM_EMAIL}",
                    "",
                    "Regards,",
                    "Vijayalakshmi Silks"
                ]
                _send_email(cust_subject, "\n".join(cust_lines), [user_email])

            # If you have a custom per-order email function, call it too
            if EMAIL_notify_customer:
                try:
                    EMAIL_notify_customer(o)
                except Exception as e:
                    logger.exception("Custom EMAIL_notify_customer failed for %s: %s", o.id, e)

        except Exception as e:
            logger.exception("Customer email error for order %s: %s", o.id, e)

    # -------------------------
    # OPTIONAL: SEND SMSes (Admin + Customer) - concise
    # -------------------------
    try:
        if getattr(settings, "ENABLE_SMS", False):
            # Admin SMS (concise)
            try:
                first = orders.first()
                addr = getattr(first, 'delivery_address', None)
                admin_phone = getattr(settings, 'ADMIN_PHONE', None)
                if admin_phone:
                    admin_sms = (
                        f"NEW ORDER #{first.id} | {addr.full_name if addr else first.user.username} | "
                        f"{addr.phone if addr else 'N/A'} | Items: {len(order_lines)} | Rs.{total_amount}"
                    )
                    _send_sms(admin_phone, admin_sms)
            except Exception as e:
                logger.exception("Admin SMS failed: %s", e)

            # Customer SMS(s) - short receipt
            for o in orders:
                try:
                    ca = getattr(o, 'delivery_address', None)
                    phone = getattr(ca, 'phone', None) or (o.user and getattr(o.user, 'profile', None) and getattr(o.user.profile, 'mobile_number', None))
                    if not phone:
                        # no phone available on order delivery address
                        logger.debug("Order %s - no customer phone available; skipping SMS", o.id)
                        continue
                    cust_sms = (
                        f"Dear {ca.full_name if ca else (o.user.get_full_name() or o.user.username)}, your order #{o.id} for Rs.{o.amount} is confirmed. "
                        f"Payment ID:{payment_display}. - Vijayalakshmi Silks"
                    )
                    _send_sms(phone, cust_sms)
                except Exception as e:
                    logger.exception("Customer SMS failed for order %s: %s", o.id, e)
    except Exception as e:
        logger.exception("SMS section failed globally: %s", e)

    # -------------------------
    # Clear cart for logged-in user
    # -------------------------
    if request.user.is_authenticated:
        try:
            cart = Cart.objects.get(user=request.user)
            cart.items.all().delete()
        except Cart.DoesNotExist:
            pass

    return render(request, 'thankyou.html', {
        'orders': orders,
        'total_amount': total_amount
    })


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

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': f'{saree.name} added to cart!',
            'cart_total_items': cart.get_total_items(),
            'cart_items_count': cart.get_items_count()
        })

    messages.success(request, f'{saree.name} has been added to your cart!')
    return redirect('shop')


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
    return redirect('select_address_checkout')


@login_required
def clear_cart_after_payment(request):
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
    saree = get_object_or_404(Saree, id=product_id, available=True)
    user_addresses = Address.objects.filter(user=request.user)

    if request.method == 'POST':
        address_id = request.POST.get('address_id')
        if address_id:
            address = get_object_or_404(Address, id=address_id, user=request.user)
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
    cart = get_object_or_404(Cart, user=request.user)

    if not cart.items.exists():
        messages.warning(request, 'Your cart is empty!')
        return redirect('cart')

    user_addresses = Address.objects.filter(user=request.user)

    if request.method == 'POST':
        address_id = request.POST.get('address_id')
        if address_id:
            address = get_object_or_404(Address, id=address_id, user=request.user)
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

            action = request.GET.get('action')
            if action == 'buy_now':
                product_id = request.GET.get('product_id')
                if product_id:
                    return redirect('select_address_buy_now', product_id=int(product_id))
            elif action == 'checkout':
                return redirect('select_address_checkout')

            return redirect('manage_addresses')

        except Exception as e:
            messages.error(request, 'Error adding address. Please try again.')

    return render(request, 'address/add_address.html')


@login_required
def manage_addresses(request):
    addresses = Address.objects.filter(user=request.user)
    context = {'addresses': addresses}
    return render(request, 'address/manage_addresses.html', context)


@login_required
def edit_address(request, address_id):
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
    address = get_object_or_404(Address, id=address_id, user=request.user)

    if request.method == 'POST':
        address.delete()
        messages.success(request, 'Address deleted successfully!')
        return redirect('manage_addresses')

    return render(request, 'address/delete_address.html', {'address': address})


@login_required
def process_buy_now_payment(request):
    address_id = request.session.get('selected_address_id')
    product_id = request.session.get('product_id')

    if not address_id or not product_id:
        messages.error(request, 'Session expired. Please try again.')
        return redirect('shop')

    address = get_object_or_404(Address, id=address_id, user=request.user)
    saree = get_object_or_404(Saree, id=product_id, available=True)

    amount = saree.price * 100  # paise
    razorpay_order = client.order.create({'amount': amount, 'currency': 'INR', 'payment_capture': '1'})

    order = Order.objects.create(
        saree=saree,
        amount=saree.price,
        razorpay_order_id=razorpay_order['id'],
        user=request.user,
        delivery_address=address
    )

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
    address_id = request.session.get('selected_address_id')

    if not address_id:
        messages.error(request, 'Session expired. Please try again.')
        return redirect('cart')

    address = get_object_or_404(Address, id=address_id, user=request.user)
    cart = get_object_or_404(Cart, user=request.user)

    if not cart.items.exists():
        messages.warning(request, 'Your cart is empty!')
        return redirect('cart')

    total_amount = cart.get_total_price()
    razorpay_amount = total_amount * 100  # Convert to paise

    razorpay_order = client.order.create({
        'amount': razorpay_amount,
        'currency': 'INR',
        'payment_capture': '1'
    })

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
