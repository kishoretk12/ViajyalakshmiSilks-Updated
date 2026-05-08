# products/models.py
from django.db import models
from django.contrib.auth.models import User

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    mobile_number = models.CharField(max_length=15)

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.mobile_number}"

class Address(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    name = models.CharField(max_length=100, help_text="Address label (e.g., Home, Office)")
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=15)
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_default', '-created_at']
        verbose_name_plural = "Addresses"

    def __str__(self):
        return f"{self.name} - {self.full_name}"

    def get_full_address(self):
        address_parts = [self.address_line_1]
        if self.address_line_2:
            address_parts.append(self.address_line_2)
        address_parts.extend([self.city, self.state, self.pincode])
        return ", ".join(address_parts)

    def save(self, *args, **kwargs):
        if self.is_default:
            Address.objects.filter(user=self.user, is_default=True).update(is_default=False)
        super().save(*args, **kwargs)

class Saree(models.Model):
    name = models.CharField(max_length=200)
    price = models.PositiveIntegerField()
    mrp = models.PositiveIntegerField(null=True, blank=True, help_text="Original price (Maximum Retail Price)")
    description = models.TextField(blank=True)


    main_image = models.ImageField(upload_to='sarees/', blank=True, null=True, help_text="Main image (required)")
    extra_image1 = models.ImageField(upload_to='sarees/', blank=True, null=True, help_text="Extra image 1 (optional)")
    extra_image2 = models.ImageField(upload_to='sarees/', blank=True, null=True, help_text="Extra image 2 (optional)")
    extra_image3 = models.ImageField(upload_to='sarees/', blank=True, null=True, help_text="Extra image 3 (optional)")
    video = models.FileField(upload_to='videos/', blank=True, null=True, help_text="Product showcase video (optional)")

    available = models.BooleanField(default=True)
    stock_quantity = models.PositiveIntegerField(default=10)
    is_featured = models.BooleanField(default=False)
    is_best_seller = models.BooleanField(default=False)
    is_new_arrival = models.BooleanField(default=False)
    is_authentic_silk = models.BooleanField(default=True)
    
    # SEO Fields
    slug = models.SlugField(unique=True, null=True, blank=True)
    meta_title = models.CharField(max_length=200, blank=True)
    meta_description = models.TextField(blank=True)
    highlights = models.TextField(blank=True, help_text="Enter bullet points separated by newlines")
    canonical_override = models.URLField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    def save(self, *args, **kwargs):
        from django.utils.text import slugify
        import uuid
        if not self.slug:
            original_slug = slugify(self.name)
            self.slug = original_slug
            while Saree.objects.filter(slug=self.slug).exclude(id=self.id).exists():
                self.slug = f"{original_slug}-{uuid.uuid4().hex[:4]}"
                
        if self.pk:
            old_instance = Saree.objects.filter(pk=self.pk).first()
            if old_instance and old_instance.stock_quantity <= 0 and int(self.stock_quantity) > 0:
                self.available = True
            elif int(self.stock_quantity) <= 0:
                self.available = False
        else:
            if int(self.stock_quantity) > 0:
                self.available = True
            else:
                self.available = False
            
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def get_all_images(self):
        images = []
        if self.main_image:
            images.append(self.main_image)
        if self.extra_image1:
            images.append(self.extra_image1)
        if self.extra_image2:
            images.append(self.extra_image2)
        if self.extra_image3:
            images.append(self.extra_image3)
            
        for extra in self.additional_images.all():
            images.append(extra.image)
        return images

    def get_discount_percent(self):
        if self.mrp and self.mrp > self.price:
            discount = ((self.mrp - self.price) / self.mrp) * 100
            return int(discount)
        return 0

    def get_savings_amount(self):
        if self.mrp and self.mrp > self.price:
            return self.mrp - self.price
        return 0

class SareeImage(models.Model):
    saree = models.ForeignKey(Saree, related_name='additional_images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='sarees/', help_text="Upload additional product image")
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Image for {self.saree.name}"

class Cart(models.Model):

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart - {self.user.get_full_name() or self.user.username}"

    def get_total_items(self):
        return sum(item.quantity for item in self.items.all())

    def get_total_price(self):
        return sum(item.get_total_price() for item in self.items.all())

    def get_items_count(self):
        return sum(item.quantity for item in self.items.all())

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name='items', on_delete=models.CASCADE)
    saree = models.ForeignKey(Saree, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('cart', 'saree')


    def __str__(self):
        return f"{self.saree.name}"

    def get_total_price(self):
        return self.saree.price * self.quantity

class Order(models.Model):
    saree = models.ForeignKey(Saree, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    delivery_address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True)
    guest_name = models.CharField(max_length=200, blank=True)
    guest_email = models.EmailField(blank=True)
    guest_phone = models.CharField(max_length=20, blank=True)
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('SHIPPED', 'Shipped'),
        ('DELIVERED', 'Delivered'),
        ('CANCELLED', 'Cancelled'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    tracking_id = models.CharField(max_length=100, blank=True, null=True)
    guest_address = models.TextField(blank=True)
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)
    paid = models.BooleanField(default=False)
    amount = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Logistics
    courier_name = models.CharField(max_length=100, blank=True, null=True, help_text="e.g. BlueDart, Delhivery")
    courier_tracking_url = models.URLField(blank=True, null=True)

    def __str__(self):
        if self.user:
            return f"Order {self.id} - {self.user.get_full_name()}"
        return f"Order {self.id} - {self.guest_name}"

    def get_total_price(self):
        return self.saree.price * self.quantity

    def get_delivery_address_display(self):
        if self.delivery_address:
            return f"{self.delivery_address.full_name}, {self.delivery_address.get_full_address()}, Phone: {self.delivery_address.phone}"
        elif self.guest_address:
            return f"{self.guest_name}, {self.guest_address}, Phone: {self.guest_phone}"
        else:
            return "No address provided"

class Collection(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, null=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='collections/', blank=True, null=True)
    products = models.ManyToManyField(Saree, related_name='collections', blank=True)
    is_active = models.BooleanField(default=True)
    show_on_home = models.BooleanField(default=False)
    priority = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        from django.utils.text import slugify
        import uuid
        if not self.slug:
            original_slug = slugify(self.name)
            self.slug = original_slug
            while Collection.objects.filter(slug=self.slug).exclude(id=self.id).exists():
                self.slug = f"{original_slug}-{uuid.uuid4().hex[:4]}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['-priority', 'name']

class Coupon(models.Model):
    DISCOUNT_TYPES = [
        ('PERCENTAGE', 'Percentage'),
        ('FIXED', 'Fixed Amount'),
    ]
    code = models.CharField(max_length=50, unique=True)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPES)
    discount_value = models.PositiveIntegerField()
    min_purchase_amount = models.PositiveIntegerField(default=0)
    expiry_date = models.DateTimeField()
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_expired(self):
        from django.utils import timezone
        return not self.active or self.expiry_date <= timezone.now()

    def __str__(self):
        return f"{self.code} ({self.discount_value} {self.get_discount_type_display()})"

class SiteSettings(models.Model):
    # General
    store_name = models.CharField(max_length=200, default="Vijayalakshmi Silks")
    contact_phone = models.CharField(max_length=20, default="+91 97915 79731")
    whatsapp_number = models.CharField(max_length=20, default="+91 97915 79731")
    email = models.EmailField(default="kishore.kumar0728@gmail.com")
    address = models.TextField(default="Kanchipuram, Tamil Nadu, India")
    business_hours = models.CharField(max_length=200, default="Mon - Sat: 9:00 AM - 8:00 PM")

    # Shipping
    free_delivery_min = models.PositiveIntegerField(default=999)
    delivery_charge = models.PositiveIntegerField(default=100)
    enable_free_delivery = models.BooleanField(default=True)
    free_delivery_all_orders = models.BooleanField(default=False)
    est_delivery_time = models.CharField(max_length=100, default="5-7 Business Days")

    # Payment
    razorpay_enabled = models.BooleanField(default=True)
    cod_enabled = models.BooleanField(default=True)
    cod_charge = models.PositiveIntegerField(default=50)

    # Rules
    min_order_value = models.PositiveIntegerField(default=0)
    max_order_qty = models.PositiveIntegerField(default=5)
    allow_guest_checkout = models.BooleanField(default=True)
    auto_confirm_orders = models.BooleanField(default=False)

    # Branding & Content
    hero_tagline = models.CharField(max_length=255, default="Authentic Kanchipuram Heritage")
    hero_description = models.TextField(default="Experience the timeless elegance of handpicked pure silk sarees.")
    logo = models.ImageField(upload_to='branding/', blank=True, null=True)
    hero_image_1 = models.ImageField(upload_to='branding/', blank=True, null=True)
    hero_image_2 = models.ImageField(upload_to='branding/', blank=True, null=True)
    hero_image_3 = models.ImageField(upload_to='branding/', blank=True, null=True)
    
    show_collections = models.BooleanField(default=True)
    show_story = models.BooleanField(default=True)
    show_stats = models.BooleanField(default=True)

    # Invoice Customization
    invoice_footer = models.TextField(default="Thank you for choosing Vijayalakshmi Silks. We hope you cherish this heritage piece.")
    invoice_notes = models.TextField(default="For support, contact: support@vijayalakshmisilks.com")
    invoice_prefix = models.CharField(max_length=20, default="ORD")

    # Notifications
    admin_phone = models.CharField(max_length=20, default="+919791579731", help_text="Phone number to receive new order alerts (e.g. +919876543210)")
    whatsapp_order_placed = models.BooleanField(default=True)
    whatsapp_order_shipped = models.BooleanField(default=True)
    enable_sms_notifications = models.BooleanField(default=False, help_text="Enable Twilio SMS notifications for orders")
    twilio_account_sid = models.CharField(max_length=100, blank=True, null=True, help_text="Twilio Account SID")
    twilio_auth_token = models.CharField(max_length=100, blank=True, null=True, help_text="Twilio Auth Token")
    twilio_phone_number = models.CharField(max_length=20, blank=True, null=True, help_text="Twilio Phone Number (e.g. +1234567890)")

    # SEO
    default_meta_title = models.CharField(max_length=200, default="Vijayalakshmi Silks | Pure Kanchipuram Silk Sarees")
    default_meta_description = models.TextField(default="Handpicked pure silk sarees from Kanchipuram.")
    default_keywords = models.CharField(max_length=500, default="silk sarees, kanchipuram, handloom, wedding sarees")

    # Advanced
    maintenance_mode = models.BooleanField(default=False)
    currency_symbol = models.CharField(max_length=10, default="₹")
    tax_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return "Global Site Settings"

    def save(self, *args, **kwargs):
        if not self.pk and SiteSettings.objects.exists():
            return # Ensure only one instance exists
        return super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

class ProductFAQ(models.Model):
    saree = models.ForeignKey(Saree, related_name='faqs', on_delete=models.CASCADE)
    question = models.CharField(max_length=255)
    answer = models.TextField()

    def __str__(self):
        return f"FAQ for {self.saree.name}"

class BlogPost(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, null=True, blank=True)
    content = models.TextField()
    main_image = models.ImageField(upload_to='blog/', blank=True, null=True)
    meta_title = models.CharField(max_length=200, blank=True)
    meta_description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        from django.utils.text import slugify
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
