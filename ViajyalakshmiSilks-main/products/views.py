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

# SMS util - controlled by settings.ENABLE_SMS
try:
    from .sms_utils import send_sms
except Exception:
    def send_sms(to_phone, message):
        logging.getLogger(__name__).warning("SMS system not available.")
        return False

import razorpay
from .models import Saree, Order, UserProfile, Cart, CartItem, Address

logger = logging.getLogger(__name__)

client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


# ---------------------------
# HOME / SHOP
# ---------------------------

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

    return render(request, 'shop.html', {"sarees": sarees, "cart_items": cart_items})


# ---------------------------
# BUY NOW
# ---------------------------

@login_required
def buy_now(request, product_id):
    return redirect("select_address_buy_now", product_id=product_id)


# ---------------------------
# PAYMENT COMPLETE
# ---------------------------

@login_required
def payment_complete(request):
    if request.method != "POST":
        return redirect("shop")

    payment_id = request.POST.get("razorpay_payment_id")
    order_id = request.POST.get("razorpay_order_id")
    signature = request.POST.get("razorpay_signature")

    orders = Order.objects.filter(razorpay_order_id=order_id)

    if not orders.exists():
        return render(request, "payment_failed.html")

    params = {
        "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": signature,
    }

    try:
        # Verify payment
        client.utility.verify_payment_signature(params)

        # Mark order(s) as paid
        for order in orders:
            order.paid = True
            order.razorpay_payment_id = payment_id
            order.razorpay_signature = signature
            order.save()

        # Fetch Razorpay payment details (for receipt)
        payment_info = None
        try:
            payment_info = client.payment.fetch(payment_id)
        except Exception as e:
            logger.warning("Payment fetch failed: %s", e)

        # -------------------------
        # EMAIL NOTIFICATIONS
        # -------------------------
        try:
            from .email_utils import send_order_notification_to_admin, send_order_confirmation_to_customer
        except Exception:
            send_order_notification_to_admin = None
            send_order_confirmation_to_customer = None

        # Admin email
        if callable(send_order_notification_to_admin):
            send_order_notification_to_admin(orders)

        # Customer email + Receipt
        for order in orders:
            # Existing template mail
            if callable(send_order_confirmation_to_customer):
                try:
                    send_order_confirmation_to_customer(order)
                except Exception as e:
                    logger.error("Customer email failed: %s", e)

            # Payment receipt email
            customer_email = order.user.email if order.user.email else None

            if customer_email:
                try:
                    subject = f"Payment Receipt for Order #{order.id}"
                    body = f"""
Hello {order.delivery_address.full_name},

Thank you for shopping with us!

Order ID: {order.id}
Payment ID: {payment_id}
Amount Paid: ₹{order.amount}

Payment Method: {payment_info.get('method') if payment_info else 'N/A'}
Status: {payment_info.get('status') if payment_info else 'N/A'}

We will send tracking details once shipped.

Regards,  
Vijayalakshmi Silks
                    """

                    send_mail(
                        subject,
                        body,
                        settings.DEFAULT_FROM_EMAIL,
                        [customer_email],
                    )
                except Exception as e:
                    logger.error("Receipt email failed: %s", e)

        # -------------------------
        # SMS NOTIFICATION (ENABLE_SMS=True)
        # -------------------------
        if getattr(settings, "ENABLE_SMS", False):
            first_order = orders.first()
            addr = first_order.delivery_address

            # ADMIN SMS
            admin_msg = (
                f"NEW ORDER #{first_order.id}\n"
                f"{addr.full_name}, {addr.phone}\n"
                f"{addr.address_line_1}, {addr.city}\n"
                f"Amount: Rs.{sum(o.amount for o in orders)}"
            )

            try:
                send_sms(settings.ADMIN_PHONE, admin_msg)
            except Exception as e:
                logger.error("Admin SMS failed: %s", e)

            # CUSTOMER SMS
            for o in orders:
                try:
                    msg = (
                        f"Dear {o.delivery_address.full_name}, your order #{o.id} is confirmed. "
                        "Tracking details will be sent once shipped."
                    )
                    send_sms(o.delivery_address.phone, msg)
                except Exception as e:
                    logger.error("Customer SMS failed: %s", e)

        # Clear cart
        if request.user.is_authenticated:
            try:
                cart = Cart.objects.get(user=request.user)
                cart.items.all().delete()
            except Cart.DoesNotExist:
                pass

        return render(request, "thankyou.html", {
            "orders": orders,
            "total_amount": sum(order.amount for order in orders)
        })

    except Exception as e:
        logger.exception("Payment verification failed: %s", e)
        return render(request, "payment_failed.html")


# ---------------------------
# CART
# ---------------------------

@login_required
def cart_view(request):
    cart, created = Cart.objects.get_or_create(user=request.user)
    items = cart.items.all().select_related("saree")

    return render(request, "cart.html", {
        "cart": cart,
        "cart_items": items,
        "total_price": cart.get_total_price(),
        "total_items": cart.get_total_items(),
    })


@login_required
@require_POST
def add_to_cart(request, product_id):
    saree = get_object_or_404(Saree, id=product_id, available=True)
    cart, created = Cart.objects.get_or_create(user=request.user)

    item, created = CartItem.objects.get_or_create(cart=cart, saree=saree, defaults={"quantity": 1})

    if not created:
        return JsonResponse({"success": False, "message": "Already in cart"})

    return JsonResponse({"success": True, "message": "Added to cart"})


@login_required
@require_POST
def remove_from_cart(request, item_id):
    item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
    item.delete()
    return JsonResponse({"success": True})


# ---------------------------
# CHECKOUT FLOW
# ---------------------------

@login_required
def checkout_cart(request):
    return redirect("select_address_checkout")


@login_required
def clear_cart_after_payment(request):
    try:
        cart = Cart.objects.get(user=request.user)
        cart.items.all().delete()
    except Cart.DoesNotExist:
        pass

    return redirect("profile")


# ---------------------------
# AUTH
# ---------------------------

def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user)
            return redirect("/")
        else:
            messages.error(request, "Invalid credentials")

    return render(request, "auth/login.html")


def signup_view(request):
    if request.method == "POST":
        full_name = request.POST.get("full_name")
        username = request.POST.get("username")
        email = request.POST.get("email")
        mobile = request.POST.get("mobile_number")
        password = request.POST.get("password")
        confirm = request.POST.get("confirm_password")

        if password != confirm:
            messages.error(request, "Passwords do not match.")
            return render(request, "auth/signup.html")

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=full_name.split(" ")[0],
            last_name=" ".join(full_name.split(" ")[1:])
        )

        UserProfile.objects.create(user=user, mobile_number=mobile)

        login(request, user)
        return redirect("/")

    return render(request, "auth/signup.html")


def logout_view(request):
    logout(request)
    return redirect("/")


@login_required
def profile_view(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    orders = Order.objects.filter(user=request.user).order_by("-created_at")

    return render(request, "auth/profile.html", {"profile": profile, "orders": orders})


# ---------------------------
# ADDRESS MGMT
# ---------------------------

@login_required
def select_address_buy_now(request, product_id):
    saree = get_object_or_404(Saree, id=product_id)
    addresses = Address.objects.filter(user=request.user)

    if request.method == "POST":
        address_id = request.POST.get("address_id")
        request.session["selected_address_id"] = address_id
        request.session["product_id"] = product_id
        return redirect("process_buy_now_payment")

    return render(request, "address/select_address.html", {
        "saree": saree,
        "addresses": addresses,
        "is_buy_now": True
    })


@login_required
def select_address_checkout(request):
    cart = get_object_or_404(Cart, user=request.user)

    if not cart.items.exists():
        messages.warning(request, "Your cart is empty!")
        return redirect("cart")

    addresses = Address.objects.filter(user=request.user)

    if request.method == "POST":
        address_id = request.POST.get("address_id")
        request.session["selected_address_id"] = address_id
        return redirect("process_checkout_payment")

    return render(request, "address/select_address.html", {
        "addresses": addresses,
        "cart": cart,
        "is_checkout": True
    })


# ---------------------------
# ADD / EDIT / DELETE ADDRESS
# ---------------------------

@login_required
def add_address(request):
    if request.method == "POST":
        Address.objects.create(
            user=request.user,
            name=request.POST.get("name"),
            full_name=request.POST.get("full_name"),
            phone=request.POST.get("phone"),
            address_line_1=request.POST.get("address_line_1"),
            address_line_2=request.POST.get("address_line_2"),
            city=request.POST.get("city"),
            state=request.POST.get("state"),
            pincode=request.POST.get("pincode"),
        )

        return redirect("manage_addresses")

    return render(request, "address/add_address.html")


@login_required
def manage_addresses(request):
    addresses = Address.objects.filter(user=request.user)
    return render(request, "address/manage_addresses.html", {"addresses": addresses})


@login_required
def edit_address(request, address_id):
    address = get_object_or_404(Address, id=address_id, user=request.user)

    if request.method == "POST":
        address.name = request.POST.get("name")
        address.full_name = request.POST.get("full_name")
        address.phone = request.POST.get("phone")
        address.address_line_1 = request.POST.get("address_line_1")
        address.address_line_2 = request.POST.get("address_line_2")
        address.city = request.POST.get("city")
        address.state = request.POST.get("state")
        address.pincode = request.POST.get("pincode")
        address.save()
        return redirect("manage_addresses")

    return render(request, "address/edit_address.html", {"address": address})


@login_required
def delete_address(request, address_id):
    address = get_object_or_404(Address, id=address_id, user=request.user)

    if request.method == "POST":
        address.delete()
        return redirect("manage_addresses")

    return render(request, "address/delete_address.html", {"address": address})


# ---------------------------
# PAYMENT FOR BUY NOW
# ---------------------------

@login_required
def process_buy_now_payment(request):
    address_id = request.session.get("selected_address_id")
    product_id = request.session.get("product_id")

    address = get_object_or_404(Address, id=address_id, user=request.user)
    saree = get_object_or_404(Saree, id=product_id)

    amount = saree.price * 100

    razorpay_order = client.order.create({
        "amount": amount,
        "currency": "INR",
        "payment_capture": "1"
    })

    order = Order.objects.create(
        saree=saree,
        user=request.user,
        amount=saree.price,
        razorpay_order_id=razorpay_order["id"],
        delivery_address=address,
    )

    del request.session["selected_address_id"]
    del request.session["product_id"]

    return render(request, "payment.html", {
        "order": order,
        "order_id": razorpay_order["id"],
        "amount": amount,
        "razorpay_key": settings.RAZORPAY_KEY_ID,
        "saree": saree,
        "address": address
    })


# ---------------------------
# PAYMENT FOR CART CHECKOUT
# ---------------------------

@login_required
def process_checkout_payment(request):
    address_id = request.session.get("selected_address_id")
    address = get_object_or_404(Address, id=address_id, user=request.user)
    cart = get_object_or_404(Cart, user=request.user)

    total_amount = cart.get_total_price()
    razorpay_amount = total_amount * 100

    razorpay_order = client.order.create({
        "amount": razorpay_amount,
        "currency": "INR",
        "payment_capture": "1"
    })

    orders = []

    for item in cart.items.all():
        order = Order.objects.create(
            saree=item.saree,
            user=request.user,
            quantity=item.quantity,
            amount=item.get_total_price(),
            razorpay_order_id=razorpay_order["id"],
            delivery_address=address,
        )
        orders.append(order)

    del request.session["selected_address_id"]

    return render(request, "checkout.html", {
        "orders": orders,
        "cart": cart,
        "order_id": razorpay_order["id"],
        "amount": razorpay_amount,
        "total_amount": total_amount,
        "razorpay_key": settings.RAZORPAY_KEY_ID,
        "address": address
    })
