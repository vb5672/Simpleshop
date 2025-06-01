from django.urls import path
from . import views

urlpatterns = [
    path('', views.product_list_view),
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),  # Add login URL
    path('products/', views.product_list_view, name='product_list'),
    path('logout/', views.logout_view, name='logout'),  # Add logout URL    
    path('add-to-cart/<int:product_id>/', views.add_to_cart_view, name='add_to_cart'),
    path('cart/', views.cart_view, name='cart'),
    path('checkout/', views.checkout_view, name='checkout'),
    path('payment_callback/', views.payment_callback_view, name='payment_callback'),
]
