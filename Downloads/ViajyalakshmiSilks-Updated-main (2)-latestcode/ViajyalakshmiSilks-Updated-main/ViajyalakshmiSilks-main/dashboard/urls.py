from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_home, name='dashboard_home'),
    
    # Products
    path('products/', views.dashboard_products, name='dashboard_products'),
    path('products/add/', views.product_add, name='product_add'),
    path('products/edit/<int:pk>/', views.product_edit, name='product_edit'),
    path('products/delete/<int:pk>/', views.product_delete, name='product_delete'),
    path('products/toggle-status/<int:pk>/', views.toggle_product_status, name='toggle_product_status'),
    
    # Orders
    path('orders/', views.dashboard_orders, name='dashboard_orders'),
    path('orders/<int:pk>/', views.order_detail, name='dashboard_order_detail'),
    path('orders/<int:pk>/status/', views.update_order_status, name='update_order_status'),
    path('orders/<int:pk>/edit-invoice/', views.edit_invoice, name='edit_invoice'),
    path('orders/<int:pk>/print/invoice/', views.print_invoice, name='print_invoice'),
    path('orders/<int:pk>/print/label/', views.print_shipping_label, name='print_shipping_label'),
    path('orders/export/csv/', views.export_orders_csv, name='export_orders_csv'),
    
    # Collections
    path('collections/', views.dashboard_collections, name='dashboard_collections'),
    path('collections/add/', views.collection_add, name='collection_add'),
    path('collections/edit/<int:pk>/', views.collection_edit, name='collection_edit'),
    path('collections/delete/<int:pk>/', views.collection_delete, name='collection_delete'),
    
    # Customers
    path('customers/', views.dashboard_customers, name='dashboard_customers'),
    path('customers/delete/<int:pk>/', views.customer_delete, name='customer_delete'),

    
    # Coupons
    path('coupons/', views.dashboard_coupons, name='dashboard_coupons'),
    path('coupons/add/', views.coupon_add, name='coupon_add'),
    path('coupons/edit/<int:pk>/', views.coupon_edit, name='coupon_edit'),
    path('coupons/delete/<int:pk>/', views.coupon_delete, name='coupon_delete'),

    
    # Settings
    path('settings/', views.dashboard_settings, name='dashboard_settings'),
    path('settings/verify/', views.verify_admin_changes, name='verify_admin_changes'),
]
