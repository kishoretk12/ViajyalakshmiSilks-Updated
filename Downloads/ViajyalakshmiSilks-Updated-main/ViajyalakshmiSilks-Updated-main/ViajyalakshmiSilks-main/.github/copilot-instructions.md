# Copilot Instructions for ViajyalakshmiSilks

## Project Overview
**ViajyalakshmiSilks** is a Django-based e-commerce platform for selling sarees. It features user authentication, shopping cart management, address handling, and Razorpay payment integration. Single product ("Buy Now") and cart-based ("Checkout") purchase flows are both supported.

## Architecture & Key Components

### Core Models (`products/models.py`)
- **Saree**: Product model with `name`, `price`, `description`, and 4 image fields (`main_image` + `extra_image1-3`)
  - Helper method: `get_all_images()` returns list of all available images
- **User**-related:
  - `UserProfile`: OneToOne with Django User; stores `mobile_number`
  - `Address`: ForeignKey to User; manages multiple delivery addresses per user
    - `is_default` field with special `save()` logic: auto-clears other defaults for same user
    - `get_full_address()` method concatenates all address components
- **Cart & CartItem**: OneToOne Cart per User; CartItem has **fixed quantity=1** (not editable)
  - CartItem enforces uniqueness via `unique_together = ('cart', 'saree')`
- **Order**: Represents completed purchases; links to Saree, User (optional for guest), and Address
  - Stores Razorpay IDs and payment signature for verification
  - `get_delivery_address_display()` handles both registered and guest orders

### Data Flow - Two Purchase Paths

#### 1. **Buy Now** (Single Product)
1. User clicks "Buy Now" on shop → `buy_now` view
2. Redirects to `select_address_buy_now` → user picks/adds address
3. Address ID + product_id stored in **session**
4. `process_buy_now_payment` creates **one Order** with selected address
5. Payment page renders; Razorpay captures payment
6. `payment_complete` verifies signature & marks order as paid

#### 2. **Checkout** (Cart)
1. `add_to_cart` creates/gets CartItem (rejects if already in cart)
2. `cart_view` displays cart items with totals
3. `checkout_cart` redirects to address selection
4. `process_checkout_payment` creates **multiple Orders** (one per cart item)
5. Payment flow identical to "Buy Now"
6. `clear_cart_after_payment` empties cart after successful payment

### Key Views & Decorators
- `@login_required`: Protects cart, checkout, address, and payment views
- Session usage: `request.session['selected_address_id']` and `request.session['product_id']` are critical
- AJAX detection: Check `request.headers.get('X-Requested-With') == 'XMLHttpRequest'` for JSON responses

### Payment Integration (`settings.py`)
- **Razorpay credentials stored directly** (production: use environment variables)
- **EMAIL settings configured** for order notifications (Gmail SMTP)
- TIME_ZONE set to `'Asia/Kolkata'` (IST)

## Critical Patterns & Conventions

### 1. Multiple Orders Per Transaction
- **Cart checkout** creates one Order per CartItem (not a single aggregated order)
- Both Buy Now and Checkout can result in multiple Order objects with same `razorpay_order_id`
- `Order.objects.filter(razorpay_order_id=...)` retrieves all items in a transaction

### 2. Guest vs. Registered User Orders
- Registered: Use `delivery_address` ForeignKey (preferred)
- Guest/Legacy: Use `guest_name`, `guest_email`, `guest_phone`, `guest_address` fields
- Check `if order.user:` to determine order type

### 3. Context Processor Pattern
- `products/context_processors.py`: `cart_context()` injects `cart_items_count` and `cart_total_items` into **all templates**
- Registered in `TEMPLATES['OPTIONS']['context_processors']` in settings

### 4. Email Notifications
- `email_utils.send_order_notification_to_admin()` called after payment success
- Non-blocking: Email failures logged but don't interrupt payment flow (try/except in `payment_complete`)
- Handles both single and multiple orders

## Developer Workflows

### Setup & Run
```bash
# Install dependencies
pip install -r requirements.txt

# Apply migrations (note: schema has evolved significantly)
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run development server
python manage.py runserver
```

### Key Database Commands
```bash
# Check migration history
python manage.py showmigrations products

# Create new migration after model changes
python manage.py makemigrations

# Apply pending migrations
python manage.py migrate
```

### Adding/Modifying Models
1. Edit `products/models.py`
2. Run `python manage.py makemigrations` (creates migration file)
3. Review migration file for accuracy (especially data migrations)
4. Run `python manage.py migrate`
5. Update admin.py if needed

## Integration Points & Gotchas

### Razorpay Payment Signature Verification
- Happens in `payment_complete` view using `client.utility.verify_payment_signature()`
- On verification success: update Order(s) with `paid=True`
- **On verification failure**: render `payment_failed.html` (template needs to exist)

### Cart Quantity Always 1
- `CartItem.save()` **forces `quantity=1`** regardless of input
- UI should not show quantity controls for cart items
- This is intentional (not a bug)

### Address Default Logic
- `Address.save()` automatically clears `is_default` on all other addresses for same user
- Prevents data inconsistency when multiple defaults could exist

### Media Files
- Images uploaded to `media/sarees/` directory
- `MEDIA_URL = '/media/'` and `MEDIA_ROOT` configured for serving during development
- Saree model provides `get_all_images()` helper; templates use this for image galleries

## Testing & Debugging Tips

### Common Issues
- **"No address provided" in orders**: Check that `delivery_address` is set; `guest_address` is fallback
- **Cart not persisting**: Ensure user is authenticated before calling `Cart.objects.get_or_create()`
- **Email not sending**: Verify `EMAIL_HOST_PASSWORD` is Gmail App Password (not regular password)
- **Payment verification fails**: Check Razorpay credentials match live/test environment

### Debugging Payments
- Razorpay order IDs stored in `Order.razorpay_order_id`
- Use admin interface to inspect Order records: verify `paid` status, address linkage
- Session data cleared after payment: if debugging, add logging before deletion

## File Structure Reference
- `sareeshop/`: Django project config (settings, urls, wsgi)
- `products/`: Main app (models, views, templates, migrations)
- `templates/`: Global templates + subdirectories for features (auth, address)
- `static/`, `media/`: CSS, images
- `db.sqlite3`: Local development database
