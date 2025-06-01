from django.contrib import admin
from .models import Product, Cart, Order,Payment
# Register your models here.

admin.site.register(Product)
admin.site.register(Cart)
admin.site.register(Payment)
admin.site.register(Order)

