from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic.base import RedirectView
from products import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('shop/', views.shop_view, name='shop'),
    path('cart/', views.cart_view, name='cart'),
    path('buy/<slug:slug>/', views.buy_now, name='buy_now'),
    path('payment_complete/', views.payment_complete, name='payment_complete'),
    
    # Cart URLs
    path('add-to-cart/<slug:slug>/', views.add_to_cart, name='add_to_cart'),
    path('update-cart-quantity/', views.update_cart_quantity, name='update_cart_quantity'),
    path('remove-from-cart/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('checkout/', views.checkout_cart, name='checkout_cart'),
    path('clear-cart/', views.clear_cart_after_payment, name='clear_cart'),
    path('apply-coupon/', views.apply_coupon, name='apply_coupon'),
    path('remove-coupon/', views.remove_coupon, name='remove_coupon'),

    
    # Authentication URLs
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('verify-signup-otp/', views.verify_signup_otp, name='verify_signup_otp'),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('reset-password/', views.reset_password, name='reset_password'),
    path('logout/', views.logout_view, name='logout'),
    path('accounts/', include('allauth.urls')), # Google Auth
    path('profile/', views.profile_view, name='profile'),
    path('order/<int:order_id>/', views.order_detail_view, name='order_detail'),
    
    path('address/select-buy-now/<slug:slug>/', views.select_address_buy_now, name='select_address_buy_now'),
    path('collection/<slug:slug>/', RedirectView.as_view(url='/collections/%(slug)s/', permanent=True)),
    path('collections/<slug:slug>/', views.collection_detail, name='collection_detail'),
    path('product/<slug:slug>/', views.product_detail, name='product_detail'),
    path('address/select-checkout/', views.select_address_checkout, name='select_address_checkout'),
    path('address/add/', views.add_address, name='add_address'),
    path('address/manage/', views.manage_addresses, name='manage_addresses'),
    path('address/edit/<int:address_id>/', views.edit_address, name='edit_address'),
    path('address/delete/<int:address_id>/', views.delete_address, name='delete_address'),
    path('process-buy-now-payment/', views.process_buy_now_payment, name='process_buy_now_payment'),
    path('process-checkout-payment/', views.process_checkout_payment, name='process_checkout_payment'),
    path('create-stripe-session/', views.create_stripe_session, name='create_stripe_session'),
    path('stripe-success/', views.stripe_success, name='stripe_success'),
    path('stripe-cancel/', views.stripe_cancel, name='stripe_cancel'),
    path('test-payment/', views.custom_test_payment, name='custom_test_payment'),
    path('initiate-razorpay-checkout/', views.initiate_razorpay_checkout, name='initiate_razorpay_checkout'),
    path('verify-razorpay-payment/', views.verify_razorpay_payment, name='verify_razorpay_payment'),
    
    path('management/', include('dashboard.urls')),
    path('sitemap.xml', views.sitemap_xml, name='sitemap_xml'),
    path('robots.txt', views.robots_txt, name='robots_txt'),
    path('location/', views.location_view, name='location'),
    path('admin/', admin.site.urls),
]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

