from django.shortcuts import render, redirect , get_object_or_404
from django.core.paginator import Paginator
from .models import *
from .utils import hash_pw, verify_pw, validate_password_complexity
from django.utils import timezone
import json
from pathlib import Path
from django.conf import settings
from django.http import JsonResponse
import requests
import traceback
from django.core.cache import cache
from django.contrib import messages
from django.urls import reverse
from decimal import Decimal,InvalidOperation
from datetime import date
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
import calendar
from django.db.models import Sum

DATE_FMT = "%Y-%m-%d"

def _parse_date(s):
    try:
        return datetime.strptime(s, DATE_FMT).date()
    except Exception:
        return None

def profit_and_loss(request):
    # parse optional start/end
    start = _parse_date(request.GET.get('start'))
    end = _parse_date(request.GET.get('end'))
    if not start or not end:
        today = timezone.localdate()
        start = date(today.year, today.month, 1)
        last_day = calendar.monthrange(today.year, today.month)[1]
        end = date(today.year, today.month, last_day)

    expenses_qs = (JournalLine.objects
                   .filter(account__account_type__iexact='expense', entry__date__range=(start, end))
                   .values('account__id', 'account__name')
                   .annotate(amount=Sum('debit'))
                   .order_by('account__name'))

    income_qs = (JournalLine.objects
                 .filter(account__account_type__iexact='income', entry__date__range=(start, end))
                 .values('account__id', 'account__name')
                 .annotate(amount=Sum('credit'))
                 .order_by('account__name'))

    # fallback to full history if nothing in range (useful during dev)
    fallback = False
    if not expenses_qs.exists() and not income_qs.exists():
        fallback = True
        expenses_qs = (JournalLine.objects
                       .filter(account__account_type__iexact='expense')
                       .values('account__id','account__name')
                       .annotate(amount=Sum('debit'))
                       .order_by('account__name'))
        income_qs = (JournalLine.objects
                     .filter(account__account_type__iexact='income')
                     .values('account__id','account__name')
                     .annotate(amount=Sum('credit'))
                     .order_by('account__name'))

    expenses = [{'account_id': r['account__id'], 'account': r['account__name'], 'amount': (r['amount'] or Decimal('0.00'))} for r in expenses_qs]
    income = [{'account_id': r['account__id'], 'account': r['account__name'], 'amount': (r['amount'] or Decimal('0.00'))} for r in income_qs]

    total_expenses = sum((e['amount'] for e in expenses), Decimal('0.00'))
    total_income = sum((i['amount'] for i in income), Decimal('0.00'))
    net = total_income - total_expenses

    ctx = {
        'start': start, 'end': end,
        'expenses': expenses, 'income': income,
        'total_expenses': total_expenses, 'total_income': total_income,
        'net': net, 'fallback_full_history': fallback,
    }
    return render(request, 'reports/pnl.html', ctx)

def parse_date_safe(s):
    """Convert posted string into a date object, or return None if invalid."""
    if not s:
        return None
    try:
        return date.fromisoformat(s)  # handles 'YYYY-MM-DD'
    except Exception:
        pass
    for fmt in ("%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None

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
    qs = Product.objects.order_by('name')
    # optional: simple pagination
    page = request.GET.get('page', 1)
    paginator = Paginator(qs, 20)
    try:
        products = paginator.get_page(page)
    except:
        products = paginator.get_page(1)

    # Provide all taxes for filters or product add link
    taxes = Tax.objects.filter(active=True).order_by('value')

    return render(request, 'products_list.html', {
        'products': products,
        'taxes': taxes,
    })

@require_login
def products_add(request):
    taxes = Tax.objects.filter(active=True).order_by('name')
    if request.method == 'POST':
        p = Product.objects.create(
            name = request.POST.get('name',''),
            product_type = request.POST.get('product_type','goods'),
            category = request.POST.get('category',''),
            sales_price = request.POST.get('sales_price') or 0,
            purchase_price = request.POST.get('purchase_price') or 0,
            hsn = request.POST.get('hsn',''),
            image = request.FILES.get('image'),
            created_by = str(request.user) if getattr(request, 'user', None) else None
        )
        # assign tax FKs if posted:
        sale_tax_id = request.POST.get('sale_tax_id')
        purchase_tax_id = request.POST.get('purchase_tax_id')
        if sale_tax_id:
            p.sale_tax_id = int(sale_tax_id)
        if purchase_tax_id:
            p.purchase_tax_id = int(purchase_tax_id)
        p.save()
        return redirect('products_list')
    return render(request, 'products_add.html', {'taxes': taxes})
    
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

# @require_login
# def products_add(request):
#     # Both admin and invoicing can create (per problem statement)
#     if request.method == 'POST':
#         sales_price = request.POST.get('sales_price') or 0
#         purchase_price = request.POST.get('purchase_price') or 0
#         p = Product.objects.create(
#             name = request.POST.get('name'),
#             product_type = request.POST.get('product_type','goods'),
#             category = request.POST.get('category',''),
#             sales_price = sales_price,
#             sale_tax_percent = request.POST.get('sale_tax_percent') or 0,
#             purchase_price = purchase_price,
#             purchase_tax_percent = request.POST.get('purchase_tax_percent') or 0,
#             hsn = request.POST.get('hsn',''),
#             image = request.FILES.get('image'),
#             created_by = getattr(request, 'user', None)
#         )
#         return redirect('products_detail', pk=p.id)
#     return render(request, 'products_add.html')

@require_login
def products_add(request):
    taxes = Tax.objects.filter(active=True).order_by('value')  # if you want to show taxes in form
    if request.method == 'POST':
        # Basic values that most Product models will accept
        name = request.POST.get('name') or ''
        product_type = request.POST.get('product_type', 'goods')
        category = request.POST.get('category', '')
        sales_price = request.POST.get('sales_price') or 0
        purchase_price = request.POST.get('purchase_price') or 0
        hsn = request.POST.get('hsn','')
        created_by = str(request.user) if getattr(request, 'user', None) else None

        # Create product WITHOUT passing unknown keyword args
        p = Product.objects.create(
            name = name,
            product_type = product_type,
            category = category,
            sales_price = sales_price,
            purchase_price = purchase_price,
            hsn = hsn,
            created_by = created_by,
            image = request.FILES.get('image')  # safe; will be None if not provided
        )

        # Now assign tax fields safely:
        # If your form sends sale_tax_id / purchase_tax_id (recommended)
        sale_tax_id = request.POST.get('sale_tax_id')
        purchase_tax_id = request.POST.get('purchase_tax_id')

        if sale_tax_id:
            # assign FK by id (works if Product has a ForeignKey field named sale_tax or sale_tax_id)
            try:
                # prefer setting the *_id attribute if model has it, otherwise try attribute name
                if hasattr(p, 'sale_tax_id'):
                    p.sale_tax_id = int(sale_tax_id)
                elif hasattr(p, 'sale_tax'):
                    p.sale_tax = Tax.objects.get(id=int(sale_tax_id))
            except Exception:
                pass

        if purchase_tax_id:
            try:
                if hasattr(p, 'purchase_tax_id'):
                    p.purchase_tax_id = int(purchase_tax_id)
                elif hasattr(p, 'purchase_tax'):
                    p.purchase_tax = Tax.objects.get(id=int(purchase_tax_id))
            except Exception:
                pass

        # Support legacy percent-named fields only if model has them
        sale_percent = request.POST.get('sale_tax_percent')
        purchase_percent = request.POST.get('purchase_tax_percent')
        if sale_percent is not None and sale_percent != '':
            if hasattr(p, 'sale_tax_percent'):
                try:
                    p.sale_tax_percent = float(sale_percent)
                except:
                    pass
        if purchase_percent is not None and purchase_percent != '':
            if hasattr(p, 'purchase_tax_percent'):
                try:
                    p.purchase_tax_percent = float(purchase_percent)
                except:
                    pass

        p.save()
        return redirect('products_detail', pk=p.id)

    return render(request, 'products_add.html', {'taxes': taxes})

@require_login
def products_detail(request, pk):
    p = get_object_or_404(Product, id=pk)
    return render(request, 'products_detail.html', {'product': p})

# @require_login
# def products_edit(request, pk):
#     # Only admin can edit (as per our chosen rule)
#     if request.user.role != 'admin':
#         return render(request, 'error.html', {'message':'Only admin can edit products.'})
#     p = get_object_or_404(Product, id=pk)
#     if request.method == 'POST':
#         p.name = request.POST.get('name')
#         p.product_type = request.POST.get('product_type','goods')
#         p.category = request.POST.get('category','')
#         p.sales_price = request.POST.get('sales_price') or 0
#         p.sale_tax_percent = request.POST.get('sale_tax_percent') or 0
#         p.purchase_price = request.POST.get('purchase_price') or 0
#         p.purchase_tax_percent = request.POST.get('purchase_tax_percent') or 0
#         p.hsn = request.POST.get('hsn','')
#         uploaded = request.FILES.get('image')
#         if uploaded:
#             p.image = uploaded
#         p.save()
#         return redirect('products_detail', pk=p.id)
#     return render(request, 'products_edit.html', {'product': p})

@require_login
def products_edit(request, pk):
    # admin-only edit as you prefer
    if getattr(request.user, 'role', '') != 'admin':
        return render(request, 'error.html', {'message':'Only admin can edit products.'})
    p = get_object_or_404(Product, id=pk)
    taxes = Tax.objects.filter(active=True).order_by('name')
    if request.method == 'POST':
        p.name = request.POST.get('name','') or p.name
        p.product_type = request.POST.get('product_type','goods')
        p.category = request.POST.get('category','')
        p.sales_price = request.POST.get('sales_price') or p.sales_price or 0
        p.purchase_price = request.POST.get('purchase_price') or p.purchase_price or 0
        p.hsn = request.POST.get('hsn','') or p.hsn
        sale_tax_id = request.POST.get('sale_tax_id')
        purchase_tax_id = request.POST.get('purchase_tax_id')
        if sale_tax_id:
            p.sale_tax_id = int(sale_tax_id)
        else:
            p.sale_tax = None
        if purchase_tax_id:
            p.purchase_tax_id = int(purchase_tax_id)
        else:
            p.purchase_tax = None
        uploaded = request.FILES.get('image')
        if uploaded:
            p.image = uploaded
        p.save()
        return redirect('products_detail', pk=p.id)
    return render(request, 'products_edit.html', {'product': p, 'taxes': taxes})

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

# @require_login
def _call_gst_api(input_text, selected_type, category):
    """
    Call GST HSN endpoint once with given params.
    Returns parsed json body or None on failure.
    """
    gst_base = "https://services.gst.gov.in/commonservices/hsn/search/qsearch"
    params = {'inputText': input_text, 'selectedType': selected_type, 'category': category}
    headers = {
        # Real browser UA helps avoid simple bot blocks
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        # Add Referer/Origin like a browser might send
        'Referer': 'https://services.gst.gov.in/',
        'Origin': 'https://services.gst.gov.in'
    }
    try:
        # use session for connection reuse
        s = requests.Session()
        resp = s.get(gst_base, params=params, headers=headers, timeout=10)
        # print useful debug
        print(f"[gst_hsn_lookup] GET {resp.url} -> status {resp.status_code}")
        # show a small snippet of body for debugging (do NOT log huge bodies in prod)
        body_snippet = resp.text[:800].replace('\n',' ')
        print("[gst_hsn_lookup] body snippet:", body_snippet)
        if resp.status_code == 200:
            try:
                return resp.json()
            except Exception as e:
                print("[gst_hsn_lookup] JSON parse failed:", e)
                return None
        else:
            return None
    except Exception as exc:
        print("[gst_hsn_lookup] network/exception:", exc)
        print(traceback.format_exc())
        return None


# @require_login
@require_login
def gst_hsn_lookup(request):
    q = (request.GET.get('q') or '').strip()
    if not q:
        return JsonResponse({'results': []})

    # API call
    attempts = [('byCode','null'), ('byDesc','P'), ('byDesc','S')] if q.isdigit() else [('byDesc','P'), ('byDesc','S'), ('byCode','null')]
    results = []

    for sel_type, cat in attempts:
        r = _call_gst_api_debug(q, sel_type, cat)
        if r.get('ok') and isinstance(r.get('json'), dict):
            body = r['json']
            data = body.get('data')
            if isinstance(data, list):
                for item in data:
                    hsn = item.get('c') or item.get('hsn')
                    desc = item.get('n') or item.get('description')
                    if hsn:
                        results.append({'hsn': hsn, 'description': desc})
                if results:
                    break
    return JsonResponse({'results': results})


def _call_gst_api_debug(input_text, selected_type, category, verify_ssl=True):
    gst_base = "https://services.gst.gov.in/commonservices/hsn/search/qsearch"
    params = {'inputText': input_text, 'selectedType': selected_type, 'category': category}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://services.gst.gov.in/',
        'Origin': 'https://services.gst.gov.in'
    }
    try:
        s = requests.Session()
        resp = s.get(gst_base, params=params, headers=headers, timeout=12, verify=verify_ssl)
        print(f"[gst_hsn_lookup] GET {resp.url} -> status {resp.status_code}")
        snippet = (resp.text or '')[:1200].replace('\n',' ')
        print("[gst_hsn_lookup] body snippet:", snippet[:1000])
        # try parse json safely
        try:
            body_json = resp.json()
        except Exception:
            body_json = None
        return {'ok': True, 'status': resp.status_code, 'text': resp.text, 'json': body_json}
    except Exception as e:
        tb = traceback.format_exc()
        print("[gst_hsn_lookup] exception while calling gst:", e)
        print(tb)
        return {'ok': False, 'error': str(e), 'traceback': tb}

@require_login
def ajax_create_tax_from_hsn(request):
    hsn = (request.GET.get('hsn') or '').strip()
    if not hsn:
        return JsonResponse({'ok': False, 'error': 'missing hsn'})

    cache_key = f"tax_api_rate:{hsn}"
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse({'ok': True, **cached})

    # 1) Try remote TAX API if configured
    api_base = getattr(settings, 'TAX_API_BASE', None)
    rate = None
    api_source = None
    raw_resp = None
    if api_base:
        try:
            resp = requests.get(api_base, params={'hsn': hsn}, headers={'Accept': 'application/json'}, timeout=8)
            raw_resp = {'status_code': resp.status_code, 'text_snippet': (resp.text or '')[:1000]}
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except Exception as e:
                    data = None
                    raw_resp['json_error'] = str(e)

                # parse multiple likely shapes
                if isinstance(data, dict):
                    for key in ('rate', 'gst_rate', 'value', 'sale_rate', 'purchase_rate'):
                        if key in data and data[key] not in (None, ''):
                            try:
                                rate = float(data[key])
                                api_source = 'remote'
                                break
                            except Exception:
                                continue
                    # maybe nested data list
                    if rate is None and isinstance(data.get('data'), list) and data['data']:
                        item = data['data'][0]
                        for key in ('rate','gst_rate','value'):
                            if key in item:
                                try:
                                    rate = float(item[key])
                                    api_source = 'remote'
                                    break
                                except:
                                    continue
                # if data is a list directly
                elif isinstance(data, list) and data:
                    item = data[0]
                    if isinstance(item, dict):
                        for key in ('rate','gst_rate','value'):
                            if key in item:
                                try:
                                    rate = float(item[key])
                                    api_source = 'remote'
                                    break
                                except:
                                    continue
        except Exception as e:
            raw_resp = {'network_error': str(e)}
            # move on to fallback below

    # 2) If remote didn't yield a rate, use local fallback JSON (if exists)
    if rate is None:
        try:
            data_path = Path(settings.BASE_DIR) / 'data' / 'hsn_tax_map.json'
            if data_path.exists():
                with open(data_path, 'r', encoding='utf-8') as f:
                    mapping = json.load(f)
                # try exact, then zero-padded 4-digit code (common), then startswith
                entry = mapping.get(hsn) or mapping.get(hsn.zfill(4))
                if not entry:
                    # some local maps store list or nested object
                    # attempt case-insensitive lookup by iterating keys
                    for k, v in mapping.items():
                        if str(k).strip() == str(hsn).strip():
                            entry = v
                            break
                if entry:
                    # entry may be dict with 'gst_rate' or 'rate' etc.
                    for key in ('gst_rate','rate','value'):
                        if key in entry and entry[key] not in (None, ''):
                            try:
                                rate = float(entry[key])
                                api_source = 'local'
                                break
                            except:
                                continue
                    # if entry is a numeric value
                    if rate is None:
                        try:
                            # allow entry to be plain value like "5" or 5
                            rate = float(entry)
                            api_source = 'local'
                        except:
                            rate = None
        except Exception as e:
            # ignore - we'll return error below if still no rate
            print("[ajax_create_tax_from_hsn] local fallback error:", e)

    if rate is None:
        # helpful server-side debug - returns raw_resp when DEBUG
        debug = {}
        if getattr(settings, 'DEBUG', False):
            debug['api_raw'] = raw_resp
            data_path = str(Path(settings.BASE_DIR) / 'data' / 'hsn_tax_map.json')
            debug['local_data_path'] = data_path
        return JsonResponse({'ok': False, 'error': 'no rate returned by tax API or local fallback', 'debug': debug})

    # create/find Tax master (ensure consistent naming)
    tax_name = f"GST {int(rate)}%" if float(rate).is_integer() else f"GST {rate}%"
    tax, created = Tax.objects.get_or_create(
        name=tax_name,
        defaults={'value': rate, 'computation': Tax.COMPUTE_PERCENT, 'apply_on': Tax.APPLY_BOTH, 'active': True}
    )
    # if found but value different, update
    if not created and float(tax.value) != float(rate):
        tax.value = rate
        tax.save(update_fields=['value'])

    out = {'tax_id': tax.id, 'rate': float(tax.value), 'name': tax.name, 'source': api_source or 'unknown'}
    cache.set(cache_key, out, 3600)  # cache 1 hour
    return JsonResponse({'ok': True, **out})

@require_login
def hsn_tax_lookup(request):
    hsn = (request.GET.get('hsn') or '').strip()
    if not hsn:
        return JsonResponse({'rate': None})
    data_path = Path(settings.BASE_DIR) / 'data' / 'hsn_tax_map.json'
    if not data_path.exists():
        return JsonResponse({'rate': None})
    try:
        with open(data_path, 'r', encoding='utf-8') as f:
            mapping = json.load(f)
        entry = mapping.get(hsn) or mapping.get(hsn.zfill(4))
        if entry:
            return JsonResponse({'rate': entry.get('gst_rate')})
    except Exception:
        pass
    return JsonResponse({'rate': None})

# Taxes views (use your require_login decorator as before)

@require_login
def taxes_list(request):
    taxes = Tax.objects.order_by('name')
    return render(request, 'taxes_list.html', {'taxes': taxes})

@require_login
def taxes_add(request):
    error = None
    if request.method == 'POST':
        name = request.POST.get('name','').strip()
        computation = request.POST.get('computation','percent')
        apply_on = request.POST.get('apply_on','both')
        value = request.POST.get('value','0') or '0'
        try:
            t = Tax.objects.create(name=name, computation=computation, apply_on=apply_on, value=value)
            return redirect('taxes_list')
        except Exception as e:
            error = str(e)
    return render(request, 'taxes_add.html', {'error': error})

@require_login
def taxes_edit(request, pk):
    # Admin-only (keeps same style but robust to missing attribute)
    if getattr(request.user, 'role', '') != 'admin':
        return render(request, 'error.html', {'message': 'Only admin can edit taxes.'})

    tax = get_object_or_404(Tax, pk=pk)
    error = None
    if request.method == 'POST':
        tax.name = request.POST.get('name','').strip()
        tax.computation = request.POST.get('computation','percent')
        tax.apply_on = request.POST.get('apply_on','both')
        tax.value = request.POST.get('value','0') or '0'
        tax.active = bool(request.POST.get('active'))
        tax.save()
        return redirect('taxes_list')
    return render(request, 'taxes_edit.html', {'tax': tax, 'error': error})

@require_login
def taxes_delete(request, pk):
    # Admin-only
    if getattr(request.user, 'role', '') != 'admin':
        return render(request, 'error.html', {'message': 'Only admin can delete taxes.'})

    tax = get_object_or_404(Tax, pk=pk)
    if request.method == 'POST':
        tax.delete()
        return redirect('taxes_list')
    return render(request, 'taxes_delete.html', {'tax': tax})

# --- Accounts CRUD (similar) ---
@require_login
def accounts_list(request):
    # runtime fallback: seed defaults if none exist (handy for demo)
    if not Account.objects.exists():
        defaults = [
            ('Cash A/c', 'asset', '1000'),
            ('Bank A/c', 'asset', '1010'),
            ('Debtors A/c', 'asset', '1020'),
            ('Creditors A/c', 'liability', '2000'),
            ('Sales Income A/c', 'income', '4000'),
            ('Purchase Expense A/c', 'expense', '5000'),
            ('Other Expense A/c', 'expense', '5100'),
        ]
        for name, typ, code in defaults:
            Account.objects.get_or_create(name=name, defaults={'account_type': typ, 'code': code})

    accounts = Account.objects.order_by('account_type', 'name')
    return render(request, 'accounts_list.html', {'accounts': accounts})

@require_login
def accounts_add(request):
    error = None
    if request.method == 'POST':
        name = request.POST.get('name','').strip()
        account_type = request.POST.get('account_type','asset')
        code = request.POST.get('code','').strip()
        try:
            Account.objects.create(name=name, account_type=account_type, code=code)
            return redirect('accounts_list')
        except Exception as e:
            error = str(e)
    return render(request, 'accounts_add.html', {'error': error})

@require_login
def accounts_edit(request, pk):
    # admin-only edit
    if getattr(request.user, 'role', '') != 'admin':
        return render(request, 'error.html', {'message': 'Only admin can edit accounts.'})

    acc = get_object_or_404(Account, pk=pk)
    error = None
    if request.method == 'POST':
        acc.name = request.POST.get('name','').strip()
        acc.account_type = request.POST.get('account_type','asset')
        acc.code = request.POST.get('code','').strip()
        acc.save()
        return redirect('accounts_list')
    return render(request, 'accounts_edit.html', {'account': acc, 'error': error})

@require_login
def accounts_delete(request, pk):
    # admin-only delete (soft archive)
    if getattr(request.user, 'role', '') != 'admin':
        return render(request, 'error.html', {'message': 'Only admin can delete accounts.'})

    acc = get_object_or_404(Account, pk=pk)
    if request.method == 'POST':
        # soft-delete approach: remove by archiving (since model has no archived field, we will hard delete)
        # If you prefer soft-delete, first add archived field to model.
        acc.delete()
        return redirect('accounts_list')
    return render(request, 'accounts_delete.html', {'account': acc})

# --- Ajax to provide tax list for product form ---
def ajax_active_taxes(request):
    taxes = Tax.objects.filter(active=True).order_by('name')
    data = []
    for t in taxes:
        data.append({'id': t.id, 'name': t.name, 'computation': t.computation, 'value': str(t.value), 'apply_on': t.apply_on})
    return JsonResponse({'results': data})

@require_login
def vendor_bill_confirm_view(request, pk):
    # Only admin allowed to confirm bills
    if getattr(request.user, 'role', '') != 'admin':
        return render(request, 'error.html', {'message': 'Only admin can confirm bills.'})

    bill = get_object_or_404(VendorBill, pk=pk)
    if request.method == 'POST':
        try:
            je = bill.confirm()
            messages.success(request, f"Bill confirmed and journal posted ({je.ref}).")
            return redirect(reverse('vendor_bill_detail', args=[bill.pk]))
        except Exception as e:
            # show error to user
            messages.error(request, f"Could not confirm bill: {e}")
            return redirect(reverse('vendor_bill_detail', args=[bill.pk]))
    # GET: show confirmation page
    return render(request, 'vendor_bill_confirm.html', {'bill': bill})

@require_login
def vendor_bills_list(request):
    bills = VendorBill.objects.order_by('-created_at')
    return render(request, 'vendor_bill_list.html', {'bills': bills})

@require_login
def vendor_bill_add(request):
    contacts = Contact.objects.all()
    products = Product.objects.all()
    if request.method == 'POST':
        vendor_id = request.POST.get('vendor')
        bill = VendorBill.objects.create(
            vendor_id = int(vendor_id),
            bill_date = request.POST.get('bill_date') or timezone.now().date(),
            due_date = request.POST.get('due_date') or None,
            reference = request.POST.get('reference',''),
            created_by = str(request.user) if getattr(request,'user',None) else None
        )
        # simple lines: handle up to N lines; form fields: product_1, qty_1, unit_price_1, tax_percent_1 ...
        i = 1
        while True:
            pid = request.POST.get(f'product_{i}')
            if not pid:
                break
            qty = request.POST.get(f'qty_{i}') or 0
            unit_price = request.POST.get(f'unit_price_{i}') or 0
            tax_percent = request.POST.get(f'tax_percent_{i}') or 0
            prod = Product.objects.filter(pk=int(pid)).first()
            VendorBillLine.objects.create(
                bill=bill,
                product=prod,
                hsn = prod.hsn if prod else '',
                account = Account.objects.filter(name__icontains='Purchase Expense').first(),
                qty = qty,
                unit_price = unit_price,
                tax_percent = tax_percent
            )
            i += 1
        return redirect('vendor_bills_list')
    return render(request, 'vendor_bill_add.html', {'contacts': contacts, 'products': products})

@require_login
def vendor_bill_detail(request, pk):
    bill = get_object_or_404(VendorBill, pk=pk)
    return render(request, 'vendor_bill_detail.html', {'bill': bill})

@require_login
def vendor_bill_confirm_view(request, pk):
    # Only admin allowed to confirm bills
    if getattr(request.user, 'role', '') != 'admin':
        return render(request, 'error.html', {'message': 'Only admin can confirm bills.'})
    bill = get_object_or_404(VendorBill, pk=pk)
    if request.method == 'POST':
        try:
            je = bill.confirm()
            messages.success(request, f"Bill confirmed and journal posted ({je.ref}).")
            return redirect(reverse('vendor_bill_detail', args=[bill.pk]))
        except Exception as e:
            messages.error(request, f"Could not confirm bill: {e}")
            return redirect(reverse('vendor_bill_detail', args=[bill.pk]))
    return render(request, 'vendor_bill_confirm.html', {'bill': bill})

# @transaction.atomic
# def vendor_bill_confirm(request, pk):
#     """
#     Confirm a vendor bill and post journal entries.
#     Creates a JournalEntry linked to the bill (source content_type/object_id),
#     sets created_by/ref, and creates JournalLine rows with partner generic FK set.
#     """
#     bill = get_object_or_404(VendorBill, pk=pk)

#     # Prevent double-posting if the bill already has a journal
#     if getattr(bill, 'journal_entry', None):
#         messages.info(request, "This bill already has a journal posted.")
#         return redirect('vendor_bill_detail', pk=bill.pk)

#     # --- helper to coerce to Decimal safely ---
#     def to_decimal(value):
#         if value is None:
#             return Decimal('0.00')
#         if isinstance(value, Decimal):
#             return value
#         try:
#             return Decimal(str(value))
#         except (InvalidOperation, TypeError, ValueError):
#             return Decimal('0.00')

#     # --- compute totals: try common bill fields, else sum lines ---
#     untaxed = Decimal('0.00')
#     tax_total = Decimal('0.00')
#     total = Decimal('0.00')

#     possible_untaxed_fields = ['total_untaxed', 'amount_untaxed', 'untaxed', 'untaxed_amount', 'net_total']
#     possible_tax_fields = ['total_tax', 'tax_total', 'amount_tax', 'tax']
#     possible_total_fields = ['total', 'amount_total', 'grand_total', 'total_amount']

#     for f in possible_untaxed_fields:
#         if hasattr(bill, f):
#             untaxed = to_decimal(getattr(bill, f))
#             break
#     for f in possible_tax_fields:
#         if hasattr(bill, f):
#             tax_total = to_decimal(getattr(bill, f))
#             break
#     for f in possible_total_fields:
#         if hasattr(bill, f):
#             total = to_decimal(getattr(bill, f))
#             break

#     # If not present, sum vendor bill lines
#     if untaxed == 0 and tax_total == 0 and total == 0:
#         lines_qs = getattr(bill, 'lines', None) or getattr(bill, 'vendorbillline_set', None)
#         if lines_qs is not None:
#             lines = lines_qs.all()
#             s_untaxed = Decimal('0.00')
#             s_tax = Decimal('0.00')
#             for ln in lines:
#                 # vendor bill line: unit_price * qty = net; tax_amount present; line_total present
#                 net = to_decimal(getattr(ln, 'unit_price', 0)) * to_decimal(getattr(ln, 'qty', 0))
#                 s_untaxed += net
#                 s_tax += to_decimal(getattr(ln, 'tax_amount', 0))
#             untaxed = s_untaxed
#             tax_total = s_tax
#             total = untaxed + tax_total

#     if total == 0:
#         messages.error(request, "Bill total is zero or unknown — cannot post empty journal.")
#         return redirect('vendor_bill_detail', pk=bill.pk)

#     # --- choose accounts (robust selection) ---
#     # Prefer exact seeded names, else fallback to first by account_type
#     def get_account_by_name_or_type(names, fallback_type=None):
#         # names: list of candidate names (exact i.e. iexact)
#         for n in names:
#             try:
#                 return Account.objects.get(name__iexact=n)
#             except Account.DoesNotExist:
#                 continue
#         if fallback_type:
#             return Account.objects.filter(account_type=fallback_type).first()
#         return None

#     purchase_account = get_account_by_name_or_type(['Purchase Expense A/c', 'Purchase Expense', 'Purchase'], fallback_type='expense')
#     creditor_account = get_account_by_name_or_type(['Creditors A/c', 'Creditors', 'Creditor'], fallback_type='liability')
#     tax_account = Account.objects.filter(name__icontains='tax').first() or Account.objects.filter(name__icontains='gst').first()

#     if not purchase_account or not creditor_account:
#         messages.error(request, "Configure Expense and Liability accounts before confirming bills.")
#         return redirect('vendor_bill_detail', pk=bill.pk)

#     # if tax exists but no tax account, we will add tax to purchase side (so overall JE balanced)
#     if tax_total > 0 and not tax_account:
#         tax_account = None

#     # --- create JournalEntry with content_type/object_id (link back to bill) ---
#     bill_ct = ContentType.objects.get_for_model(bill.__class__)
#     created_by = getattr(request.user, 'username', None) if request and hasattr(request, 'user') else None

#     je = JournalEntry.objects.create(
#         date = getattr(bill, 'bill_date', getattr(bill, 'date', timezone.now().date())),
#         narration = f"Bill {bill.pk} - {getattr(bill, 'vendor', '')}",
#         ref = f"Bill/{bill.pk}",
#         content_type = bill_ct,
#         object_id = bill.pk,
#         created_by = created_by
#     )

#     # helper to create a JournalLine and set partner generic FK properly
#     def create_line(account, debit_amt=Decimal('0.00'), credit_amt=Decimal('0.00'), narration='', partner_obj=None):
#         debit_amt = to_decimal(debit_amt)
#         credit_amt = to_decimal(credit_amt)
#         if debit_amt == 0 and credit_amt == 0:
#             return None

#         jl_kwargs = dict(
#             entry = je,
#             account = account,
#             debit = debit_amt,
#             credit = credit_amt,
#             narration = narration,
#             date = je.date,
#         )

#         # if partner_obj supplied, set partner_content_type & partner_object_id explicitly
#         if partner_obj is not None:
#             p_ct = ContentType.objects.get_for_model(partner_obj.__class__)
#             jl_kwargs['partner_content_type'] = p_ct
#             jl_kwargs['partner_object_id'] = getattr(partner_obj, 'pk', None)

#         return JournalLine.objects.create(**jl_kwargs)

#     # Build lines:
#     # Debit purchase expense (untaxed)
#     if untaxed > 0:
#         create_line(purchase_account, debit_amt=untaxed, narration="Purchase (untaxed)", partner_obj=bill.vendor)

#     # Debit tax account (if separate) or add tax to purchase expense
#     if tax_total > 0:
#         if tax_account:
#             create_line(tax_account, debit_amt=tax_total, narration="Tax", partner_obj=bill.vendor)
#         else:
#             # Add tax into purchase account so row exists and totals balance
#             create_line(purchase_account, debit_amt=tax_total, narration="Tax (added to purchase account)", partner_obj=bill.vendor)

#     # Credit creditor (vendor) total
#     create_line(creditor_account, credit_amt=total, narration=f"Creditor: {getattr(bill, 'vendor', '')}", partner_obj=bill.vendor)

#     # ensure journal is balanced? (sanity check)
#     total_debits = sum([to_decimal(l.debit) for l in je.lines.all()])
#     total_credits = sum([to_decimal(l.credit) for l in je.lines.all()])
#     if total_debits != total_credits:
#         # rollback by raising an exception - transaction.atomic will rollback
#         raise ValueError(f"Unbalanced journal created (debits {total_debits} != credits {total_credits}). Aborting.")

#     # Link the journal entry back to bill and set status
#     bill.journal_entry = je
#     # Your VendorBill uses 'status' field in model (not 'state')
#     if hasattr(bill, 'status'):
#         bill.status = VendorBill.CONFIRMED if hasattr(VendorBill, 'CONFIRMED') else 'confirmed'
#     bill.save(update_fields=['journal_entry', 'status'] if hasattr(bill, 'status') else ['journal_entry'])

#     messages.success(request, f"Vendor bill confirmed and journal entry #{je.id} created.")
#     return redirect('vendor_bill_detail', pk=bill.pk)

@transaction.atomic
def vendor_bill_confirm(request, pk):
    """
    Confirm a vendor bill and post journal entries.
    Ensures JE.created_by is set from request (or fallback) and sets bill.status='confirmed'.
    """
    bill = get_object_or_404(VendorBill, pk=pk)

    # Prevent double-posting
    if getattr(bill, 'journal_entry', None):
        messages.info(request, "This bill already has a journal posted.")
        return redirect('vendor_bill_detail', pk=bill.pk)

    # helper: safe Decimal conversion
    def to_decimal(v):
        if v is None:
            return Decimal('0.00')
        if isinstance(v, Decimal):
            return v
        try:
            return Decimal(str(v))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal('0.00')

    # Compute totals: try common fields, else sum lines
    untaxed = Decimal('0.00')
    tax_total = Decimal('0.00')
    total = Decimal('0.00')

    possible_untaxed_fields = ['total_untaxed', 'amount_untaxed', 'untaxed', 'untaxed_amount', 'net_total']
    possible_tax_fields = ['total_tax', 'tax_total', 'amount_tax', 'tax']
    possible_total_fields = ['total', 'amount_total', 'grand_total', 'total_amount', 'line_total']

    for f in possible_untaxed_fields:
        if hasattr(bill, f):
            untaxed = to_decimal(getattr(bill, f))
            break
    for f in possible_tax_fields:
        if hasattr(bill, f):
            tax_total = to_decimal(getattr(bill, f))
            break
    for f in possible_total_fields:
        if hasattr(bill, f):
            total = to_decimal(getattr(bill, f))
            break

    if untaxed == 0 and tax_total == 0 and total == 0:
        lines_qs = getattr(bill, 'lines', None) or getattr(bill, 'vendorbillline_set', None)
        if lines_qs is not None:
            s_untaxed = Decimal('0.00')
            s_tax = Decimal('0.00')
            for ln in lines_qs.all():
                net = to_decimal(getattr(ln, 'unit_price', 0)) * to_decimal(getattr(ln, 'qty', 0))
                s_untaxed += net
                s_tax += to_decimal(getattr(ln, 'tax_amount', 0))
            untaxed = s_untaxed
            tax_total = s_tax
            total = untaxed + tax_total

    if total == 0:
        messages.error(request, "Bill total is zero or unknown — cannot post empty journal.")
        return redirect('vendor_bill_detail', pk=bill.pk)

    # Robust account selection
    def get_by_name_or_type(names, fallback_type=None):
        for n in names:
            try:
                return Account.objects.get(name__iexact=n)
            except Account.DoesNotExist:
                continue
        if fallback_type:
            return Account.objects.filter(account_type=fallback_type).first()
        return None

    purchase_account = get_by_name_or_type(['Purchase Expense A/c', 'Purchase Expense', 'Purchase'], fallback_type='expense')
    creditor_account = get_by_name_or_type(['Creditors A/c', 'Creditors', 'Creditor'], fallback_type='liability')
    tax_account = Account.objects.filter(name__icontains='tax').first() or Account.objects.filter(name__icontains='gst').first()

    if not purchase_account or not creditor_account:
        messages.error(request, "Configure Expense and Liability accounts before confirming bills.")
        return redirect('vendor_bill_detail', pk=bill.pk)

    # Who created this JE? prefer request user username; else bill.created_by or 'system'
    created_by = None
    try:
        user = getattr(request, 'user', None)
        if user and getattr(user, 'is_authenticated', False):
            created_by = getattr(user, 'username', None) or str(user)
    except Exception:
        created_by = None

    if not created_by:
        created_by = getattr(bill, 'created_by', None) or 'system'

    # Create JE and link to bill (content type)
    bill_ct = ContentType.objects.get_for_model(bill.__class__)
    je = JournalEntry.objects.create(
        date=getattr(bill, 'bill_date', getattr(bill, 'date', timezone.now().date())),
        narration=f"Bill {bill.pk} - {getattr(bill, 'vendor', '')}",
        ref=f"Bill/{bill.pk}",
        content_type=bill_ct,
        object_id=bill.pk,
        created_by=created_by,
    )

    # helper to write journal lines (also sets partner_content_type/object_id if partner provided)
    def make_line(account, debit_amt=Decimal('0.00'), credit_amt=Decimal('0.00'), narration='', partner_obj=None):
        debit_amt = to_decimal(debit_amt)
        credit_amt = to_decimal(credit_amt)
        if debit_amt == 0 and credit_amt == 0:
            return None
        kwargs = dict(
            entry=je,
            account=account,
            debit=debit_amt,
            credit=credit_amt,
            narration=narration,
            date=je.date,
        )
        if partner_obj is not None:
            p_ct = ContentType.objects.get_for_model(partner_obj.__class__)
            kwargs['partner_content_type'] = p_ct
            kwargs['partner_object_id'] = getattr(partner_obj, 'pk', None)
        return JournalLine.objects.create(**kwargs)

    # Create lines: debit purchase, debit tax (if separate or add to purchase), credit creditors
    if untaxed > 0:
        make_line(purchase_account, debit_amt=untaxed, narration="Purchase (untaxed)", partner_obj=bill.vendor)

    if tax_total > 0:
        if tax_account:
            make_line(tax_account, debit_amt=tax_total, narration="Tax", partner_obj=bill.vendor)
        else:
            # add to purchase if no tax account
            make_line(purchase_account, debit_amt=tax_total, narration="Tax (added to purchase account)", partner_obj=bill.vendor)

    make_line(creditor_account, credit_amt=total, narration=f"Creditor: {getattr(bill, 'vendor', '')}", partner_obj=bill.vendor)

    # sanity check: balanced JE
    total_debits = sum([to_decimal(l.debit) for l in je.lines.all()])
    total_credits = sum([to_decimal(l.credit) for l in je.lines.all()])
    if total_debits != total_credits:
        # rollback
        raise ValueError(f"Unbalanced journal (debits {total_debits} != credits {total_credits}).")

    # Link JE to bill and mark confirmed (use your model's STATUS constant if present)
    bill.journal_entry = je
    if hasattr(bill, 'status'):
        # prefer using the model constant if defined (e.g., VendorBill.CONFIRMED)
        confirmed_val = getattr(VendorBill, 'CONFIRMED', 'confirmed')
        bill.status = confirmed_val
        bill.save(update_fields=['journal_entry', 'status'])
    else:
        bill.save(update_fields=['journal_entry'])

    messages.success(request, f"Vendor bill confirmed and journal entry #{je.id} created by {created_by}.")
    return redirect('vendor_bill_detail', pk=bill.pk)

@require_login
def payment_add(request, bill_pk):
    bill = get_object_or_404(VendorBill, pk=bill_pk)
    # only invoicing users and admin allowed to record payments
    if getattr(request.user, 'role','') not in ('admin','invoicing'):
        return render(request, 'error.html', {'message': 'Not allowed to record payments.'})

    # populate available cash/bank accounts: assets with cash/bank names or account_type asset
    accounts = Account.objects.filter(account_type='asset').order_by('name')
    if request.method == 'POST':
        amount = request.POST.get('amount') or 0
        account_id = request.POST.get('account')
        method = request.POST.get('method') or 'bank'
        reference = request.POST.get('reference','')
        p = Payment.objects.create(
            bill = bill,
            date = request.POST.get('date') or timezone.now().date(),
            amount = amount,
            account_id = int(account_id),
            method = method,
            reference = reference,
            created_by = str(request.user)
        )
        try:
            je = p.post()
            messages.success(request, f"Payment recorded and journal posted ({je.ref}).")
            return redirect(reverse('vendor_bill_detail', args=[bill.pk]))
        except Exception as e:
            messages.error(request, f"Could not post payment: {e}")
            # keep payment record? we created it; could delete it on failure. Simpler: delete
            p.delete()
            return redirect(reverse('payment_add', args=[bill.pk]))

    # compute outstanding
    total = sum([l.line_total for l in bill.lines.all()])
    paid = sum([pmt.amount for pmt in bill.payments.all()])
    outstanding = total - paid
    return render(request, 'payment_add.html', {'bill': bill, 'accounts': accounts, 'outstanding': outstanding})

@require_login
def purchase_orders_list(request):
    pos = PurchaseOrder.objects.order_by('-created_at')
    return render(request, 'purchase_orders_list.html', {'pos': pos})

def purchase_order_add(request):
    # Show product & contacts for the form
    products = Product.objects.order_by('name')
    contacts = Contact.objects.filter(contact_type__in=['vendor','both']).order_by('name')

    if request.method == 'POST':
        # Read header fields
        vendor_id = request.POST.get('vendor') or None
        po_date_raw = request.POST.get('po_date') or ''
        reference_from_form = (request.POST.get('reference') or '').strip() or None

        parsed_date = parse_date_safe(po_date_raw) or timezone.now().date()

        po = PurchaseOrder.objects.create(
            vendor_id = int(vendor_id),
                    po_date = parsed_date,            # ✅ now guaranteed a date object
                    reference_id = reference_from_form
                )

        # create up to N lines (we used 5 in template)
        lines_created = 0
        for i in range(1, 6):
            pid = request.POST.get(f'product_{i}')
            if not pid:
                continue
            try:
                product_obj = Product.objects.get(pk=int(pid))
            except Product.DoesNotExist:
                continue

            # read posted numbers safely
            qty_raw = request.POST.get(f'qty_{i}') or '0'
            unit_price_raw = request.POST.get(f'unit_price_{i}') or '0'
            tax_percent_raw = request.POST.get(f'tax_percent_{i}') or '0'

            try:
                qty = Decimal(qty_raw)
            except Exception:
                qty = Decimal('0.00')
            try:
                unit_price = Decimal(unit_price_raw)
            except Exception:
                unit_price = Decimal('0.00')
            try:
                tax_percent = Decimal(tax_percent_raw)
            except Exception:
                tax_percent = Decimal('0.00')

            # create PO line
            PurchaseOrderLine.objects.create(
                order = po,
                product = product_obj,
                hsn = getattr(product_obj, 'hsn', '') or '',
                qty = qty,
                unit_price = unit_price,
                tax_percent = tax_percent
            )
            lines_created += 1

        # Now recompute totals and save on PO
        po.recompute_totals()

        messages.success(request, f"Purchase Order {po.po_number} created ({lines_created} lines).")
        return redirect('purchase_order_detail', pk=po.pk)

    # GET -> render blank form
    ctx = {
        'products': products,
        'contacts': contacts,
        'today': timezone.now().date().isoformat()
    }
    return render(request, 'purchase_order_add.html', ctx)

@require_login
def purchase_order_detail(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    return render(request, 'purchase_order_detail.html', {'po': po})

@require_login
def purchase_order_convert_to_bill(request, pk):
    """
    Convert PO into VendorBill (copy lines). User lands on created bill detail.
    """
    po = get_object_or_404(PurchaseOrder, pk=pk)
    # create VendorBill
    vb = VendorBill.objects.create(
        vendor = po.vendor,
        bill_date = po.po_date or timezone.now().date(),
        reference = po.reference_id,
        created_by = po.created_by
    )
    # copy lines
    for L in po.lines.all():
        VendorBillLine.objects.create(
            bill = vb,
            product = L.product,
            hsn = L.hsn,
            account = Account.objects.filter(name__icontains='Purchase Expense').first(),
            qty = L.qty,
            unit_price = L.unit_price,
            tax_percent = L.tax_percent
        )
    # optionally mark PO as sent
    po.state = PurchaseOrder.SENT
    po.save(update_fields=['state'])
    messages.success(request, f"Converted PO {po.pk} → Bill {vb.pk}")
    return redirect(reverse('vendor_bill_detail', args=[vb.pk]))

def product_info(request, pk):
    p = Product.objects.filter(pk=pk).first()
    if not p:
        return JsonResponse({'error':'Not found'}, status=404)
    return JsonResponse({
        'id': p.id,
        'name': p.name,
        'unit_price': float(p.purchase_price or 0),
        'tax_percent': float(p.purchase_tax.value if p.purchase_tax else 0),
        'hsn': p.hsn or ''
    })

def partner_ledger(request, partner_id):
    from django.contrib.contenttypes.models import ContentType
    partner = get_object_or_404(Contact, pk=partner_id)
    ct = ContentType.objects.get_for_model(Contact)
    lines = (JournalLine.objects
             .filter(partner_content_type=ct, partner_object_id=partner.pk)
             .select_related('entry', 'account')
             .order_by('entry__date', 'entry_id'))
    balance = Decimal('0.00')
    rows = []
    for l in lines:
        balance += l.debit - l.credit
        rows.append({
            'date': l.date,
            'ref': l.entry.ref,
            'account': l.account.name,
            'debit': l.debit,
            'credit': l.credit,
            'balance': balance,
        })
    return render(request, 'reports/partner_ledger.html', {'partner': partner, 'rows': rows})

from django.db.models import Sum

# def profit_and_loss(request):
#     start, end = ... # from request GET or default month
#     expenses = (JournalLine.objects
#                 .filter(account__account_type='expense',
#                         entry__date__range=(start, end))
#                 .values('account__name')
#                 .annotate(total=Sum('debit')))
#     income = (JournalLine.objects
#               .filter(account__account_type='income',
#                       entry__date__range=(start, end))
#               .values('account__name')
#               .annotate(total=Sum('credit')))
#     total_exp = sum(e['total'] or 0 for e in expenses)
#     total_inc = sum(i['total'] or 0 for i in income)
#     net = total_inc - total_exp
#     return render(request, 'reports/pnl.html', {
#         'expenses': expenses, 'income': income,
#         'total_exp': total_exp, 'total_inc': total_inc,
#         'net': net
#     })

from decimal import Decimal
from django.db.models import Sum
from django.shortcuts import render
from .models import Account, JournalLine

def balance_sheet(request):
    """
    Compute balances and present them so:
      - Assets: debit - credit (positive shown)
      - Liabilities/Equity: show (credit - debit) as positive amounts
    Also compute Net Profit (Income - Expenses) and include under Equity.
    """
    rows = []
    accounts = Account.objects.all().order_by('account_type', 'name')

    total_assets = Decimal('0.00')
    total_liabilities = Decimal('0.00')
    total_equity = Decimal('0.00')

    assets = []
    liabilities = []
    equity = []

    for acc in accounts:
        sums = JournalLine.objects.filter(account=acc).aggregate(debits=Sum('debit'), credits=Sum('credit'))
        deb = sums.get('debits') or Decimal('0.00')
        cred = sums.get('credits') or Decimal('0.00')

        raw_balance = deb - cred
        acc_type = (acc.account_type or '').strip().lower()

        if acc_type == 'asset':
            display_amount = raw_balance  # debit-positive
            assets.append({'account': acc, 'amount': display_amount})
            total_assets += display_amount

        elif acc_type == 'liability':
            display_amount = (cred - deb)  # credit-positive
            liabilities.append({'account': acc, 'amount': display_amount})
            total_liabilities += display_amount

        elif acc_type == 'equity':
            display_amount = (cred - deb)  # credit-positive
            equity.append({'account': acc, 'amount': display_amount})
            total_equity += display_amount

    # 🚫 Skip expense and income accounts here
        elif acc_type in ['expense', 'income']:
            continue
        else:
            # treat unknown types as asset by default (or skip)
            display_amount = raw_balance
            assets.append({'account': acc, 'amount': display_amount})
            total_assets += display_amount

    # compute net profit (income - expenses) and include under equity
    expenses_total = JournalLine.objects.filter(account__account_type__iexact='expense').aggregate(total=Sum('debit'))['total'] or Decimal('0.00')
    income_total = JournalLine.objects.filter(account__account_type__iexact='income').aggregate(total=Sum('credit'))['total'] or Decimal('0.00')
    net_profit = (income_total or Decimal('0.00')) - (expenses_total or Decimal('0.00'))

    # For presentation, equity side should show net profit as credit-positive:
    # if net_profit positive -> add as credit amount; if negative (loss) -> shows negative number (reduces equity).
    equity.append({'account': type('X', (), {'name': 'Net Profit (P&L)'}), 'amount': net_profit})
    total_equity += net_profit

    total_liabilities_equity = (total_liabilities or Decimal('0.00')) + (total_equity or Decimal('0.00'))

    ctx = {
        'assets': assets,
        'liabilities': liabilities,
        'equity': equity,
        'total_assets': total_assets,
        'total_liabilities_equity': total_liabilities_equity,
        'total_liabilities': total_liabilities,
        'total_equity': total_equity,
        'net_profit': net_profit,
    }
    return render(request, 'reports/balance_sheet.html', ctx)
