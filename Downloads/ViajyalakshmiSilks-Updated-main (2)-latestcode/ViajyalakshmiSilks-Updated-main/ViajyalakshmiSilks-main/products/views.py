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
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.db import models
import random
from django.template.loader import render_to_string
from django.core.mail import EmailMessage


# SMS util (optional)
try:
    from .sms_utils import send_sms
except Exception:
    def send_sms(to_phone, message, from_phone=None):
        logging.getLogger(__name__).warning("send_sms not available; SMS skipped.")
        return False

import razorpay
import stripe
from .models import Saree, Order, UserProfile, Cart, CartItem, Address, Collection, Coupon, SiteSettings

stripe.api_key = settings.STRIPE_SECRET_KEY

logger = logging.getLogger(__name__)


def home_view(request):
    featured_products = Saree.objects.filter(is_featured=True)[:8]
    new_arrivals = Saree.objects.filter(is_new_arrival=True).order_by('-created_at')[:8]
    home_collections = Collection.objects.filter(show_on_home=True, is_active=True).annotate(
        min_price=models.Min('products__price')
    ).order_by('-priority', 'name')
    
    context = {
        'featured_products': featured_products,
        'new_arrivals': new_arrivals,
        'home_collections': home_collections
    }
    return render(request, 'home.html', context)


def shop_view(request):
    """
    Shop view with filtering:
    - search (name or description)
    - category (auto-generated from saree name)
    - collection (by slug)
    - min_price, max_price
    """

    # Base queryset
    sarees = Saree.objects.filter(available=True).order_by('-id')
    collections = Collection.objects.filter(is_active=True)

    # ----------------------------------
    # AUTO CATEGORY GENERATION
    # ----------------------------------
    categories_set = set()

    for s in sarees:
        if not s.name:
            continue

        name = s.name.strip()
        name = " ".join(name.split())  # normalize spaces
        words = name.split(" ")

        # Take first 2 words as category (Soft Silk, Linen Cotton, etc.)
        if len(words) >= 2:
            category_name = f"{words[0]} {words[1]}"
        else:
            category_name = words[0]

        categories_set.add(category_name.title())

    categories = sorted(categories_set)

    # ----------------------------------
    # READ FILTERS
    # ----------------------------------
    search = request.GET.get('search', '').strip()
    category = request.GET.get('category', '').strip()
    collection_slug = request.GET.get('collection', '').strip()
    min_price = request.GET.get('min_price', '').strip()
    max_price = request.GET.get('max_price', '').strip()

    # ----------------------------------
    # APPLY SEARCH
    # ----------------------------------
    if search:
        sarees = sarees.filter(
            models.Q(name__icontains=search) |
            models.Q(description__icontains=search)
        )

    # ----------------------------------
    # APPLY CATEGORY FILTER
    # ----------------------------------
    if category:
        sarees = sarees.filter(name__istartswith=category)

    # ----------------------------------
    # APPLY COLLECTION FILTER
    # ----------------------------------
    if collection_slug:
        sarees = sarees.filter(collections__slug=collection_slug)

    # ----------------------------------
    # APPLY PRICE FILTER
    # ----------------------------------
    try:
        if min_price:
            sarees = sarees.filter(price__gte=int(min_price))
    except ValueError:
        pass

    try:
        if max_price:
            sarees = sarees.filter(price__lte=int(max_price))
    except ValueError:
        pass

    # ----------------------------------
    # CART ITEMS (for logged-in users)
    # ----------------------------------
    cart_items = []
    if request.user.is_authenticated:
        try:
            cart = Cart.objects.get(user=request.user)
            cart_items = list(cart.items.values_list('saree_id', flat=True))
        except Cart.DoesNotExist:
            pass

    return render(request, 'shop.html', {
        'sarees': sarees,
        'categories': categories,
        'collections': collections,
        'search': search,
        'category': category,
        'collection_slug': collection_slug,
        'min_price': min_price,
        'max_price': max_price,
        'cart_items': cart_items,
    })


@login_required
def buy_now(request, slug):
    return redirect('select_address_buy_now', slug=slug)

def collection_detail(request, slug):
    collection = get_object_or_404(Collection, slug=slug, is_active=True)
    products = collection.products.filter(available=True)
    
    # Cart items for UI
    cart_items = []
    if request.user.is_authenticated:
        try:
            cart = Cart.objects.get(user=request.user)
            cart_items = list(cart.items.values_list('saree_id', flat=True))
        except Cart.DoesNotExist:
            pass

    return render(request, 'collection_detail.html', {
        'collection': collection,
        'sarees': products,
        'cart_items': cart_items,
    })

def product_detail(request, slug):
    product = get_object_or_404(Saree, slug=slug)
    related_products = Saree.objects.filter(available=True).exclude(id=product.id)[:4]
    
    # SEO data
    meta_title = product.meta_title or f"{product.name} | Pure Kanchipuram Silk Saree"
    meta_desc = product.meta_description or product.description[:160]

    # Cart items for UI
    cart_items = []
    if request.user.is_authenticated:
        try:
            cart = Cart.objects.get(user=request.user)
            cart_items = list(cart.items.values_list('saree_id', flat=True))
        except Cart.DoesNotExist:
            pass

    return render(request, 'product_detail.html', {
        'saree': product,
        'related_products': related_products,
        'meta_title': meta_title,
        'meta_description': meta_desc,
        'cart_items': cart_items,
    })


@login_required
def payment_complete(request):
    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    if request.method == 'GET':
        order_id = request.GET.get('order_id')
        if order_id:
            orders = Order.objects.filter(razorpay_order_id=order_id, user=request.user)
            if orders.exists():
                base_total = sum(o.amount for o in orders)
                site_settings = SiteSettings.load()
                final_total = base_total
                if site_settings.tax_percentage > 0:
                    final_total += (final_total * float(site_settings.tax_percentage)) / 100
                if not getattr(site_settings, 'free_delivery_all_orders', False) and not (site_settings.enable_free_delivery and final_total >= site_settings.free_delivery_min):
                    final_total += site_settings.delivery_charge
                return render(request, 'thankyou.html', {'orders': orders, 'total_amount': final_total})
        return redirect('shop')

    payment_id = request.POST.get('razorpay_payment_id')
    order_id = request.POST.get('razorpay_order_id')
    signature = request.POST.get('razorpay_signature')

    orders = Order.objects.filter(razorpay_order_id=order_id)
    if not orders.exists():
        return render(request, 'payment_failed.html')

    params = {'razorpay_order_id': order_id, 'razorpay_payment_id': payment_id, 'razorpay_signature': signature}

    try:
        client.utility.verify_payment_signature(params)
        for order in orders:
            order.paid = True
            order.status = 'PROCESSING'
            order.razorpay_payment_id = payment_id
            order.razorpay_signature = signature
            order.save()

        payment_info = None
        try:
            if payment_id:
                payment_info = client.payment.fetch(payment_id)
        except Exception as e:
            logger.warning("Could not fetch Razorpay payment details: %s", e)
            payment_info = None

        try:
            from .email_utils import send_order_notification_to_admin, send_customer_receipt, send_admin_order_email
        except Exception as e:
            logger.warning("Custom email utilities not present or failed to import: %s", e)
            send_order_notification_to_admin = None
            send_customer_receipt = None
            send_admin_order_email = None

        try:
            if callable(send_admin_order_email):
                try:
                    send_admin_order_email(orders)
                except Exception as e:
                    logger.error("send_admin_order_email failed: %s", e)
            else:
                first_order = orders.first()
                if first_order and getattr(first_order, 'delivery_address', None):
                    addr = first_order.delivery_address
                    product_list = ", ".join([f"{o.saree.name} (x{o.quantity or 1})" for o in orders])
                    total_amount = sum(o.amount for o in orders)
                    admin_subject = f"NEW ORDER #{first_order.id}"
                    admin_body = (
                        f"Name: {addr.full_name}\nPhone: {addr.phone}\nAddress: {addr.address_line_1}"
                        + (f", {addr.address_line_2}" if addr.address_line_2 else "") +
                        f", {addr.city}, {addr.state} - {addr.pincode}\n\n"
                        f"Items: {product_list}\nAmount: Rs.{total_amount}\n"
                        f"Payment ID: {payment_id or 'N/A'}\n")
                    admin_email = getattr(settings, 'ADMIN_EMAIL', None)
                    if admin_email:
                        try:
                            send_mail(admin_subject, admin_body, settings.DEFAULT_FROM_EMAIL, [admin_email])
                        except Exception as e:
                            logger.error("Failed to send fallback admin email: %s", e)
        except Exception as e:
            logger.error("Admin notification error: %s", e)

        for order in orders:
            try:
                if callable(send_customer_receipt):
                    try:
                        info = payment_info or {'id': payment_id or order.razorpay_payment_id or 'N/A',
                                                'method': payment_info.get('method') if payment_info else 'N/A',
                                                'status': payment_info.get('status') if payment_info else 'success',
                                                'amount': payment_info.get('amount') if payment_info else order.amount}
                        send_customer_receipt(order, info)
                    except Exception as e:
                        logger.error("send_customer_receipt failed for order %s: %s", order.id, e)

                customer_email = None
                if order.user and getattr(order.user, 'email', None):
                    customer_email = order.user.email

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
                            amt = int(payment_info.get('amount', 0)) / 100 if payment_info.get('amount') else order.amount
                            body_lines += [
                                f"Amount (INR): {amt}",
                                f"Method: {payment_info.get('method', 'N/A')}",
                                f"Status: {payment_info.get('status', 'N/A')}",
                            ]
                        else:
                            body_lines += [f"Amount (INR): {order.amount}"]
                        body_lines += ["", "This is an automated receipt from Vijayalakshmi Silks.", "If you have any questions reply to this email."]
                        body = "\n".join(body_lines)
                        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [customer_email])
                    except Exception as e:
                        logger.error("Failed to send direct payment receipt email for order %s: %s", order.id, e)
            except Exception as e:
                logger.error("Customer email error for order %s: %s", order.id, e)

        # SMS Notifications are now handled in verify_razorpay_payment or the respective payment flow
        pass

        if request.user.is_authenticated:
            try:
                cart = Cart.objects.get(user=request.user)
                cart.items.all().delete()
            except Cart.DoesNotExist:
                pass

        base_total = sum(order.amount for order in orders)
        site_settings = SiteSettings.load()
        final_total = base_total
        if site_settings.tax_percentage > 0:
            final_total += (final_total * float(site_settings.tax_percentage)) / 100
        if not getattr(site_settings, 'free_delivery_all_orders', False) and not (site_settings.enable_free_delivery and final_total >= site_settings.free_delivery_min):
            final_total += site_settings.delivery_charge
            
        return render(request, 'thankyou.html', {'orders': orders, 'total_amount': final_total})

    except Exception as e:
        logger.exception("Payment verification failed: %s", e)
        return render(request, 'payment_failed.html')


@login_required
def cart_view(request):
    cart, created = Cart.objects.get_or_create(user=request.user)
    cart_items = cart.items.all().select_related('saree')
    request.session.pop('product_id', None)
    
    total_price = cart.get_total_price()
    discount_amount = 0
    coupon_code = request.session.get('applied_coupon')
    applied_coupon = None
    
    if coupon_code:
        from .models import Coupon
        from django.utils import timezone
        applied_coupon = Coupon.objects.filter(code=coupon_code, active=True, expiry_date__gt=timezone.now()).first()
        if applied_coupon:
            if total_price >= applied_coupon.min_purchase_amount:
                if applied_coupon.discount_type == 'PERCENTAGE':
                    discount_amount = (total_price * applied_coupon.discount_value) / 100
                else:
                    discount_amount = applied_coupon.discount_value
            else:
                del request.session['applied_coupon']
                messages.warning(request, f"Coupon '{coupon_code}' removed as it requires min. purchase of {applied_coupon.min_purchase_amount}")
                applied_coupon = None

    grand_total = total_price - discount_amount
    site_settings = SiteSettings.load()
    tax_amount = 0
    if site_settings.tax_percentage > 0:
        tax_amount = (grand_total * float(site_settings.tax_percentage)) / 100
        grand_total += tax_amount
        
    context = {
        'cart': cart, 
        'cart_items': cart_items, 
        'total_price': total_price, 
        'discount_amount': discount_amount,
        'tax_amount': tax_amount,
        'grand_total': grand_total,
        'applied_coupon': applied_coupon,
        'total_items': cart.get_total_items(),
        'site_settings': site_settings
    }
    return render(request, 'cart.html', context)

@login_required
@require_POST
def apply_coupon(request):
    code = request.POST.get('coupon_code', '').strip().upper()
    if not code:
        messages.error(request, "Please enter a coupon code.")
        return redirect('cart')
        
    from .models import Coupon
    from django.utils import timezone
    coupon = Coupon.objects.filter(code=code, active=True, expiry_date__gt=timezone.now()).first()
    
    if not coupon:
        messages.error(request, "Invalid or expired coupon code.")
        return redirect('cart')
        
    cart = get_object_or_404(Cart, user=request.user)
    if cart.get_total_price() < coupon.min_purchase_amount:
        messages.error(request, f"This coupon requires a minimum purchase of {coupon.min_purchase_amount}.")
        return redirect('cart')
        
    request.session['applied_coupon'] = coupon.code
    messages.success(request, f"Coupon '{coupon.code}' applied successfully!")
    return redirect('cart')

@login_required
@require_POST
def remove_coupon(request):
    if 'applied_coupon' in request.session:
        del request.session['applied_coupon']
        messages.success(request, "Coupon removed.")
    return redirect('cart')



@login_required
@require_POST
def add_to_cart(request, slug):
    saree = get_object_or_404(Saree, slug=slug, available=True)
    cart, created = Cart.objects.get_or_create(user=request.user)
    cart_item, created = CartItem.objects.get_or_create(cart=cart, saree=saree, defaults={'quantity': 1})
    if not created:
        cart_item.quantity += 1
        cart_item.save()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': f'Another {saree.name} added to cart!', 'cart_total_items': cart.get_total_items(), 'cart_items_count': cart.get_items_count()})
        messages.success(request, f'Another {saree.name} has been added to your cart!')
        return redirect('cart')
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': f'{saree.name} added to cart!', 'cart_total_items': cart.get_total_items(), 'cart_items_count': cart.get_items_count()})
    messages.success(request, f'{saree.name} has been added to your cart!')
    return redirect('shop')


@login_required
@require_POST
def remove_from_cart(request, item_id):
    try:
        cart_item = CartItem.objects.get(id=item_id, cart__user=request.user)
        saree_name = cart_item.saree.name
        cart = cart_item.cart
        cart_item.delete()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True, 
                'message': f'{saree_name} removed from cart!', 
                'cart_total_items': cart.get_total_items(), 
                'cart_total': cart.get_total_price()
            })
        messages.success(request, f'{saree_name} has been removed from your cart!')
    except CartItem.DoesNotExist:
        # If already removed, just redirect back to cart gracefully
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Item already removed.'})
        messages.info(request, 'Item was already removed from your cart.')
    
    return redirect('cart')



@login_required
@require_POST
def update_cart_quantity(request):
    import json
    try:
        data = json.loads(request.body)
        item_id = data.get('item_id')
        action = data.get('action')  # 'increase' or 'decrease'
        
        try:
            cart_item = CartItem.objects.get(id=item_id, cart__user=request.user)
        except CartItem.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Item not found in your cart.'})

        
        cart = cart_item.cart
        if action == 'increase':
            if cart_item.quantity + 1 > cart_item.saree.stock_quantity:
                return JsonResponse({'success': False, 'error': f'Only {cart_item.saree.stock_quantity} items left in stock.'})
            cart_item.quantity += 1
            cart_item.save()
        elif action == 'decrease':
            if cart_item.quantity > 1:
                cart_item.quantity -= 1
                cart_item.save()
            else:
                cart_item.delete()
                return JsonResponse({
                    'success': True,
                    'removed': True,
                    'cart_total_items': cart.get_total_items(),
                    'cart_total': cart.get_total_price()
                })
        
        return JsonResponse({
            'success': True,
            'item_quantity': cart_item.quantity,
            'item_total': cart_item.get_total_price(),
            'cart_total': cart.get_total_price(),
            'cart_total_items': cart.get_total_items()
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


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


def login_view(request):
    if request.method == 'POST':
        login_id = request.POST.get('login_id')
        password = request.POST.get('password')
        user = authenticate(request, username=login_id, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f'Welcome back, {user.first_name or user.username}!')
            return redirect('/')
        else:
            messages.error(request, 'Invalid email/mobile number or password.')
    return render(request, 'auth/login.html')



def signup_view(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '')
        email = request.POST.get('email')
        mobile_number = request.POST.get('mobile_number')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        
        if password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'auth/signup.html')
        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, 'Email already exists.')
            return render(request, 'auth/signup.html')
        if UserProfile.objects.filter(mobile_number=mobile_number).exists():
            messages.error(request, 'Mobile number already exists.')
            return render(request, 'auth/signup.html')
            
        # Generate unique username from email
        base_username = email.split('@')[0]
        username = base_username
        counter = 1
        while User.objects.filter(username__iexact=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
            
        # Generate OTP
        email_otp = str(random.randint(100000, 999999))
        
        # Store data in session
        request.session['signup_data'] = {
            'full_name': full_name,
            'username': username,
            'email': email,
            'mobile_number': mobile_number,
            'password': password
        }
        request.session['email_otp'] = email_otp
        request.session['otp_flow'] = 'signup'
        request.session.modified = True
        
        # Send Email OTP
        try:
            from products.models import SiteSettings
            site_settings = SiteSettings.load()
            
            email = email.strip()
            subject = "Verify Your Account - Vijayalakshmi Silks"
            html_content = render_to_string('email/otp_email.html', {
                'otp': email_otp,
                'site_settings': site_settings
            })
            
            # Use authenticated email as FROM, but dashboard email as REPLY-TO
            from django.core.mail import EmailMultiAlternatives
            msg = EmailMultiAlternatives(
                subject,
                f"Your verification code is {email_otp}.",
                settings.DEFAULT_FROM_EMAIL,
                [email],
                reply_to=[site_settings.email] if site_settings.email else None
            )
            msg.attach_alternative(html_content, "text/html")
            
            print(f"DEBUG: Attempting to send signup OTP to {email} from {settings.DEFAULT_FROM_EMAIL} (Reply-To: {site_settings.email})")
            msg.send()
            
            print(f"DEBUG: Email reported success for {email}")
            logger.info(f"OTP email sent successfully to {email}")
        except Exception as e:
            print(f"DEBUG: Email FAILED for {email}: {str(e)}")
            logger.exception(f"Error sending OTP email to {email}: {e}")
            print(f"\n\n[DEBUG] SIGNUP EMAIL OTP (SMTP Failed) for {email}: {email_otp}\n\n", flush=True)
            messages.warning(request, f"We encountered an issue sending the email to {email}. If it's not in your inbox/spam, please see console logs.")
            
        messages.success(request, f'A verification code has been generated. Proceeding to verification.')
        return redirect('verify_signup_otp')
            
    return render(request, 'auth/signup.html')


def verify_signup_otp(request):
    email_otp = request.session.get('email_otp')
    
    if not email_otp:
        messages.error(request, 'Session expired. Please try again.')
        return redirect('signup')
        
    if request.method == 'POST':
        user_email_otp = request.POST.get('email_otp')
        
        if user_email_otp == email_otp:
            data = request.session.get('signup_data')
            if not data: return redirect('signup')
            try:
                with transaction.atomic():
                    name_parts = data.get('full_name', '').split(' ', 1)
                    first_name = name_parts[0] if name_parts else ''
                    last_name = name_parts[1] if len(name_parts) > 1 else ''
                    
                    user = User.objects.create_user(
                        username=data['username'],
                        email=data['email'],
                        password=data['password'],
                        first_name=first_name,
                        last_name=last_name
                    )
                    UserProfile.objects.create(user=user, mobile_number=data['mobile_number'])
                
                # Cleanup session
                if 'signup_data' in request.session: del request.session['signup_data']
                if 'email_otp' in request.session: del request.session['email_otp']
                if 'otp_flow' in request.session: del request.session['otp_flow']
                
                messages.success(request, 'Account created successfully! Please login to continue.')
                return redirect('login')
            except Exception as e:
                logger.error(f"Signup error: {e}")
                messages.error(request, 'Error creating account.')
        else:
            messages.error(request, 'Invalid OTP. Please check your email messages.')
            
    data = request.session.get('signup_data', {})
    email = data.get('email', '')
    mobile_number = data.get('mobile_number', '')
            
    return render(request, 'auth/verify_otp.html', {'email': email, 'mobile_number': mobile_number})




def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('/')


def forgot_password(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        if not User.objects.filter(email__iexact=email).exists():
            # Don't reveal if email exists or not for security, just say OTP sent
            messages.success(request, f'If an account exists with {email}, an OTP has been sent.')
            # But we only actually send it if it exists
            return render(request, 'auth/forgot_password.html')
            
        otp = str(random.randint(100000, 999999))
        request.session['reset_otp'] = otp
        request.session['reset_email'] = email
        print(f"\n\nDEBUG RESET OTP: {otp}\n\n")
        
        try:
            from products.models import SiteSettings
            site_settings = SiteSettings.load()
            
            subject = "Password Reset OTP - Vijayalakshmi Silks"
            html_content = render_to_string('email/otp_email.html', {
                'otp': otp,
                'site_settings': site_settings
            })
            
            from django.core.mail import EmailMultiAlternatives
            msg = EmailMultiAlternatives(
                subject,
                f"Your password reset code is {otp}.",
                settings.DEFAULT_FROM_EMAIL,
                [email],
                reply_to=[site_settings.email] if site_settings.email else None
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send()
            
            logger.info(f"Password reset OTP sent successfully to {email}")
            messages.success(request, f'An OTP has been sent to {email}.')
            return redirect('reset_password')
        except Exception as e:
            logger.exception(f"Error sending password reset OTP to {email}: {e}")
            print(f"\n\nDEBUG RESET OTP (SMTP Failed): {otp}\n\n")
            messages.warning(request, 'SMTP error occurred. Please check your console or try again later.')
            
        return redirect('reset_password')
            
    return render(request, 'auth/forgot_password.html')


def reset_password(request):
    if 'reset_email' not in request.session or 'reset_otp' not in request.session:
        messages.error(request, 'Session expired. Please request a new OTP.')
        return redirect('forgot_password')
        
    if request.method == 'POST':
        user_otp = request.POST.get('otp')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        if new_password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'auth/reset_password.html')
            
        if user_otp == request.session['reset_otp']:
            email = request.session['reset_email']
            user = User.objects.filter(email__iexact=email).first()
            if user:
                user.set_password(new_password)
                user.save()
                del request.session['reset_otp']
                del request.session['reset_email']
                messages.success(request, 'Your password has been reset successfully. You can now login.')
                return redirect('login')
        else:
            messages.error(request, 'Invalid OTP. Please try again.')
            
    return render(request, 'auth/reset_password.html')


@login_required
def profile_view(request):
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user, mobile_number='')
    
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        mobile_number = request.POST.get('mobile_number', '').strip()
        
        # Update User model (Full Name)
        if full_name:
            name_parts = full_name.split(' ', 1)
            request.user.first_name = name_parts[0]
            request.user.last_name = name_parts[1] if len(name_parts) > 1 else ''
            request.user.save()
            
        # Update Profile model (Mobile Number)
        profile.mobile_number = mobile_number
        profile.save()
        
        messages.success(request, 'Profile updated successfully!')
        return redirect('profile')

    from django.db.models import Q
    user_orders = Order.objects.filter(Q(user=request.user) & (Q(paid=True) | Q(razorpay_payment_id='COD'))).order_by('-created_at')
    context = {'user': request.user, 'profile': profile, 'orders': user_orders}
    return render(request, 'auth/profile.html', context)


@login_required
def order_detail_view(request, order_id):
    from django.db.models import Q
    order = get_object_or_404(Order, Q(id=order_id, user=request.user) & (Q(paid=True) | Q(razorpay_payment_id='COD')))
    return render(request, 'order_detail.html', {'order': order})


@login_required
def select_address_buy_now(request, slug):
    saree = get_object_or_404(Saree, slug=slug, available=True)
    user_addresses = Address.objects.filter(user=request.user)
    if request.method == 'POST':
        address_id = request.POST.get('address_id')
        if address_id:
            address = get_object_or_404(Address, id=address_id, user=request.user)
            request.session['selected_address_id'] = address.id
            request.session['product_id'] = slug
            return redirect('process_buy_now_payment')
    context = {'saree': saree, 'addresses': user_addresses, 'is_buy_now': True}
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
            request.session.pop('product_id', None)
            return redirect('process_checkout_payment')
    context = {'cart': cart, 'addresses': user_addresses, 'is_checkout': True}
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
            Address.objects.create(user=request.user, name=name, full_name=full_name, phone=phone, address_line_1=address_line_1, address_line_2=address_line_2, city=city, state=state, pincode=pincode, is_default=is_default)
            messages.success(request, 'Address added successfully!')
            action = request.GET.get('action')
            if action == 'buy_now':
                product_id = request.GET.get('product_id')
                if product_id:
                    return redirect('select_address_buy_now', slug=product_id)
            elif action == 'checkout':
                return redirect('select_address_checkout')
            return redirect('manage_addresses')
        except Exception:
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
        except Exception:
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
    saree = get_object_or_404(Saree, slug=product_id, available=True)
    
    total_price = saree.price
    discount_amount = 0
    coupon_code = request.session.get('applied_coupon')
    applied_coupon = None
    
    if coupon_code:
        from django.utils import timezone
        from .models import Coupon
        applied_coupon = Coupon.objects.filter(code=coupon_code, active=True, expiry_date__gt=timezone.now()).first()
        if applied_coupon:
            if total_price >= applied_coupon.min_purchase_amount:
                if applied_coupon.discount_type == 'PERCENTAGE':
                    discount_amount = (total_price * applied_coupon.discount_value) / 100
                else:
                    discount_amount = applied_coupon.discount_value
            else:
                applied_coupon = None
                
    site_settings = SiteSettings.load()
    final_total = total_price - discount_amount
    tax_amount = 0
    if site_settings.tax_percentage > 0:
        tax_amount = (final_total * float(site_settings.tax_percentage)) / 100
        final_total += tax_amount

    context = {
        'saree': saree,
        'address': address,
        'is_buy_now': True,
        'total_amount': total_price,
        'discount_amount': discount_amount,
        'tax_amount': tax_amount,
        'applied_coupon': applied_coupon,
        'final_total': final_total,
        'stripe_publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
        'site_settings': site_settings
    }
    return render(request, 'checkout.html', context)


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
    
    total_price = cart.get_total_price()
    discount_amount = 0
    coupon_code = request.session.get('applied_coupon')
    applied_coupon = None
    
    if coupon_code:
        from django.utils import timezone
        from .models import Coupon
        applied_coupon = Coupon.objects.filter(code=coupon_code, active=True, expiry_date__gt=timezone.now()).first()
        if applied_coupon:
            if total_price >= applied_coupon.min_purchase_amount:
                if applied_coupon.discount_type == 'PERCENTAGE':
                    discount_amount = (total_price * applied_coupon.discount_value) / 100
                else:
                    discount_amount = applied_coupon.discount_value
            else:
                applied_coupon = None
                
    site_settings = SiteSettings.load()
    final_total = total_price - discount_amount
    tax_amount = 0
    if site_settings.tax_percentage > 0:
        tax_amount = (final_total * float(site_settings.tax_percentage)) / 100
        final_total += tax_amount

    context = {
        'cart': cart,
        'orders': cart.items.all(), 
        'address': address,
        'total_amount': total_price,
        'discount_amount': discount_amount,
        'tax_amount': tax_amount,
        'applied_coupon': applied_coupon,
        'final_total': final_total,
        'stripe_publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
        'site_settings': site_settings
    }
    return render(request, 'checkout.html', context)


@login_required
def create_stripe_session(request):
    address_id = request.session.get('selected_address_id')
    if not address_id:
        return JsonResponse({'error': 'Session expired'}, status=400)
        
    # Check if it's Buy Now or Cart Checkout
    product_id = request.session.get('product_id')
    
    line_items = []
    metadata = {'address_id': address_id}
    
    if product_id:
        saree = get_object_or_404(Saree, id=product_id, available=True)
        line_items.append({
            'price_data': {
                'currency': 'inr',
                'product_data': {'name': saree.name},
                'unit_amount': int(saree.price * 100),
            },
            'quantity': 1,
        })
        metadata['type'] = 'buy_now'
        metadata['product_id'] = product_id
    else:
        cart = get_object_or_404(Cart, user=request.user)
        for item in cart.items.all():
            line_items.append({
                'price_data': {
                    'currency': 'inr',
                    'product_data': {'name': item.saree.name},
                    'unit_amount': int(item.saree.price * 100),
                },
                'quantity': item.quantity,
            })
        metadata['type'] = 'cart_checkout'

    # Handle Coupon Discount for Stripe
    applied_coupon = None
    discount_total = 0
    if not product_id:
        coupon_code = request.session.get('applied_coupon')
        if coupon_code:
            from .models import Coupon
            from django.utils import timezone
            applied_coupon = Coupon.objects.filter(code=coupon_code, active=True, expiry_date__gt=timezone.now()).first()
            if applied_coupon:
                cart = get_object_or_404(Cart, user=request.user)
                subtotal = cart.get_total_price()
                if applied_coupon.discount_type == 'PERCENTAGE':
                    discount_total = (subtotal * applied_coupon.discount_value) / 100
                else:
                    discount_total = applied_coupon.discount_value
                
                # Add discount as a negative line item
                line_items.append({
                    'price_data': {
                        'currency': 'inr',
                        'product_data': {'name': f'Discount ({applied_coupon.code})'},
                        'unit_amount': -int(discount_total * 100),
                    },
                    'quantity': 1,
                })
                metadata['coupon_code'] = coupon_code
                metadata['discount_amount'] = str(discount_total)

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=line_items,
            mode='payment',
            success_url=request.build_absolute_uri('/stripe-success/') + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=request.build_absolute_uri('/stripe-cancel/'),
            metadata=metadata
        )
        return JsonResponse({'id': checkout_session.id})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def stripe_success(request):
    session_id = request.GET.get('session_id')
    if not session_id:
        return redirect('home')
        
    session = stripe.checkout.Session.retrieve(session_id)
    metadata = session.metadata
    user = request.user
    
    orders = []
    with transaction.atomic():
        address = Address.objects.get(id=metadata['address_id'])
        
        if metadata['type'] == 'buy_now':
            saree = Saree.objects.get(id=metadata['product_id'])
            order = Order.objects.create(
                saree=saree,
                user=user,
                quantity=1,
                amount=saree.price,
                paid=True,
                status='PROCESSING',
                delivery_address=address,
                razorpay_payment_id=session.payment_intent # Storing stripe payment intent in the old field for compatibility or renaming later
            )
            saree.stock_quantity = max(0, saree.stock_quantity - 1)
            if saree.stock_quantity == 0:
                saree.available = False
            saree.save()
            orders.append(order)
        else:
            cart = Cart.objects.get(user=user)
            subtotal = cart.get_total_price()
            discount_total = float(metadata.get('discount_amount', 0))
            
            for item in cart.items.all():
                # Pro-rate discount
                item_price = item.get_total_price()
                item_discount = (item_price / subtotal) * discount_total if subtotal > 0 else 0
                
                order = Order.objects.create(
                    saree=item.saree,
                    user=user,
                    quantity=item.quantity,
                    amount=item_price - item_discount,
                    paid=True,
                    status='PROCESSING',
                    delivery_address=address,
                    razorpay_payment_id=session.payment_intent
                )
                saree = item.saree
                saree.stock_quantity = max(0, saree.stock_quantity - item.quantity)
                if saree.stock_quantity == 0:
                    saree.available = False
                saree.save()
                orders.append(order)
            cart.items.all().delete()
            if 'applied_coupon' in request.session:
                del request.session['applied_coupon']


    base_total = sum(o.amount for o in orders)
    site_settings = SiteSettings.load()
    final_total = base_total
    if site_settings.tax_percentage > 0:
        final_total += (final_total * float(site_settings.tax_percentage)) / 100
    if not getattr(site_settings, 'free_delivery_all_orders', False) and not (site_settings.enable_free_delivery and final_total >= site_settings.free_delivery_min):
        final_total += site_settings.delivery_charge

    # -----------------------
    # SEND CONFIRMATION EMAILS
    # -----------------------
    try:
        from .email_utils import send_customer_receipt, send_admin_order_email
        try:
            send_admin_order_email(orders)
        except Exception as e:
            logger.error("send_admin_order_email failed in stripe flow: %s", e)
            
        for order in orders:
            try:
                info = {
                    'id': session_id,
                    'method': 'Stripe',
                    'status': 'success',
                    'amount': order.amount
                }
                send_customer_receipt(order, info)
            except Exception as e:
                logger.error("send_customer_receipt failed for order %s in stripe flow: %s", order.id, e)
    except Exception as e:
        logger.error("Email notification failure in stripe flow: %s", e)

    # -----------------------
    # SMS Notifications
    # -----------------------
    try:
        if site_settings.enable_sms_notifications or getattr(settings, "ENABLE_SMS", False):
            first_order = orders[0] if orders else None
            if first_order and first_order.delivery_address:
                addr = first_order.delivery_address
                product_list = ", ".join([f"{o.saree.name} (x{o.quantity or 1})" for o in orders])
                
                # 1. Admin SMS
                admin_phone = site_settings.admin_phone or getattr(settings, "ADMIN_PHONE", None)
                admin_msg = (
                    f"NEW STRIPE ORDER #{first_order.id}\n"
                    f"{addr.full_name}, {addr.phone}\n"
                    f"{addr.address_line_1}, {addr.city}\n"
                    f"Items: {product_list}\n"
                    f"Total: Rs.{int(final_total)}"
                )
                try:
                    if admin_phone:
                        send_sms(admin_phone, admin_msg)
                except Exception as e:
                    logger.error("Admin SMS failed in stripe flow: %s", e)

                # 2. Customer SMS
                try:
                    if addr.phone:
                        base_url = settings.SITE_URL
                        cust_msg = (
                            f"Hi {addr.full_name}, your order #{first_order.id} for Rs.{int(final_total)} is confirmed. "
                            f"Items: {product_list}. Track here: {base_url}/order/{first_order.id}/ - Vijayalakshmi Silks"
                        )
                        send_sms(addr.phone, cust_msg)
                except Exception as e:
                    logger.error("Customer SMS failed in stripe flow: %s", e)
    except Exception as e:
        logger.error("SMS notification section failed in stripe flow: %s", e)

    return render(request, 'thankyou.html', {
        'orders': orders,
        'total_amount': final_total
    })


@login_required
def stripe_cancel(request):
    messages.warning(request, 'Payment was cancelled.')
    return redirect('cart')


@login_required
def custom_test_payment(request):
    from products.models import SiteSettings
    address_id = request.session.get('selected_address_id')
    product_id = request.session.get('product_id')
    
    if not address_id:
        messages.error(request, 'Session expired.')
        return redirect('cart')
        
    address = get_object_or_404(Address, id=address_id, user=request.user)
    site_settings = SiteSettings.load()
    
    total_amount = 0
    items_display = []
    
    if product_id:
        saree = get_object_or_404(Saree, slug=product_id)
        total_amount = saree.price
        items_display.append({'name': saree.name, 'price': saree.price, 'qty': 1})
    else:
        cart = get_object_or_404(Cart, user=request.user)
        total_amount = cart.get_total_price()
        for item in cart.items.all():
            items_display.append({'name': item.saree.name, 'price': item.saree.price, 'qty': item.quantity})
            
    # Apply coupon discount
    discount_amount = 0
    coupon_code = request.session.get('applied_coupon')
    if coupon_code:
        from django.utils import timezone
        from .models import Coupon
        applied_coupon = Coupon.objects.filter(code=coupon_code, active=True, expiry_date__gt=timezone.now()).first()
        if applied_coupon and total_amount >= applied_coupon.min_purchase_amount:
            if applied_coupon.discount_type == 'PERCENTAGE':
                discount_amount = (total_amount * applied_coupon.discount_value) / 100
            else:
                discount_amount = applied_coupon.discount_value
                
    final_total = total_amount - discount_amount
    
    tax_amount = 0
    if site_settings.tax_percentage > 0:
        tax_amount = (final_total * float(site_settings.tax_percentage)) / 100
        final_total += tax_amount
        
    # Apply Delivery Charge
    if not getattr(site_settings, 'free_delivery_all_orders', False) and not (site_settings.enable_free_delivery and final_total >= site_settings.free_delivery_min):
        final_total += site_settings.delivery_charge
        
    action = request.POST.get('action') if request.method == 'POST' else None
    
    # Apply COD charge if applicable
    if action == 'cod':
        final_total += getattr(site_settings, 'cod_charge', 50)

    if request.method == 'POST':
        if action in ['approve', 'cod']:
            is_paid = (action == 'approve')
            order_status = 'PROCESSING' if action == 'approve' else 'PENDING'
            payment_id = f"TEST_PAY_{random.randint(1000,9999)}" if action == 'approve' else "COD"
            
            orders = []
            with transaction.atomic():
                if product_id:
                    saree = Saree.objects.get(slug=product_id)
                    order = Order.objects.create(
                        saree=saree, user=request.user, quantity=1,
                        amount=final_total, paid=is_paid, 
                        status=order_status,
                        delivery_address=address, 
                        razorpay_payment_id=payment_id
                    )
                    saree.stock_quantity = max(0, saree.stock_quantity - 1)
                    if saree.stock_quantity == 0:
                        saree.available = False
                    saree.save()
                    orders.append(order)
                else:
                    cart = Cart.objects.get(user=request.user)
                    cart_total = cart.get_total_price()
                    for item in cart.items.all():
                        item_price = item.get_total_price()
                        if cart_total > 0:
                            proportional_discount = (item_price / cart_total) * discount_amount
                        else:
                            proportional_discount = 0
                        
                        order_amount = max(0, int(item_price - proportional_discount))
                        
                        order = Order.objects.create(
                            saree=item.saree, user=request.user, quantity=item.quantity,
                            amount=order_amount, paid=is_paid, 
                            status=order_status,
                            delivery_address=address, 
                            razorpay_payment_id=payment_id
                        )
                        saree = item.saree
                        saree.stock_quantity = max(0, saree.stock_quantity - item.quantity)
                        if saree.stock_quantity == 0:
                            saree.available = False
                        saree.save()
                        orders.append(order)
                    
                    if orders:
                        total_overhead = final_total - sum(o.amount for o in orders)
                        if total_overhead != 0:
                            orders[0].amount += total_overhead
                            orders[0].save()
                    
                    request.session.pop('applied_coupon', None)
                    cart.items.all().delete()
            
            # -----------------------
            # SEND CONFIRMATION EMAILS
            # -----------------------
            try:
                from .email_utils import send_customer_receipt, send_admin_order_email
                
                try:
                    send_admin_order_email(orders)
                except Exception as e:
                    logger.error("send_admin_order_email failed in test gateway: %s", e)
                    
                for order in orders:
                    try:
                        info = {
                            'id': payment_id,
                            'method': 'COD' if action == 'cod' else 'Online',
                            'status': 'success',
                            'amount': order.amount
                        }
                        send_customer_receipt(order, info)
                    except Exception as e:
                        logger.error("send_customer_receipt failed for order %s in test gateway: %s", order.id, e)
            except Exception as e:
                logger.error("Email notification failure in test gateway: %s", e)

            # -----------------------
            # SMS Notifications
            # -----------------------
            try:
                if site_settings.enable_sms_notifications or getattr(settings, "ENABLE_SMS", False):
                    first_order = orders[0] if orders else None
                    if first_order and first_order.delivery_address:
                        addr = first_order.delivery_address
                        product_list = ", ".join([f"{o.saree.name} (x{o.quantity or 1})" for o in orders])
                        
                        # 1. Admin SMS
                        admin_phone = site_settings.admin_phone or getattr(settings, "ADMIN_PHONE", None)
                        admin_msg = (
                            f"NEW {'COD ' if action == 'cod' else ''}ORDER #{first_order.id}\n"
                            f"{addr.full_name}, {addr.phone}\n"
                            f"{addr.address_line_1}, {addr.city}\n"
                            f"Items: {product_list}\n"
                            f"Total: Rs.{int(final_total)}"
                        )
                        try:
                            if admin_phone:
                                send_sms(admin_phone, admin_msg)
                        except Exception as e:
                            logger.error("Admin SMS failed in test gateway: %s", e)

                        # 2. Customer SMS
                        try:
                            if addr.phone:
                                base_url = settings.SITE_URL
                                cust_msg = (
                                    f"Hi {addr.full_name}, your order #{first_order.id} for Rs.{int(final_total)} is confirmed ({'COD' if action == 'cod' else 'Paid'}). "
                                    f"Items: {product_list}. Track here: {base_url}/order/{first_order.id}/ - Vijayalakshmi Silks"
                                )
                                send_sms(addr.phone, cust_msg)
                        except Exception as e:
                            logger.error("Customer SMS failed in test gateway: %s", e)
            except Exception as e:
                logger.error("SMS notification section failed in test gateway: %s", e)

            if action == 'cod':
                messages.success(request, "Order placed successfully via Cash on Delivery!")
            return render(request, 'thankyou.html', {'orders': orders, 'total_amount': final_total})
        else:
            messages.warning(request, 'Payment was declined.')
            return redirect('cart')

    return render(request, 'auth/test_payment.html', {
        'address': address,
        'total_amount': total_amount,
        'items': items_display
    })

from django.views.decorators.csrf import csrf_exempt

@login_required
def initiate_razorpay_checkout(request):
    import razorpay
    from django.conf import settings
    
    address_id = request.session.get('selected_address_id')
    product_id = request.session.get('product_id')
    
    if not address_id:
        return JsonResponse({'error': 'Session expired. No address selected.'}, status=400)
        
    address = get_object_or_404(Address, id=address_id, user=request.user)
    
    total_price = 0
    if product_id:
        saree = get_object_or_404(Saree, slug=product_id, available=True)
        total_price = saree.price
    else:
        cart = get_object_or_404(Cart, user=request.user)
        total_price = cart.get_total_price()
        
    # Apply coupon discount
    discount_amount = 0
    coupon_code = request.session.get('applied_coupon')
    if coupon_code:
        from django.utils import timezone
        from .models import Coupon
        applied_coupon = Coupon.objects.filter(code=coupon_code, active=True, expiry_date__gt=timezone.now()).first()
        if applied_coupon and total_price >= applied_coupon.min_purchase_amount:
            if applied_coupon.discount_type == 'PERCENTAGE':
                discount_amount = (total_price * applied_coupon.discount_value) / 100
            else:
                discount_amount = applied_coupon.discount_value
                
    final_amount = total_price - discount_amount
    site_settings = SiteSettings.load()
    
    tax_amount = 0
    if site_settings.tax_percentage > 0:
        tax_amount = (final_amount * float(site_settings.tax_percentage)) / 100
        final_amount += tax_amount
        
    if not getattr(site_settings, 'free_delivery_all_orders', False) and not (site_settings.enable_free_delivery and final_amount >= site_settings.free_delivery_min):
        final_amount += site_settings.delivery_charge
        
    try:
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        
        razorpay_order_data = {
            'amount': int(final_amount * 100),  # Razorpay expects amount in paise
            'currency': 'INR',
            'payment_capture': 1
        }
        
        razorpay_order = client.order.create(data=razorpay_order_data)
        
        # Cache relevant data in session
        request.session['razorpay_order_id'] = razorpay_order['id']
        request.session['razorpay_amount'] = final_amount
        
        return JsonResponse({
            'order_id': razorpay_order['id'],
            'amount': final_amount,
            'key_id': settings.RAZORPAY_KEY_ID,
            'user_email': request.user.email or '',
            'user_name': request.user.get_full_name() or request.user.username
        })
    except Exception as e:
        logger.error(f"Razorpay order creation failed: {e}")
        return JsonResponse({'error': f'Payment gateway initialization failed: {str(e)}'}, status=500)


@login_required
@csrf_exempt
def verify_razorpay_payment(request):
    import razorpay
    from django.conf import settings
    from products.models import SiteSettings
    site_settings = SiteSettings.load()
    
    if request.method == 'POST':
        import json
        try:
            data = json.loads(request.body)
        except ValueError:
            data = request.POST
            
        payment_id = data.get('razorpay_payment_id')
        razorpay_order_id = data.get('razorpay_order_id')
        signature = data.get('razorpay_signature')
        
        address_id = request.session.get('selected_address_id')
        product_id = request.session.get('product_id')
        
        if not address_id:
            return JsonResponse({'status': 'failure', 'error': 'Session expired.'}, status=400)
            
        address = Address.objects.get(id=address_id)
        
        try:
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            
            params_dict = {
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': signature
            }
            client.utility.verify_payment_signature(params_dict)
            
            orders = []
            with transaction.atomic():
                if product_id:
                    saree = Saree.objects.get(slug=product_id)
                    order = Order.objects.create(
                        saree=saree, user=request.user, quantity=1,
                        amount=saree.price, paid=True, 
                        status='PROCESSING',
                        delivery_address=address, 
                        razorpay_order_id=razorpay_order_id,
                        razorpay_payment_id=payment_id,
                        razorpay_signature=signature
                    )
                    saree.stock_quantity = max(0, saree.stock_quantity - 1)
                    if saree.stock_quantity == 0:
                        saree.available = False
                    saree.save()
                    orders.append(order)
                else:
                    cart = Cart.objects.get(user=request.user)
                    cart_total = cart.get_total_price()
                    
                    discount_amount = 0
                    coupon_code = request.session.get('applied_coupon')
                    if coupon_code:
                        from django.utils import timezone
                        from .models import Coupon
                        applied_coupon = Coupon.objects.filter(code=coupon_code, active=True, expiry_date__gt=timezone.now()).first()
                        if applied_coupon and cart_total >= applied_coupon.min_purchase_amount:
                            if applied_coupon.discount_type == 'PERCENTAGE':
                                discount_amount = (cart_total * applied_coupon.discount_value) / 100
                            else:
                                discount_amount = applied_coupon.discount_value
                                
                    for item in cart.items.all():
                        item_price = item.get_total_price()
                        if cart_total > 0:
                            proportional_discount = (item_price / cart_total) * discount_amount
                        else:
                            proportional_discount = 0
                        
                        order_amount = max(0, int(item_price - proportional_discount))
                        
                        order = Order.objects.create(
                            saree=item.saree, user=request.user, quantity=item.quantity,
                            amount=order_amount, paid=True, 
                            status='PROCESSING',
                            delivery_address=address, 
                            razorpay_order_id=razorpay_order_id,
                            razorpay_payment_id=payment_id,
                            razorpay_signature=signature
                        )
                        saree = item.saree
                        saree.stock_quantity = max(0, saree.stock_quantity - item.quantity)
                        if saree.stock_quantity == 0:
                            saree.available = False
                        saree.save()
                        orders.append(order)
                    
                    request.session.pop('applied_coupon', None)
                    cart.items.all().delete()
            
            try:
                from .email_utils import send_customer_receipt, send_admin_order_email
                try:
                    send_admin_order_email(orders)
                except Exception as e:
                    logger.error("send_admin_order_email failed in razorpay flow: %s", e)
                    
                for order in orders:
                    try:
                        info = {
                            'id': payment_id,
                            'method': 'Razorpay',
                            'status': 'success',
                            'amount': order.amount
                        }
                        send_customer_receipt(order, info)
                    except Exception as e:
                        logger.error("send_customer_receipt failed for order %s in razorpay flow: %s", order.id, e)
            except Exception as e:
                logger.error("Email notification failure in razorpay flow: %s", e)
                
            # SMS Notifications
            try:
                if site_settings.enable_sms_notifications or getattr(settings, "ENABLE_SMS", False):
                    first_order = orders[0] if orders else None
                    if first_order and first_order.delivery_address:
                        addr = first_order.delivery_address
                        product_list = ", ".join([f"{o.saree.name} (x{o.quantity or 1})" for o in orders])
                        
                        # Calculate Grand Total (Items + Tax + Delivery)
                        subtotal = sum(o.amount for o in orders)
                        tax_amount = (subtotal * float(site_settings.tax_percentage)) / 100 if site_settings.tax_percentage > 0 else 0
                        grand_total = subtotal + tax_amount
                        
                        if not getattr(site_settings, 'free_delivery_all_orders', False) and not (site_settings.enable_free_delivery and grand_total >= site_settings.free_delivery_min):
                            grand_total += site_settings.delivery_charge
                        
                        # 1. Admin SMS
                        admin_phone = site_settings.admin_phone or getattr(settings, "ADMIN_PHONE", None)
                        admin_msg = (
                            f"NEW ORDER #{first_order.id}\n"
                            f"{addr.full_name}, {addr.phone}\n"
                            f"{addr.address_line_1}, {addr.city}\n"
                            f"Items: {product_list}\n"
                            f"Total: Rs.{int(grand_total)} (Inc. Tax & Delivery)"
                        )
                        try:
                            if admin_phone:
                                send_sms(admin_phone, admin_msg)
                        except Exception as e:
                            logger.error("Admin SMS failed: %s", e)

                        # 2. Customer SMS (One combined message)
                        try:
                            if addr.phone:
                                base_url = settings.SITE_URL
                                cust_msg = (
                                    f"Hi {addr.full_name}, your order #{first_order.id} for Rs.{int(grand_total)} is confirmed. "
                                    f"Items: {product_list}. Track here: {base_url}/order/{first_order.id}/ - Vijayalakshmi Silks"
                                )
                                send_sms(addr.phone, cust_msg)
                        except Exception as e:
                            logger.error("Customer SMS failed: %s", e)
            except Exception as e:
                logger.error("SMS notification section failed: %s", e)

            return JsonResponse({'status': 'success', 'redirect_url': f'/payment_complete/?order_id={razorpay_order_id}'})
        except razorpay.errors.SignatureVerificationError:
            return JsonResponse({'status': 'failure', 'error': 'Payment verification failed.'}, status=400)
        except Exception as e:
            return JsonResponse({'status': 'failure', 'error': str(e)}, status=500)
            
    return JsonResponse({'status': 'failure', 'error': 'Invalid request method.'}, status=405)


def robots_txt(request):
    lines = [
        "User-agent: *",
        "Disallow: /admin/",
        "Disallow: /management/",
        "Disallow: /cart/",
        "Disallow: /checkout/",
        f"Sitemap: {request.scheme}://{request.get_host()}/sitemap.xml"
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")

def sitemap_xml(request):
    host = f"{request.scheme}://{request.get_host()}"
    urls = [
        {'loc': f"{host}/", 'priority': '1.0'},
        {'loc': f"{host}/shop/", 'priority': '0.8'},
    ]
    
    for saree in Saree.objects.filter(available=True):
        urls.append({'loc': f"{host}/product/{saree.slug}/", 'priority': '0.7'})
        
    for col in Collection.objects.filter(is_active=True):
        urls.append({'loc': f"{host}/collection/{col.slug}/", 'priority': '0.7'})
        
    xml_content = render_to_string('sitemap_xml.html', {'urls': urls})
    return HttpResponse(xml_content, content_type='application/xml')


def location_view(request):
    return render(request, 'location.html')
