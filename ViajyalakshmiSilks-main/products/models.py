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
        # Ensure only one default address per user
        if self.is_default:
            Address.objects.filter(user=self.user, is_default=True).update(is_default=False)
        super().save(*args, **kwargs)

class Saree(models.Model):
    name = models.CharField(max_length=200)
    price = models.PositiveIntegerField()
    description = models.TextField(blank=True)
    
    # Main image + 3 extra images (4 total)
    main_image = models.ImageField(upload_to='sarees/', blank=True, null=True, help_text="Main image (required)")
    extra_image1 = models.ImageField(upload_to='sarees/', blank=True, null=True, help_text="Extra image 1 (optional)")
    extra_image2 = models.ImageField(upload_to='sarees/', blank=True, null=True, help_text="Extra image 2 (optional)")
    extra_image3 = models.ImageField(upload_to='sarees/', blank=True, null=True, help_text="Extra image 3 (optional)")
    
    available = models.BooleanField(default=True)

    def __str__(self):
        return self.name
    
    def get_all_images(self):
        """Return list of all available images for this saree (main + extras)"""
        images = []
        if self.main_image:
            images.append(self.main_image)
        if self.extra_image1:
            images.append(self.extra_image1)
        if self.extra_image2:
            images.append(self.extra_image2)
        if self.extra_image3:
            images.append(self.extra_image3)
        return images

class Cart(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Cart - {self.user.get_full_name() or self.user.username}"
    
    def get_total_items(self):
        return self.items.count()  # Since each item has quantity 1
    
    def get_total_price(self):
        return sum(item.get_total_price() for item in self.items.all())
    
    def get_items_count(self):
        return self.items.count()

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name='items', on_delete=models.CASCADE)
    saree = models.ForeignKey(Saree, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1, editable=False)  # Always 1, not editable
    added_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('cart', 'saree')
    
    def save(self, *args, **kwargs):
        # Always ensure quantity is 1
        self.quantity = 1
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.saree.name}"
    
    def get_total_price(self):
        return self.saree.price  # Since quantity is always 1

class Order(models.Model):
    saree = models.ForeignKey(Saree, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    
    # Delivery address (linked to Address model for registered users)
    delivery_address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Guest checkout fields (when user is null) - kept for backward compatibility
    guest_name = models.CharField(max_length=200, blank=True)
    guest_email = models.EmailField(blank=True)
    guest_phone = models.CharField(max_length=20, blank=True)
    guest_address = models.TextField(blank=True)
    
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)
    paid = models.BooleanField(default=False)
    amount = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        if self.user:
            return f"Order {self.id} - {self.user.get_full_name()}"
        return f"Order {self.id} - {self.guest_name}"
    
    def get_total_price(self):
        return self.saree.price * self.quantity
    
    def get_delivery_address_display(self):
        """Get formatted delivery address for display"""
        if self.delivery_address:
            return f"{self.delivery_address.full_name}, {self.delivery_address.get_full_address()}, Phone: {self.delivery_address.phone}"
        elif self.guest_address:
            return f"{self.guest_name}, {self.guest_address}, Phone: {self.guest_phone}"
        else:
            return "No address provided"

