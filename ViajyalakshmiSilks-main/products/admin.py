from django.contrib import admin
from django.utils import timezone
from .models import Saree, Order, UserProfile, Cart, CartItem, Address

@admin.register(Saree)
class SareeAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'available', 'has_images')
    list_filter = ('available',)
    search_fields = ('name', 'description')
    fields = ('name', 'price', 'description', 'main_image', 'extra_image1', 'extra_image2', 'extra_image3', 'available')
    
    def has_images(self, obj):
        """Show how many images are uploaded"""
        count = len(obj.get_all_images())
        return f"{count}/4 images"
    has_images.short_description = 'Images'

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_customer_name', 'get_delivery_address', 'get_customer_phone', 'saree', 'amount', 'paid', 'get_created_at_ist')
    list_filter = ('paid', 'created_at')
    search_fields = ('user__first_name', 'user__last_name', 'guest_name', 'saree__name', 'user__addresses__full_name', 'user__addresses__city')
    readonly_fields = ('get_customer_details',)
    
    def get_customer_name(self, obj):
        if obj.user:
            return obj.user.get_full_name() or obj.user.username
        return obj.guest_name or 'Guest'
    get_customer_name.short_description = 'Customer'
    
    def get_delivery_address(self, obj):
        if obj.delivery_address:
            # Use the new Address model
            address = obj.delivery_address.get_full_address()
            return address[:50] + '...' if len(address) > 50 else address
        elif obj.guest_address:
            # Fallback to guest address for backward compatibility
            return obj.guest_address[:50] + '...' if len(obj.guest_address) > 50 else obj.guest_address
        else:
            return "No address provided"
    get_delivery_address.short_description = 'Delivery Address'
    
    def get_customer_phone(self, obj):
        if obj.user:
            try:
                profile = obj.user.userprofile
                phone = profile.mobile_number.strip() if profile.mobile_number else ''
                if phone:
                    return phone
                else:
                    return 'No phone provided'
            except UserProfile.DoesNotExist:
                return 'Profile not found'
            except Exception as e:
                return f'Error: {str(e)}'
        return obj.guest_phone or 'No guest phone'
    get_customer_phone.short_description = 'Phone'
    
    def get_customer_details(self, obj):
        if obj.user:
            try:
                profile = obj.user.userprofile
                # Get default address if exists
                default_address = obj.user.addresses.filter(is_default=True).first()
                address_text = default_address.get_full_address() if default_address else "No default address"
                
                return f"""
                Name: {obj.user.get_full_name() or obj.user.username}
                Email: {obj.user.email}
                Phone: {profile.mobile_number}
                Default Address: {address_text}
                """
            except UserProfile.DoesNotExist:
                return f"""
                Name: {obj.user.get_full_name() or obj.user.username}
                Email: {obj.user.email}
                Phone: Not provided
                Default Address: Not provided
                """
        else:
            return f"""
            Name: {obj.guest_name or 'Not provided'}
            Email: {obj.guest_email or 'Not provided'}
            Phone: {obj.guest_phone or 'Not provided'}
            Address: {obj.guest_address or 'Not provided'}
            """
    get_customer_details.short_description = 'Customer Details'
    
    def get_created_at_ist(self, obj):
        local_time = timezone.localtime(obj.created_at)
        return local_time.strftime('%d %B %Y at %I:%M %p IST')
    get_created_at_ist.short_description = 'Order Date (IST)'
    get_created_at_ist.admin_order_field = 'created_at'

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'mobile_number', 'get_user_email', 'get_addresses_count')
    search_fields = ('user__first_name', 'user__last_name', 'user__username', 'mobile_number')
    fields = ('user', 'mobile_number')
    
    def get_user_email(self, obj):
        return obj.user.email
    get_user_email.short_description = 'Email'
    
    def get_addresses_count(self, obj):
        count = obj.user.addresses.count()
        if count == 0:
            return "No addresses"
        elif count == 1:
            return "1 address"
        else:
            return f"{count} addresses"
    get_addresses_count.short_description = 'Addresses'

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_items_count', 'get_total_items', 'get_total_price', 'get_created_at_ist')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('user__first_name', 'user__last_name', 'user__username')
    readonly_fields = ('created_at', 'updated_at')
    
    def get_created_at_ist(self, obj):
        local_time = timezone.localtime(obj.created_at)
        return local_time.strftime('%d %B %Y at %I:%M %p IST')
    get_created_at_ist.short_description = 'Created (IST)'
    get_created_at_ist.admin_order_field = 'created_at'

@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('cart', 'saree', 'quantity', 'get_total_price', 'get_added_at_ist')
    list_filter = ('added_at', 'saree')
    search_fields = ('cart__user__first_name', 'cart__user__last_name', 'saree__name')
    readonly_fields = ('added_at',)
    
    def get_added_at_ist(self, obj):
        local_time = timezone.localtime(obj.added_at)
        return local_time.strftime('%d %B %Y at %I:%M %p IST')
    get_added_at_ist.short_description = 'Added (IST)'
    get_added_at_ist.admin_order_field = 'added_at'

@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'full_name', 'city', 'state', 'pincode', 'is_default', 'get_created_at_ist')
    list_filter = ('is_default', 'state', 'city', 'created_at')
    search_fields = ('user__first_name', 'user__last_name', 'user__username', 'name', 'full_name', 'city', 'state', 'pincode')
    readonly_fields = ('created_at',)
    
    def get_created_at_ist(self, obj):
        local_time = timezone.localtime(obj.created_at)
        return local_time.strftime('%d %B %Y at %I:%M %p IST')
    get_created_at_ist.short_description = 'Created (IST)'
    get_created_at_ist.admin_order_field = 'created_at'

