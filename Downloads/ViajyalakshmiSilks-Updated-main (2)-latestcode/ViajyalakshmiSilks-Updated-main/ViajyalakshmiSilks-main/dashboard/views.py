import csv
import logging
from datetime import datetime, timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import user_passes_test, login_required
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.db.models import Sum, Count, Q
from django.http import HttpResponse, JsonResponse
from products.models import Saree, Order, UserProfile, Cart, CartItem, Address, Collection, Coupon, SiteSettings
from django.contrib.auth.models import User
from django.utils import timezone
from allauth.socialaccount.models import SocialApp
from django.contrib.sites.models import Site
from django.conf import settings as django_settings

logger = logging.getLogger(__name__)

def admin_required(function):
    return user_passes_test(lambda u: u.is_staff)(function)

@admin_required
def dashboard_home(request):
    # Stats
    total_revenue = Order.objects.filter(Q(paid=True) | Q(razorpay_payment_id='COD')).aggregate(Sum('amount'))['amount__sum'] or 0
    total_orders = Order.objects.filter(Q(paid=True) | Q(razorpay_payment_id='COD')).count()
    total_customers = User.objects.filter(is_staff=False).count()
    low_stock_products = Saree.objects.filter(stock_quantity__lt=5).count()
    
    # Recent Orders
    recent_orders = Order.objects.filter(Q(paid=True) | Q(razorpay_payment_id='COD')).order_by('-created_at')[:10]
    
    # Best Sellers
    best_sellers = Saree.objects.filter(is_best_seller=True)[:5]
    
    # Sales Chart Data (Last 7 Days)
    today = timezone.now().date()
    labels = []
    values = []
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        day_total = Order.objects.filter(Q(paid=True) | Q(razorpay_payment_id='COD'), created_at__date=date).aggregate(Sum('amount'))['amount__sum'] or 0
        labels.append(date.strftime('%b %d'))
        values.append(int(day_total))

    context = {
        'total_revenue': total_revenue,
        'total_orders': total_orders,
        'total_customers': total_customers,
        'low_stock_products': low_stock_products,
        'recent_orders': recent_orders,
        'best_sellers': best_sellers,
        'chart_labels': labels,
        'chart_values': values,
    }
    return render(request, 'dashboard/home.html', context)

@admin_required
def dashboard_products(request):
    search = request.GET.get('search', '')
    products = Saree.objects.all().order_by('-id')
    if search:
        products = products.filter(Q(name__icontains=search) | Q(description__icontains=search))
    
    return render(request, 'dashboard/products.html', {'products': products})

@admin_required
def product_add(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        price = request.POST.get('price')
        description = request.POST.get('description')
        stock = request.POST.get('stock')
        main_image = request.FILES.get('main_image')
        video = request.FILES.get('video')
        
        product = Saree.objects.create(
            name=name, price=price, mrp=request.POST.get('mrp') or None,
            description=description, 
            stock_quantity=stock, main_image=main_image,
            video=video,
            is_featured=request.POST.get('is_featured') == 'on',
            is_best_seller=request.POST.get('is_best_seller') == 'on',
            is_new_arrival=request.POST.get('is_new_arrival') == 'on',
            is_authentic_silk=request.POST.get('is_authentic_silk') == 'on',
            slug=request.POST.get('slug') or None,
            meta_title=request.POST.get('meta_title', ''),
            meta_description=request.POST.get('meta_description', '')
        )

        collection_ids = request.POST.getlist('collections')
        if collection_ids:
            product.collections.set(collection_ids)
            
        additional_images = request.FILES.getlist('additional_images')
        if additional_images:
            from products.models import SareeImage
            for img in additional_images:
                SareeImage.objects.create(saree=product, image=img)
            
        messages.success(request, f'Product {product.name} created successfully!')
        return redirect('dashboard_products')
        
    collections = Collection.objects.all()
    return render(request, 'dashboard/product_form.html', {'collections': collections})

@admin_required
def product_edit(request, pk):
    product = get_object_or_404(Saree, pk=pk)
    if request.method == 'POST':
        product.name = request.POST.get('name')
        product.price = request.POST.get('price')
        product.mrp = request.POST.get('mrp') or None
        product.description = request.POST.get('description')
        product.stock_quantity = request.POST.get('stock')

        if request.FILES.get('main_image'):
            product.main_image = request.FILES.get('main_image')
            
        if request.FILES.get('video'):
            product.video = request.FILES.get('video')
        
        product.is_featured = request.POST.get('is_featured') == 'on'
        product.is_best_seller = request.POST.get('is_best_seller') == 'on'
        product.is_new_arrival = request.POST.get('is_new_arrival') == 'on'
        product.is_authentic_silk = request.POST.get('is_authentic_silk') == 'on'
        product.slug = request.POST.get('slug') or None
        product.meta_title = request.POST.get('meta_title', '')
        product.meta_description = request.POST.get('meta_description', '')
        product.save()
        
        collection_ids = request.POST.getlist('collections')
        product.collections.set(collection_ids)
        
        additional_images = request.FILES.getlist('additional_images')
        if additional_images:
            from products.models import SareeImage
            for img in additional_images:
                SareeImage.objects.create(saree=product, image=img)
        
        messages.success(request, f'Product {product.name} updated!')
        return redirect('dashboard_products')
        
    collections = Collection.objects.all()
    return render(request, 'dashboard/product_form.html', {
        'product': product,
        'collections': collections
    })

@admin_required
def product_delete(request, pk):
    product = get_object_or_404(Saree, pk=pk)
    product.delete()
    messages.success(request, 'Product deleted.')
    return redirect('dashboard_products')

@admin_required
def toggle_product_status(request, pk):
    product = get_object_or_404(Saree, pk=pk)
    if int(product.stock_quantity) <= 0 and not product.available:
        messages.error(request, f'Cannot show {product.name} because stock is 0.')
    else:
        product.available = not product.available
        product.save()
        messages.success(request, f'Product status for {product.name} updated to {"Shown" if product.available else "Hidden"}.')
    return redirect('dashboard_products')


@admin_required
def dashboard_orders(request):
    status = request.GET.get('status')
    orders = Order.objects.filter(Q(paid=True) | Q(razorpay_payment_id='COD')).order_by('-created_at')
    if status:
        orders = orders.filter(status=status)
    return render(request, 'dashboard/orders.html', {'orders': orders})

@admin_required
def order_detail(request, pk):
    order = get_object_or_404(Order, pk=pk)
    return render(request, 'dashboard/order_detail.html', {'order': order})

@admin_required
def update_order_status(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        tracking_id = request.POST.get('tracking_id')
        courier_name = request.POST.get('courier_name')
        courier_tracking_url = request.POST.get('courier_tracking_url')
        
        order.status = new_status
        if tracking_id:
            order.tracking_id = tracking_id
        if courier_name:
            order.courier_name = courier_name
        if courier_tracking_url:
            order.courier_tracking_url = courier_tracking_url
        order.save()
        messages.success(request, f'Order #{order.id} status updated to {new_status}')
    return redirect('dashboard_order_detail', pk=pk)

@admin_required
def edit_invoice(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == 'POST':
        # Amount and Basic Details
        order.amount = request.POST.get('amount', order.amount)
        order.paid = request.POST.get('paid') == 'on'
        
        # Address Details
        if order.delivery_address:
            addr = order.delivery_address
            addr.full_name = request.POST.get('full_name', addr.full_name)
            addr.phone = request.POST.get('phone', addr.phone)
            addr.address_line_1 = request.POST.get('address_line_1', addr.address_line_1)
            addr.address_line_2 = request.POST.get('address_line_2', addr.address_line_2)
            addr.city = request.POST.get('city', addr.city)
            addr.state = request.POST.get('state', addr.state)
            addr.pincode = request.POST.get('pincode', addr.pincode)
            addr.save()
        else:
            # Guest Address
            order.guest_name = request.POST.get('full_name', order.guest_name)
            order.guest_phone = request.POST.get('phone', order.guest_phone)
            order.guest_address = request.POST.get('guest_address', order.guest_address)
            
        order.save()
        messages.success(request, f'Invoice details for Order #{order.id} updated successfully.')
    return redirect('dashboard_order_detail', pk=pk)

@admin_required
def print_invoice(request, pk):
    order = get_object_or_404(Order, pk=pk)
    return render(request, 'dashboard/print_invoice.html', {'order': order})

@admin_required
def print_shipping_label(request, pk):
    order = get_object_or_404(Order, pk=pk)
    return render(request, 'dashboard/print_label.html', {'order': order})

@admin_required
def export_orders_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="orders_export.csv"'
    writer = csv.writer(response)
    writer.writerow(['Order ID', 'Customer', 'Product', 'Amount', 'Status', 'Date'])
    orders = Order.objects.filter(Q(paid=True) | Q(razorpay_payment_id='COD'))
    for o in orders:
        writer.writerow([o.id, o.user.username if o.user else o.guest_name, o.saree.name, o.amount, o.status, o.created_at])
    return response

@admin_required
def dashboard_collections(request):
    collections = Collection.objects.all().order_by('-priority', 'name')
    return render(request, 'dashboard/collections.html', {'collections': collections})

@admin_required
def collection_add(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        image = request.FILES.get('image')
        show_on_home = request.POST.get('show_on_home') == 'on'
        priority_val = request.POST.get('priority', 0)
        priority = int(priority_val) if priority_val and str(priority_val).strip() else 0
        
        Collection.objects.create(
            name=name, 
            description=description, 
            image=image, 
            show_on_home=show_on_home,
            priority=priority,
            is_active=True
        )
        return redirect('dashboard_collections')
    return render(request, 'dashboard/collection_form.html')

@admin_required
def collection_edit(request, pk):
    collection = get_object_or_404(Collection, pk=pk)
    if request.method == 'POST':
        collection.name = request.POST.get('name')
        collection.description = request.POST.get('description', '')
        if request.FILES.get('image'):
            collection.image = request.FILES.get('image')
        collection.show_on_home = request.POST.get('show_on_home') == 'on'
        
        priority_val = request.POST.get('priority')
        if priority_val and str(priority_val).strip():
            collection.priority = int(priority_val)
            
        collection.save()
        messages.success(request, f"Collection '{collection.name}' updated successfully.")
        return redirect('dashboard_collections')
    return render(request, 'dashboard/collection_form.html', {'collection': collection})

@admin_required
def collection_delete(request, pk):
    collection = get_object_or_404(Collection, pk=pk)
    name = collection.name
    collection.delete()
    messages.success(request, f"Collection '{name}' deleted successfully.")
    return redirect('dashboard_collections')

@admin_required
def dashboard_customers(request):
    customers = User.objects.filter(is_staff=False).annotate(order_count=Count('order', filter=Q(order__paid=True) | Q(order__razorpay_payment_id='COD')))
    return render(request, 'dashboard/customers.html', {'customers': customers})

@admin_required
def customer_delete(request, pk):
    customer = get_object_or_404(User, pk=pk, is_staff=False)
    name = customer.get_full_name() or customer.username
    customer.delete()
    messages.success(request, f"Customer '{name}' and all associated data have been removed.")
    return redirect('dashboard_customers')


@admin_required
def dashboard_coupons(request):
    coupons = Coupon.objects.all()
    return render(request, 'dashboard/coupons.html', {'coupons': coupons})

@admin_required
def coupon_add(request):
    if request.method == 'POST':
        code = request.POST.get('code')
        dtype = request.POST.get('discount_type')
        val = request.POST.get('value')
        min_purchase = request.POST.get('min_purchase', 0)
        expiry = request.POST.get('expiry')
        try:
            expiry_naive = datetime.strptime(expiry, '%Y-%m-%dT%H:%M')
            expiry_aware = timezone.make_aware(expiry_naive, timezone.get_current_timezone())
        except (ValueError, TypeError):
            expiry_aware = timezone.now() + timezone.timedelta(days=30)
            
        Coupon.objects.create(
            code=code, 
            discount_type=dtype, 
            discount_value=val, 
            min_purchase_amount=min_purchase,
            expiry_date=expiry_aware
        )
        messages.success(request, f"Coupon code '{code}' created.")
        return redirect('dashboard_coupons')
    return render(request, 'dashboard/coupon_form.html')


@admin_required
def coupon_edit(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)
    if request.method == 'POST':
        coupon.code = request.POST.get('code')
        coupon.discount_type = request.POST.get('discount_type')
        coupon.discount_value = request.POST.get('value')
        coupon.min_purchase_amount = request.POST.get('min_purchase', 0)
        expiry = request.POST.get('expiry')
        try:
            expiry_naive = datetime.strptime(expiry, '%Y-%m-%dT%H:%M')
            coupon.expiry_date = timezone.make_aware(expiry_naive, timezone.get_current_timezone())
        except (ValueError, TypeError):
            pass
        coupon.active = request.POST.get('active') == 'on'
        coupon.save()
        messages.success(request, f"Coupon '{coupon.code}' updated.")
        return redirect('dashboard_coupons')
    return render(request, 'dashboard/coupon_form.html', {'coupon': coupon})

@admin_required
def coupon_delete(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)
    code = coupon.code
    coupon.delete()
    messages.success(request, f"Coupon '{code}' deleted.")
    return redirect('dashboard_coupons')


@admin_required
def dashboard_settings(request):
    settings = SiteSettings.load()
    google_app = SocialApp.objects.filter(provider='google').first()
    
    import os
    from django.conf import settings as django_settings
    env_path = os.path.join(django_settings.BASE_DIR, '.env')
    env_credentials = {}
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    k, v = line.strip().split('=', 1)
                    env_credentials[k] = v
    if request.method == 'POST':
        # General
        settings.store_name = request.POST.get('store_name')
        settings.contact_phone = request.POST.get('contact_phone')
        settings.whatsapp_number = request.POST.get('whatsapp_number')
        settings.email = request.POST.get('email')
        settings.address = request.POST.get('address')
        settings.business_hours = request.POST.get('business_hours')
        
        # Shipping
        settings.free_delivery_min = request.POST.get('free_delivery_min', 0)
        settings.delivery_charge = request.POST.get('delivery_charge', 0)
        settings.enable_free_delivery = request.POST.get('enable_free_delivery') == 'on'
        settings.free_delivery_all_orders = request.POST.get('free_delivery_all_orders') == 'on'
        settings.est_delivery_time = request.POST.get('est_delivery_time')
        
        # Payment
        settings.razorpay_enabled = request.POST.get('razorpay_enabled') == 'on'
        settings.cod_enabled = request.POST.get('cod_enabled') == 'on'
        settings.cod_charge = request.POST.get('cod_charge', 0)
        
        # Rules
        settings.min_order_value = request.POST.get('min_order_value', 0)
        settings.max_order_qty = request.POST.get('max_order_qty', 5)
        settings.allow_guest_checkout = request.POST.get('allow_guest_checkout') == 'on'
        settings.auto_confirm_orders = request.POST.get('auto_confirm_orders') == 'on'
        
        # Branding
        settings.hero_tagline = request.POST.get('hero_tagline')
        settings.hero_description = request.POST.get('hero_description')
        
        if request.FILES.get('logo'): settings.logo = request.FILES.get('logo')
        if request.FILES.get('hero_image_1'): settings.hero_image_1 = request.FILES.get('hero_image_1')
        if request.FILES.get('hero_image_2'): settings.hero_image_2 = request.FILES.get('hero_image_2')
        if request.FILES.get('hero_image_3'): settings.hero_image_3 = request.FILES.get('hero_image_3')
        
        settings.show_collections = request.POST.get('show_collections') == 'on'
        settings.show_story = request.POST.get('show_story') == 'on'
        settings.show_stats = request.POST.get('show_stats') == 'on'
        
        # SEO
        settings.default_meta_title = request.POST.get('default_meta_title')
        settings.default_meta_description = request.POST.get('default_meta_description')
        settings.default_keywords = request.POST.get('default_keywords')
        
        # Advanced
        settings.currency_symbol = request.POST.get('currency_symbol')
        settings.tax_percentage = request.POST.get('tax_percentage', 0)
        
        # Invoice Customization
        settings.invoice_prefix = request.POST.get('invoice_prefix', 'ORD')
        settings.invoice_footer = request.POST.get('invoice_footer')
        settings.invoice_notes = request.POST.get('invoice_notes')
        
        # Notifications & SMS
        settings.enable_sms_notifications = request.POST.get('enable_sms_notifications') == 'on'
        settings.whatsapp_order_placed = request.POST.get('whatsapp_order_placed') == 'on'
        settings.whatsapp_order_shipped = request.POST.get('whatsapp_order_shipped') == 'on'
        
        settings.admin_phone = request.POST.get('admin_phone')
        settings.twilio_account_sid = request.POST.get('twilio_account_sid')
        settings.twilio_auth_token = request.POST.get('twilio_auth_token')
        settings.twilio_phone_number = request.POST.get('twilio_phone_number')
        
        settings.save()

        # Credentials Update
        allowed_env_keys = [
            'GOOGLE_CLIENT_ID', 'GOOGLE_SECRET',
            'RAZORPAY_KEY_ID', 'RAZORPAY_KEY_SECRET',
            'STRIPE_PUBLISHABLE_KEY', 'STRIPE_SECRET_KEY',
            'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_PHONE_NUMBER',
            'EMAIL_HOST_USER', 'EMAIL_HOST_PASSWORD'
        ]
        
        pending_credentials = {}
        credentials_changed = False
        
        for key in allowed_env_keys:
            val = request.POST.get(key)
            if val is not None and val != '•' * 16:
                if env_credentials.get(key, '') != val:
                    credentials_changed = True
                pending_credentials[key] = val
            else:
                pending_credentials[key] = env_credentials.get(key, '')
                
        if credentials_changed:
            request.session['pending_credentials'] = pending_credentials

        # Admin Account Update
        admin_email = request.POST.get('admin_email')
        admin_password = request.POST.get('admin_password')
        
        needs_verification = False
        
        if credentials_changed:
            needs_verification = True
        
        if admin_email and admin_email != request.user.email:
            if User.objects.filter(email=admin_email).exclude(pk=request.user.pk).exists():
                messages.error(request, f"Email '{admin_email}' is already taken.")
            else:
                request.session['pending_admin_email'] = admin_email
                needs_verification = True

        if admin_password:
            request.session['pending_admin_password'] = admin_password
            needs_verification = True
            
        if needs_verification:
            import random
            from django.core.mail import EmailMessage
            from django.template.loader import render_to_string
            from dotenv import load_dotenv
            import os
            
            env_path = os.path.join(django_settings.BASE_DIR, '.env')
            load_dotenv(env_path, override=True)
            
            django_settings.EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
            django_settings.EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
            django_settings.DEFAULT_FROM_EMAIL = django_settings.EMAIL_HOST_USER
            
            otp = str(random.randint(100000, 999999))
            request.session['admin_change_otp'] = otp
            
            try:
                subject = "Security Alert: Admin Changes Requested - Vijayalakshmi Silks"
                html_content = render_to_string('email/otp_email.html', {'otp': otp})
                recipients = list(set([request.user.email, django_settings.EMAIL_HOST_USER]))
                email_message = EmailMessage(subject, html_content, django_settings.DEFAULT_FROM_EMAIL, recipients)
                email_message.content_subtype = "html"
                email_message.send()
                
                messages.info(request, 'An OTP has been sent to your current email address to verify these changes.')
                return render(request, 'dashboard/verify_admin_otp.html')
            except Exception as e:
                logger.error(f"Error sending admin change OTP: {e}")
                messages.warning(request, f"We couldn't send the verification email. Take this fallback OTP to finalize credentials: {otp}")
                return render(request, 'dashboard/verify_admin_otp.html')

        messages.success(request, 'Site settings updated successfully.')
        return redirect('dashboard_settings')
        
    masked_credentials = {}
    for k, v in env_credentials.items():
        if v:
            masked_credentials[k] = '•' * 16
        else:
            masked_credentials[k] = ''
            
    return render(request, 'dashboard/settings.html', {
        'settings': settings, 
        'google_app': google_app, 
        'env_credentials': masked_credentials
    })


@admin_required
def verify_admin_changes(request):
    if request.method == 'POST':
        user_otp = request.POST.get('otp')
        correct_otp = request.session.get('admin_change_otp')
        
        if user_otp and correct_otp and user_otp == correct_otp:
            # Apply changes
            pending_email = request.session.get('pending_admin_email')
            pending_password = request.session.get('pending_admin_password')
            
            changes_made = []
            
            if pending_email:
                request.user.email = pending_email
                request.user.username = pending_email.split('@')[0] # keep username sync'd somewhat
                changes_made.append('Email')
                
            if pending_password:
                request.user.set_password(pending_password)
                changes_made.append('Password')
                
            pending_credentials = request.session.get('pending_credentials')
            if pending_credentials:
                import os
                from django.conf import settings as django_settings
                env_path = os.path.join(django_settings.BASE_DIR, '.env')
                
                existing_env = {}
                if os.path.exists(env_path):
                    with open(env_path, 'r') as f:
                        for line in f:
                            if '=' in line and not line.startswith('#'):
                                k, v = line.strip().split('=', 1)
                                existing_env[k] = v
                                
                for k, v in pending_credentials.items():
                    existing_env[k] = v
                    
                with open(env_path, 'w') as f:
                    for k, v in existing_env.items():
                        f.write(f"{k}={v}\n")
                        
                changes_made.append('Credentials')
                
                from dotenv import load_dotenv
                load_dotenv(env_path, override=True)
                
            if changes_made:
                if pending_email or pending_password:
                    request.user.save()
                    update_session_auth_hash(request, request.user)
                messages.success(request, f"Successfully updated: {', '.join(changes_made)}.")
                
            # Cleanup session
            request.session.pop('pending_admin_email', None)
            request.session.pop('pending_admin_password', None)
            request.session.pop('pending_credentials', None)
            request.session.pop('admin_change_otp', None)
            
            return redirect('dashboard_settings')
        else:
            messages.error(request, "Invalid OTP. Please try again.")
            return render(request, 'dashboard/verify_admin_otp.html')
            
    return redirect('dashboard_settings')
