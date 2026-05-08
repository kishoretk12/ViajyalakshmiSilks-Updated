# products/models.py
from django.db import models

class Saree(models.Model):
    name = models.CharField(max_length=200)
    price = models.PositiveIntegerField()
    description = models.TextField(blank=True)
    main_image = models.ImageField(upload_to='sarees/')
    available = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class Order(models.Model):
    saree = models.ForeignKey(Saree, on_delete=models.CASCADE)
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    paid = models.BooleanField(default=False)
    amount = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

