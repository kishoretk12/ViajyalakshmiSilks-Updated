from django.shortcuts import render, get_object_or_404, redirect
from django.conf import settings
import razorpay
from .models import Saree, Order

client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

def home_view(request):
    return render(request, 'home.html')

def shop_view(request):
    sarees = Saree.objects.filter(available=True)
    return render(request, 'shop.html', {'sarees': sarees})

def buy_now(request, product_id):
    saree = get_object_or_404(Saree, id=product_id, available=True)
    amount = saree.price * 100  # paise
    razorpay_order = client.order.create({'amount': amount, 'currency': 'INR', 'payment_capture': '1'})
    order = Order.objects.create(saree=saree, amount=saree.price, razorpay_order_id=razorpay_order['id'])
    return render(request, 'payment.html', {
        'order': order,
        'order_id': razorpay_order['id'],
        'amount': amount,
        'razorpay_key': settings.RAZORPAY_KEY_ID,
        'saree': saree,
    })

def payment_complete(request):
    if request.method == 'POST':
        payment_id = request.POST.get('razorpay_payment_id')
        order_id = request.POST.get('razorpay_order_id')
        signature = request.POST.get('razorpay_signature')
        order = Order.objects.get(razorpay_order_id=order_id)
        params = { 'razorpay_order_id': order_id, 'razorpay_payment_id': payment_id, 'razorpay_signature': signature }
        try:
            client.utility.verify_payment_signature(params)
            order.paid = True
            order.save()
            return render(request, 'thankyou.html', {'saree': order.saree})
        except:
            return render(request, 'payment_failed.html')
    return redirect('shop')

def cart_view(request):
    return render(request, 'cart.html')

