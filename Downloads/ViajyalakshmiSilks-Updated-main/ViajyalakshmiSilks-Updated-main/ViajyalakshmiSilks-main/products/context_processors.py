from .models import Cart

def cart_context(request):
    """Add cart information to all templates"""
    cart_items_count = 0
    cart_total_items = 0
    
    if request.user.is_authenticated:
        try:
            cart = Cart.objects.get(user=request.user)
            cart_items_count = cart.get_items_count()
            cart_total_items = cart.get_total_items()
        except Cart.DoesNotExist:
            cart_items_count = 0
            cart_total_items = 0
    
    return {
        'cart_items_count': cart_items_count,
        'cart_total_items': cart_total_items,
    }