from django.contrib import admin
from .models import Saree, Order

@admin.register(Saree)
class SareeAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'available')

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'saree', 'amount', 'paid', 'created_at')

