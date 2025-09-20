from django.shortcuts import render, redirect , get_object_or_404
from .models import User, Contact, Product
from .utils import hash_pw, verify_pw, validate_password_complexity
from django.utils import timezone
import json
from pathlib import Path
from django.conf import settings
from django.http import JsonResponse


def require_login(view_fn):
    def wrapper(request, *args, **kwargs):
        user_id = request.session.get('user_id')
        if not user_id:
            return redirect('login')
        try:
            request.user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            request.session.flush()
            return redirect('login')
        return view_fn(request, *args, **kwargs)
    # preserve function attributes (optional)
    wrapper.__name__ = getattr(view_fn, '__name__', 'wrapper')
    return wrapper

def login_view(request):
    if request.method == 'POST':
        u = request.POST.get('username','').strip()
        p = request.POST.get('password','').strip()
        try:
            obj = User.objects.get(username=u)
            if verify_pw(obj.password, p):
                request.session['user_id'] = obj.id
                return redirect('dashboard')
        except User.DoesNotExist:
            pass
        return render(request, 'login.html', {'error':'Invalid credentials'})
    return render(request, 'login.html')

def logout_view(request):
    request.session.flush()
    return redirect('login')

# core/views.py (signup_view)
def signup_view(request):
    """
    Public signup: only creates 'invoicing' users.
    Username length 6-12, password complexity enforced, password confirm.
    Role is not accepted from form and will be set to 'invoicing'.
    """
    if request.method == 'POST':
        full_name = request.POST.get('full_name','').strip()
        username = request.POST.get('username','').strip()
        email = request.POST.get('email','').strip()
        pw = request.POST.get('password','')
        pw2 = request.POST.get('password2','')

        # validation
        if not (6 <= len(username) <= 12):
            return render(request, 'signup.html', {'error': 'Login ID must be 6-12 characters.'})
        if User.objects.filter(username=username).exists():
            return render(request, 'signup.html', {'error':'Login ID already exists.'})

        if pw != pw2:
            return render(request, 'signup.html', {'error':'Passwords do not match.'})
        ok, msg = validate_password_complexity(pw)
        if not ok:
            return render(request, 'signup.html', {'error': msg})

        # create user as invoicing only (server-enforced)
        User.objects.create(username=username, full_name=full_name, password=hash_pw(pw), role='invoicing')
        return render(request, 'signup_success.html', {'username': username})
    return render(request, 'signup.html')

@require_login
def create_user_view(request):
    # allow only if currently logged-in user is admin
    if not getattr(request, 'user', None) or request.user.role != 'admin':
        return render(request, 'error.html', {'message': 'Only admin can create users.'})

    if request.method == 'POST':
        full_name = request.POST.get('full_name','').strip()
        username = request.POST.get('username','').strip()
        email = request.POST.get('email','').strip()
        role = request.POST.get('role','invoicing')  # admin selects this
        pw = request.POST.get('password','')
        pw2 = request.POST.get('password2','')

        if not (6 <= len(username) <= 12):
            return render(request, 'create_user.html', {'error': 'Login ID must be 6-12 characters.'})
        if User.objects.filter(username=username).exists():
            return render(request, 'create_user.html', {'error':'Login ID already exists.'})

        if pw != pw2:
            return render(request, 'create_user.html', {'error':'Passwords do not match.'})
        ok, msg = validate_password_complexity(pw)
        if not ok:
            return render(request, 'create_user.html', {'error': msg})

        User.objects.create(username=username, full_name=full_name, password=hash_pw(pw), role=role)
        return render(request, 'create_user.html', {'success': 'User created successfully.'})

    return render(request, 'create_user.html')



def require_login(fn):
    def wrapper(req, *args, **kwargs):
        if not req.session.get('user_id'):
            return redirect('login')
        req.user = User.objects.get(id=req.session['user_id'])
        return fn(req, *args, **kwargs)
    return wrapper

@require_login
def dashboard(request):
    return render(request, 'dashboard.html', {'user': request.user})

# Contacts
@require_login
def contacts_list(request):
    contacts = Contact.objects.all().order_by('-id')
    return render(request, 'contacts_list.html', {'contacts': contacts})

@require_login
def contacts_add(request):
    if request.method == 'POST':
        Contact.objects.create(
            name=request.POST.get('name'),
            contact_type=request.POST.get('contact_type'),
            email=request.POST.get('email'),
            mobile=request.POST.get('mobile'),
            city=request.POST.get('city'),
            state=request.POST.get('state'),
            pincode=request.POST.get('pincode'),
        )
        return redirect('contacts_list')
    return render(request, 'contacts_add.html')

# Products
@require_login
def products_list(request):
    products = Product.objects.all().order_by('-id')
    return render(request, 'products_list.html', {'products': products})

@require_login
def products_add(request):
    if request.method == 'POST':
        Product.objects.create(
            name=request.POST.get('name'),
            product_type=request.POST.get('product_type','goods'),
            sales_price=request.POST.get('sales_price') or 0,
            purchase_price=request.POST.get('purchase_price') or 0,
            sale_tax_percent=request.POST.get('sale_tax_percent') or 0,
            purchase_tax_percent=request.POST.get('purchase_tax_percent') or 0,
            hsn=request.POST.get('hsn',''),
            category=request.POST.get('category',''),
        )
        return redirect('products_list')
    return render(request, 'products_add.html')

@require_login
def contacts_list(request):
    contacts = Contact.objects.all().order_by('-id')
    return render(request, 'contacts_list.html', {'contacts': contacts})

@require_login
def contacts_add(request):
    if request.method == 'POST':
        Contact.objects.create(
            name = request.POST.get('name'),
            contact_type = request.POST.get('contact_type'),
            email = request.POST.get('email'),
            mobile = request.POST.get('mobile'),
            city = request.POST.get('city'),
            state = request.POST.get('state'),
            pincode = request.POST.get('pincode'),
            profile_image = request.FILES.get('profile_image')  # 👈 handles upload
        )
        return redirect('contacts_list')
    return render(request, 'contacts_add.html')

@require_login
def contacts_detail(request, pk):
    contact = get_object_or_404(Contact, id=pk)
    return render(request, 'contacts_detail.html', {'contact': contact})

# Admin-only edit/delete
@require_login
def contacts_edit(request, pk):
    # only admin allowed to edit (as per your rules)
    if request.user.role != 'admin':
        return render(request, 'error.html', {'message': 'Only admin can edit contacts.'})
    contact = get_object_or_404(Contact, id=pk)
    if request.method == 'POST':
        contact.name = request.POST.get('name')
        contact.contact_type = request.POST.get('contact_type')
        contact.email = request.POST.get('email')
        contact.mobile = request.POST.get('mobile')
        contact.city = request.POST.get('city')
        contact.state = request.POST.get('state')
        contact.pincode = request.POST.get('pincode')

        uploaded = request.FILES.get('profile_image')
        if uploaded:
            contact.profile_image = uploaded

        contact.save()
        return redirect('contacts_detail', pk=contact.id)
    return render(request, 'contacts_edit.html', {'contact': contact})


@require_login
def contacts_delete(request, pk):
    # only admin allowed to delete
    if request.user.role != 'admin':
        return render(request, 'error.html', {'message': 'Only admin can delete contacts.'})
    contact = get_object_or_404(Contact, id=pk)
    if request.method == 'POST':
        contact.delete()
        return redirect('contacts_list')
    return render(request, 'contacts_delete.html', {'contact': contact})

@require_login
def products_list(request):
    products = Product.objects.filter(archived=False).order_by('-id')
    return render(request, 'products_list.html', {'products': products})

@require_login
def products_add(request):
    # Both admin and invoicing can create (per problem statement)
    if request.method == 'POST':
        sales_price = request.POST.get('sales_price') or 0
        purchase_price = request.POST.get('purchase_price') or 0
        p = Product.objects.create(
            name = request.POST.get('name'),
            product_type = request.POST.get('product_type','goods'),
            category = request.POST.get('category',''),
            sales_price = sales_price,
            sale_tax_percent = request.POST.get('sale_tax_percent') or 0,
            purchase_price = purchase_price,
            purchase_tax_percent = request.POST.get('purchase_tax_percent') or 0,
            hsn = request.POST.get('hsn',''),
            image = request.FILES.get('image'),
            created_by = getattr(request, 'user', None)
        )
        return redirect('products_detail', pk=p.id)
    return render(request, 'products_add.html')

@require_login
def products_detail(request, pk):
    p = get_object_or_404(Product, id=pk)
    return render(request, 'products_detail.html', {'product': p})

@require_login
def products_edit(request, pk):
    # Only admin can edit (as per our chosen rule)
    if request.user.role != 'admin':
        return render(request, 'error.html', {'message':'Only admin can edit products.'})
    p = get_object_or_404(Product, id=pk)
    if request.method == 'POST':
        p.name = request.POST.get('name')
        p.product_type = request.POST.get('product_type','goods')
        p.category = request.POST.get('category','')
        p.sales_price = request.POST.get('sales_price') or 0
        p.sale_tax_percent = request.POST.get('sale_tax_percent') or 0
        p.purchase_price = request.POST.get('purchase_price') or 0
        p.purchase_tax_percent = request.POST.get('purchase_tax_percent') or 0
        p.hsn = request.POST.get('hsn','')
        uploaded = request.FILES.get('image')
        if uploaded:
            p.image = uploaded
        p.save()
        return redirect('products_detail', pk=p.id)
    return render(request, 'products_edit.html', {'product': p})

@require_login
def products_delete(request, pk):
    if request.user.role != 'admin':
        return render(request, 'error.html', {'message':'Only admin can delete products.'})
    p = get_object_or_404(Product, id=pk)
    if request.method == 'POST':
        # hard delete:
        p.delete()
        # or to archive: p.archived = True; p.save()
        return redirect('products_list')
    return render(request, 'products_delete.html', {'product': p})

@require_login
def hsn_lookup(request):
    """
    AJAX endpoint: ?q=search-term
    Searches local data/hsn_codes.json for matches on HSN or description.
    Returns JSON: { results: [ {hsn, description}, ... ] }
    """
    q = request.GET.get('q', '').strip().lower()
    results = []
    if not q:
        return JsonResponse({'results': []})

    data_path = Path(settings.BASE_DIR) / 'data' / 'hsn_codes.json'
    try:
        with open(data_path, 'r', encoding='utf-8') as f:
            all_codes = json.load(f)
    except FileNotFoundError:
        return JsonResponse({'results': []})

    for item in all_codes:
        # match either HSN code substring or description contains
        if q in item.get('hsn', '').lower() or q in item.get('description', '').lower():
            results.append(item)
            if len(results) >= 12:
                break
    return JsonResponse({'results': results})

@require_login
def products_by_hsn(request):
    hsn = request.GET.get('hsn', '').strip()
    if not hsn:
        return JsonResponse({'results': []})
    # find products with exact HSN (or startswith/contains if you prefer)
    qs = Product.objects.filter(hsn__iexact=hsn)
    results = []
    for p in qs:
        results.append({
            'id': p.id,
            'name': p.name,
            'sales_price': str(p.sales_price),
            'sale_tax_percent': str(p.sale_tax_percent),
            'purchase_price': str(p.purchase_price),
            'purchase_tax_percent': str(p.purchase_tax_percent),
            'category': p.category or '',
            'image_url': p.image.url if p.image else '',
        })
    return JsonResponse({'results': results})