from django.contrib import admin
from django.utils import timezone
from .models import Saree, SareeImage, Order, UserProfile, Cart, CartItem, Address, ProductFAQ, BlogPost, Collection, SiteSettings

class SareeImageInline(admin.TabularInline):
    model = SareeImage
    extra = 3

class ProductFAQInline(admin.TabularInline):
    model = ProductFAQ
    extra = 1

# =========================
# SAREE ADMIN (OPTIMIZED)
# =========================
@admin.register(Saree)
class SareeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'price', 'available')
    list_filter = ('available',)
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    inlines = [SareeImageInline, ProductFAQInline]
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'price', 'mrp', 'description', 'highlights', 'canonical_override')}),
        ('Images', {'fields': ('main_image', 'extra_image1', 'extra_image2', 'extra_image3', 'video')}),
        ('Availability', {'fields': ('available', 'stock_quantity', 'is_featured', 'is_best_seller', 'is_new_arrival')}),
        ('SEO', {'fields': ('meta_title', 'meta_description')}),
    )

@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_at')
    prepopulated_fields = {'slug': ('title',)}

@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'show_on_home')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ('store_name', 'email')
    fieldsets = (
        ('General & Contact', {
            'fields': ('store_name', 'contact_phone', 'whatsapp_number', 'email', 'address', 'business_hours')
        }),
        ('Shipping', {
            'fields': ('enable_free_delivery', 'free_delivery_all_orders', 'free_delivery_min', 'delivery_charge', 'est_delivery_time')
        }),
        ('Payment', {
            'fields': ('razorpay_enabled', 'cod_enabled', 'cod_charge')
        }),
        ('Order Rules', {
            'fields': ('min_order_value', 'max_order_qty', 'allow_guest_checkout', 'auto_confirm_orders')
        }),
        ('Branding & Content', {
            'fields': ('logo', 'hero_image_1', 'hero_image_2', 'hero_image_3', 'hero_tagline', 'hero_description', 'show_collections', 'show_story', 'show_stats')
        }),
        ('Invoice Customization', {
            'fields': ('invoice_prefix', 'invoice_notes', 'invoice_footer')
        }),
        ('Notifications', {
            'fields': (
                'admin_phone',
                'whatsapp_order_placed', 
                'whatsapp_order_shipped', 
                'enable_sms_notifications',
                'twilio_account_sid',
                'twilio_auth_token',
                'twilio_phone_number'
            )
        }),
        ('SEO', {
            'fields': ('default_meta_title', 'default_meta_description', 'default_keywords')
        }),
        ('Advanced', {
            'fields': ('maintenance_mode', 'currency_symbol', 'tax_percentage')
        }),
    )

# =========================
# ORDER ADMIN
# =========================
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'get_customer_name',
        'saree',
        'amount',
        'paid',
        'get_created_at_ist'
    )
    list_filter = ('paid', 'created_at')
    search_fields = (
        'user__first_name',
        'user__last_name',
        'guest_name',
        'saree__name',
    )
    readonly_fields = ('get_customer_details',)

    def get_customer_name(self, obj):
        if obj.user:
            return obj.user.get_full_name() or obj.user.username
        return obj.guest_name or 'Guest'
    get_customer_name.short_description = 'Customer'

    def get_customer_details(self, obj):
        if obj.user:
            try:
                profile = obj.user.userprofile
                return f"""
Name: {obj.user.get_full_name()}
Email: {obj.user.email}
Phone: {profile.mobile_number}
"""
            except Exception:
                return "Customer details unavailable"
        return "Guest order"
    get_customer_details.short_description = 'Customer Details'

    def get_created_at_ist(self, obj):
        local_time = timezone.localtime(obj.created_at)
        return local_time.strftime('%d %b %Y %I:%M %p')
    get_created_at_ist.admin_order_field = 'created_at'

# =========================
# USER PROFILE
# =========================
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'mobile_number')
    search_fields = ('user__username', 'mobile_number')

# =========================
# CART
# =========================
@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'updated_at')

# =========================
# CART ITEM
# =========================
@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('cart', 'saree', 'quantity')

# =========================
# ADDRESS
# =========================
@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('user', 'city', 'state', 'pincode', 'is_default')

