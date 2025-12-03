from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from products import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('shop/', views.shop_view, name='shop'),
    path('cart/', views.cart_view, name='cart'),
    path('buy/<int:product_id>/', views.buy_now, name='buy_now'),
    path('payment_complete/', views.payment_complete, name='payment_complete'),
    
    # Cart URLs
    path('add-to-cart/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('remove-from-cart/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('checkout/', views.checkout_cart, name='checkout_cart'),
    path('clear-cart/', views.clear_cart_after_payment, name='clear_cart'),
    
    # Authentication URLs
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    
    # Address Management URLs
    path('address/select-buy-now/<int:product_id>/', views.select_address_buy_now, name='select_address_buy_now'),
    path('address/select-checkout/', views.select_address_checkout, name='select_address_checkout'),
    path('address/add/', views.add_address, name='add_address'),
    path('address/manage/', views.manage_addresses, name='manage_addresses'),
    path('address/edit/<int:address_id>/', views.edit_address, name='edit_address'),
    path('address/delete/<int:address_id>/', views.delete_address, name='delete_address'),
    path('process-buy-now-payment/', views.process_buy_now_payment, name='process_buy_now_payment'),
    path('process-checkout-payment/', views.process_checkout_payment, name='process_checkout_payment'),
    
    path('admin/', admin.site.urls),
]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

