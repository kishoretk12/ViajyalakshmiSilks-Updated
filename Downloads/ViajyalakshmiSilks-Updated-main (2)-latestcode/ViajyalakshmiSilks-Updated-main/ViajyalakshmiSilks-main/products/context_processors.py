from django.contrib.auth.models import User
from .models import SiteSettings, Cart

def site_settings(request):
    """
    Makes the site settings available to all templates globally.
    """
    return {
        'site_settings': SiteSettings.load()
    }

def cart_context(request):
    """
    Makes the cart total items, price and a mapping of items available globally.
    """
    if request.user.is_authenticated:
        try:
            cart = Cart.objects.get(user=request.user)
            # Create a mapping: {saree_id: {'id': cart_item_id, 'quantity': quantity}}
            cart_data = {item.saree.id: {'id': item.id, 'quantity': item.quantity} 
                         for item in cart.items.all()}
            return {
                'cart_total_items': cart.get_total_items(),
                'cart_total_price': cart.get_total_price(),
                'cart_items_map': cart_data,
            }
        except Cart.DoesNotExist:
            pass
            
    return {
        'cart_total_items': 0,
        'cart_total_price': 0,
        'cart_items_map': {},
    }