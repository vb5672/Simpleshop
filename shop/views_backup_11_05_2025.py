from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, Order
from .forms import SignUpForm

from django.http import JsonResponse
import razorpay
from django.conf import settings

from django.contrib import messages
from datetime import datetime
from django.utils import timezone
#import random
import uuid
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt

razorpay_client = razorpay.Client(auth=(settings.RAZOR_KEY_ID, settings.RAZOR_KEY_SECRET))

def index_view(request):
    return render(request, 'index.html')

def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        
        # Authenticate the user
        user = authenticate(request, username=username, password=password)
        print('user:', user)
        if user is not None:
            login(request, user)  # Log the user in
            return redirect('product_list')  # Redirect to the cart page after login
        else:
            messages.error(request, 'Invalid username or password')
    
    return render(request, 'login.html')

def signup_view(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            print("form is valid")
            user = form.save()
            print('user:', user)
            login(request, user)
            return redirect('product_list')
    else:
        form = SignUpForm()
    return render(request, 'signup.html', {'form': form})

@login_required
def product_list_view(request):
    products = Product.objects.all()
    return render(request, 'product_list.html', {'products': products})


@login_required
def add_to_cart_view(request, product_id):
    product = Product.objects.get(id=product_id)
    Cart.objects.create(user=request.user, product=product)
    return redirect('product_list')

@login_required
def cart_view(request):
    items = Cart.objects.filter(user=request.user)
    #total = sum(item.product.price * item.quantity for item in items)
    total = 0.0
    for item in items:
        total = total + item.product.price * item.quantity
    return render(request, 'cart.html', {'items': items, 'total': total})

@login_required
def checkout_view(request):
    items = Cart.objects.filter(user=request.user)
    if not items.exists():
        return render(request, 'checkout.html', {'error': "No items in cart."})

    total_amount = 0.0
    created_orders = []
    transaction_id = generate_transaction_id(request.user)

    for item in items:
        order_id = generate_order_id(request.user)
        order_amount = item.product.price * item.quantity
        total_amount += order_amount

        order = Order.objects.create(
            user=request.user,
            order_id=order_id,
            order_amount=order_amount,
            order_date=datetime.now()
        )
        created_orders.append(order)

    # Razorpay amount in paise
    razorpay_amount = int(total_amount * 100)
    notes = f'Transaction number: {transaction_id} ({request.user.first_name})'

    razorpay_order = razorpay_client.order.create({
        'amount': razorpay_amount,
        'currency': 'INR',
        'receipt': transaction_id,
        'payment_capture': 1,
        'notes': {'note_key': notes}
    })

    # Update only the orders created now
    for order in created_orders:
        order.gw_order_id = razorpay_order['id']
        order.transaction_id = transaction_id
        order.save()

    # Save details in session for later use in payment_callback
    request.session['transaction_id'] = transaction_id
    request.session['total_amount'] = total_amount

    context = {
        'razorpay_merchant_key': settings.RAZOR_KEY_ID,
        'razorpay_order_id': razorpay_order['id'],
        'razorpay_amount': razorpay_amount,
        'total_amount': total_amount,
        'currency': 'INR',
        'callback_url': '/payment_callback/',
    }

    return render(request, 'checkout.html', context)


def generate_order_id(user):
    """Generate a unique and traceable order ID."""
    now = datetime.now()
    timestamp = now.strftime("%d%m%Y%H%M%S")  # e.g., 20250507143045
    unique_part = uuid.uuid4().hex[:6].upper()  # Shorten UUID for readability
    return f"ORD{timestamp}{unique_part}"

def generate_transaction_id(user):
        """Generate a unique and traceable order ID."""
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d%H%M%S")  # e.g., 20250507143045
        unique_part = uuid.uuid4().hex[:6].upper()  # Shorten UUID for readability
        return f"TXN{user.id}{timestamp}{unique_part}"
######################

@csrf_exempt
def payment_callback_view(request):
    try:
        transaction_id = request.session.get('transaction_id')
        total_amount = request.session.get('total_amount')

        if not transaction_id:
            return HttpResponseBadRequest("Missing transaction ID.")

        
        razorpay_amount = int(float(total_amount) * 100)  # Convert to paise

        if request.method == "POST":
            razorpay_payment_id = request.POST.get('razorpay_payment_id')
            razorpay_order_id = request.POST.get('razorpay_order_id')
            signature = request.POST.get('razorpay_signature')
            print("payment_id: ", razorpay_payment_id)
            print("\n razorpay_order_id: ",razorpay_order_id)
            print("\n Transaction id: ", transaction_id)
            print("\nAmount: ", razorpay_amount)
            params_dict = {
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': signature
            }

            # Verify the signature
            try:
                razorpay_client.utility.verify_payment_signature(params_dict)
                razorpay_client.payment.capture(razorpay_payment_id, razorpay_amount)

                # Get transaction details
                payment_details = razorpay_client.payment.fetch(razorpay_payment_id)
                contact = payment_details.get('contact', '')
                method = payment_details.get('method', '')
                created_at_timestamp = payment_details.get('created_at')
                payment_date = timezone.make_aware(datetime.fromtimestamp(created_at_timestamp))

                
                # Update orders
                orders = Order.objects.all()
                for order in orders:
                    order.order_status = 'Shipping'
                    order.is_deleted = 'N'
                    order.payment_status = 'Success'
                    order.transaction_id = transaction_id
                    order.gw_order_id = razorpay_order_id
                    order.gw_payment_id = razorpay_payment_id
                    order.gw_response = f"Signature: {signature}"
                    order.description = (
                        f"Customer: {contact}, Method: {method}, Created At: {payment_date}, "
                        f"Signature: {signature}, Details: {payment_details}"
                    )
                    order.total_amount = total_amount
                    order.payment_date = payment_date
                    order.gw_response = f"Signature: {signature}"
                    order.description = (
                    f"Customer: {contact}, Method: {method}, Created At: {payment_date}, "
                    f"Signature: {signature}, Details: {payment_details}"
                    )
                    order.save()

                # Clear cart
                cart = Cart.objects.filter(user=request.user).first()
                if cart:
                    cart.delete()

                messages.success(request, "Payment successful!")
                return render(request,"payment_success.html")

            except razorpay.errors.SignatureVerificationError:
                order.payment_status = 'Failed'
                order.save()
                return HttpResponse("Signature verification failed.", status=400)

        return HttpResponseBadRequest("Invalid request method.")

    # except Payment.DoesNotExist:
    #     return HttpResponse("Invalid transaction.", status=400)

    except Exception as e:
        return HttpResponse(f"Error occurred: {str(e)}", status=500)

###################
