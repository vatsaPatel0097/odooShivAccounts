from django.shortcuts import render, redirect , get_object_or_404
from .models import User, Contact, Product , Tax, Account
from .utils import hash_pw, verify_pw, validate_password_complexity
from django.utils import timezone
import json
from pathlib import Path
from django.conf import settings
from django.http import JsonResponse
import requests
import traceback
from django.core.cache import cache


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

