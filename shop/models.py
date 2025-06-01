from django.db import models

# Create your models here.
from django.db import models
from django.contrib.auth.models import User
from datetime import datetime

class Product(models.Model):
    name = models.CharField(max_length=100)
    price = models.FloatField()

    def __str__(self):
        return self.name

class Cart(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.user.username} - {self.product.name}"

class Payment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    transaction_id = models.CharField(max_length=100, unique=True)
    
    amount = models.FloatField()
    status = models.CharField(max_length=50, default='Pending')  # e.g., Success, Failed
    created_at = models.DateTimeField(auto_now_add=True)
    gw_order_id = models.CharField(max_length=100)
    gw_payment_id = models.CharField(max_length=100)
    gw_response = models.TextField()
    description = models.TextField()
    payment_date = models.DateTimeField(auto_now_add=True)
        
    def __str__(self):
        return f"{self.user.username} - {self.transaction_id}"
    
class Order(models.Model):
    ORDER_STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Shipped', 'Shipped'),
        ('Delivered', 'Delivered'),
        ('Cancelled', 'Cancelled'),
        ('Returned', 'Returned'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    order_date = models.DateTimeField(auto_now_add=True)
    order_id = models.CharField(max_length=100, unique=True)
    order_amount = models.FloatField()
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True)
    order_status = models.CharField(max_length=50, choices=ORDER_STATUS_CHOICES, default='Pending')
    is_deleted = models.BooleanField(default=False)
    paid = models.BooleanField(default=False)
    
    def save(self, *args, **kwargs):
        if not self.order_id:
            self.order_id = self.generate_order_id()  # Ensure order_id is set
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Order {self.order_id} by {self.user.username}"

    

