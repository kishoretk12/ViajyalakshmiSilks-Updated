from django.contrib import admin
from django.urls import path
from products import views
urlpatterns = [
    path('', views.home_view, name='home'),
    path('shop/', views.shop_view, name='shop'),
    path('cart/', views.cart_view, name='cart'),
    path('buy/<int:product_id>/', views.buy_now, name='buy_now'),
    path('payment_complete/', views.payment_complete, name='payment_complete'),
    path('admin/', admin.site.urls),
]

