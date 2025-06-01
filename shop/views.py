from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, Order, Payment
from .forms import SignUpForm
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
import razorpay
from django.conf import settings
from django.contrib import messages
from datetime import datetime
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
import uuid

razorpay_client = razorpay.Client(auth=(settings.RAZOR_KEY_ID, settings.RAZOR_KEY_SECRET))

def index_view(request):
    return render(request, 'index.html')

def logout_view(request):
    if request.user.is_authenticated:
        print("logout")
        # django.contrib.auth import login, authenticate, logout
        # logout from auth must be imported
        # or 
        # if you from django.contrib import auth
        # then auth.logout 
        logout(request)
    return redirect("/")


def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('product_list')
        else:
            messages.error(request, 'Invalid username or password')
    return render(request, 'login.html')

def signup_view(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('product_list')
    else:
        form = SignUpForm()
    return render(request, 'signup.html', {'form': form})


def product_list_view(request):
    products = Product.objects.all()
    context = {'products': products}
    if request.user.is_authenticated:        
        cart_count = Cart.objects.filter(user=request.user).count()
        context.update({'cart_count': cart_count})

    return render(request, 'product_list.html',context)

@login_required
def add_to_cart_view(request, product_id):
    product = Product.objects.get(id=product_id)
    Cart.objects.create(user=request.user, product=product)
    
    return redirect('product_list')
    

@login_required
def cart_view(request):
    items = Cart.objects.filter(user=request.user)
    error = ''
    if not items.exists():
        total = 0.0
        error = {'error': "No items in cart.", 'total': total}
        return render(request, 'cart.html', error)
    #total = sum(item.product.price * item.quantity for item in items)
    total = 0.0
    for item in items:
        total = total + (item.product.price * item.quantity)
    context = {'items': items, 'total': total}
    context.update(error)
    return render(request, 'cart.html', {'items': items, 'total': total})

@login_required
def checkout_view(request):
    items = Cart.objects.filter(user=request.user)
    if not items.exists():
        return render(request, 'checkout.html', {'error': "No items in cart."})

    total_amount = sum(item.product.price * item.quantity for item in items)
    transaction_id = generate_transaction_id(request.user)

    payment = Payment.objects.create(
        user=request.user,
        transaction_id=transaction_id,
        amount=total_amount,
        gw_order_id='',  # to be filled after razorpay order
        gw_payment_id='',
        gw_response='',
        description=''
    )
    notes = f"{transaction_id}"
    razorpay_order = razorpay_client.order.create({
        'amount': int(total_amount * 100),
        'currency': 'INR',
        'receipt': transaction_id,
        'payment_capture': 0,
        'notes': {'note_key': notes}
    })

    payment.gw_order_id = razorpay_order['id']
    payment.save()

    for item in items:
        existing_order = Order.objects.filter(
            user=request.user,
            product=item.product,
            payment=payment
        ).first()
        print("existing_order: ",existing_order)

        if not existing_order:
            print("Order not existing")
            Order.objects.create(
                user=request.user,
                product=item.product,
                quantity=item.quantity,
                order_amount=item.product.price * item.quantity,
                order_id=generate_order_id(request.user),
                payment=payment
            )

    request.session['transaction_id'] = transaction_id
    request.session['total_amount'] = total_amount
    
    razorpay_amount = int(total_amount * 100)
    currency = 'INR'
    context = {
        'razorpay_merchant_key': settings.RAZOR_KEY_ID,
        'razorpay_order_id': razorpay_order['id'],
        'razorpay_amount': razorpay_amount,
        'currency': currency,
        'currency_symbol':'₹',
        'total_amount': total_amount,
        'callback_url': '/payment_callback/',
    }

    return render(request, 'checkout.html', context)

def generate_order_id(user):
    now = datetime.now()
    timestamp = now.strftime("%d%m%Y%H%M%S")
    unique_part = uuid.uuid4().hex[:6].upper()
    return f"ORD-{timestamp}-{unique_part}"

def generate_transaction_id(user):
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d%H%M%S")
    unique_part = uuid.uuid4().hex[:6].upper()
    return f"TXN-{user.id}-{timestamp}-{unique_part}"

@csrf_exempt
def payment_callback_view(request):
    try:
        # Fetch transaction_id and total_amount from session
        transaction_id = request.session.get('transaction_id')
        total_amount = request.session.get('total_amount')
        if not transaction_id or not total_amount:
            return HttpResponseBadRequest("Missing transaction/session info.")

        # Check if payment exists for this transaction_id
        payment = Payment.objects.filter(transaction_id=transaction_id).first()
        if payment and payment.status == 'Success':
            return HttpResponse("Payment already processed.", status=400)

        if request.method == "POST":
            razorpay_payment_id = request.POST.get('razorpay_payment_id')
            razorpay_order_id = request.POST.get('razorpay_order_id')
            signature = request.POST.get('razorpay_signature')

            # Verify the payment signature
            params_dict = {
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': signature
            }

            razorpay_client.utility.verify_payment_signature(params_dict)
            razorpay_client.payment.capture(razorpay_payment_id, int(float(total_amount) * 100))
            payment_details = razorpay_client.payment.fetch(razorpay_payment_id)

            # Update Payment object
            payment.status = 'Success'
            payment.gw_payment_id = razorpay_payment_id
            payment.gw_response = str(payment_details)
            payment.description = (
                f"Customer: {payment_details.get('contact', '')}, "
                f"Method: {payment_details.get('method', '')} "
            )
            payment.payment_date = timezone.make_aware(datetime.fromtimestamp(payment_details['created_at']))
            payment.save()

            # Update related orders
            orders = Order.objects.filter(payment=payment)
            for order in orders:
                order.order_status = 'Shipped'
                order.paid = True
                order.save()

            # Clear cart
            Cart.objects.filter(user=request.user).delete()

            messages.success(request, "Payment successful!")
            return render(request, "payment_success.html")

        return HttpResponseBadRequest("Invalid request method.")

    except razorpay.errors.SignatureVerificationError:
        messages.error(request, "Payment failed due to signature verification.")
        return HttpResponse("Signature verification failed.", status=400)

    except Payment.DoesNotExist:
        return HttpResponse("Payment not found.", status=404)

    except Exception as e:
        return HttpResponse(f"Error: {str(e)}", status=500)