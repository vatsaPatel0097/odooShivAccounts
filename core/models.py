from django.db import models
from django.utils import timezone

class User(models.Model):
    ROLE_CHOICES = (('admin','Admin'),('invoicing','Invoicing User'))
    username = models.CharField(max_length=150, unique=True)
    full_name = models.CharField(max_length=200, blank=True)
    password = models.CharField(max_length=128)   # hashed
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='invoicing')
    created_at = models.DateTimeField(default=timezone.now)

class Contact(models.Model):
    CONTACT_TYPES = [
        ('customer', 'Customer'),
        ('vendor', 'Vendor'),
        ('both', 'Both'),
    ]

    name = models.CharField(max_length=100)
    contact_type = models.CharField(max_length=10, choices=CONTACT_TYPES)
    email = models.EmailField(blank=True, null=True)
    mobile = models.CharField(max_length=20, blank=True, null=True)
    city = models.CharField(max_length=50, blank=True, null=True)
    state = models.CharField(max_length=50, blank=True, null=True)
    pincode = models.CharField(max_length=10, blank=True, null=True)
    profile_image = models.ImageField(upload_to='contacts/', blank=True, null=True)  # 👈 added field

    def __str__(self):
        return self.name

class Tax(models.Model):
    COMPUTE_PERCENT = 'percent'
    COMPUTE_FIXED = 'fixed'
    COMPUTE_CHOICES = [
        (COMPUTE_PERCENT, 'Percentage'),
        (COMPUTE_FIXED, 'Fixed value'),
    ]

    APPLY_SALES = 'sales'
    APPLY_PURCHASE = 'purchase'
    APPLY_BOTH = 'both'
    APPLY_CHOICES = [
        (APPLY_SALES, 'Sales'),
        (APPLY_PURCHASE, 'Purchase'),
        (APPLY_BOTH, 'Both'),
    ]

    name = models.CharField(max_length=120, unique=True)
    computation = models.CharField(max_length=20, choices=COMPUTE_CHOICES, default=COMPUTE_PERCENT)
    apply_on = models.CharField(max_length=20, choices=APPLY_CHOICES, default=APPLY_BOTH)
    value = models.DecimalField(max_digits=7, decimal_places=2, help_text='Percent (eg 5.00) or fixed value')
    active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.value}{'%' if self.computation==self.COMPUTE_PERCENT else ''})"


class Account(models.Model):
    TYPE_ASSET = 'asset'
    TYPE_LIABILITY = 'liability'
    TYPE_INCOME = 'income'
    TYPE_EXPENSE = 'expense'
    TYPE_EQUITY = 'equity'
    TYPE_CHOICES = [
        (TYPE_ASSET, 'Asset'),
        (TYPE_LIABILITY, 'Liability'),
        (TYPE_INCOME, 'Income'),
        (TYPE_EXPENSE, 'Expense'),
        (TYPE_EQUITY, 'Equity'),
    ]

    name = models.CharField(max_length=120, unique=True)
    account_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    code = models.CharField(max_length=32, blank=True, null=True)

    def __str__(self):
        return f"{self.name} [{self.get_account_type_display()}]"

class Product(models.Model):
    name = models.CharField(max_length=255)
    product_type = models.CharField(max_length=32, choices=[('goods','Goods'),('service','Service')], default='goods')
    sales_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    sale_tax = models.ForeignKey(Tax, null=True, blank=True, related_name='products_for_sale', on_delete=models.SET_NULL)
    purchase_tax = models.ForeignKey(Tax, null=True, blank=True, related_name='products_for_purchase', on_delete=models.SET_NULL)
    hsn = models.CharField(max_length=32, blank=True, null=True)
    category = models.CharField(max_length=100, blank=True, null=True)
    image = models.ImageField(upload_to='products/', null=True, blank=True)
    created_by = models.CharField(max_length=120, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    # <-- ADD THIS LINE:
    archived = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    def sale_tax_value(self):
        """Return numeric tax value or None"""
        if not self.sale_tax: return None
        return float(self.sale_tax.value)

    def purchase_tax_value(self):
        if not self.purchase_tax: return None
        return float(self.purchase_tax.value)


# class Account(models.Model):
#     ACCOUNT_TYPES = [
#         ('asset', 'Asset'),
#         ('liability', 'Liability'),
#         ('income', 'Income'),
#         ('expense', 'Expense'),
#         ('equity', 'Equity'),
#     ]

#     name = models.CharField(max_length=150, unique=True)
#     account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
#     code = models.CharField(max_length=20, blank=True, null=True)   # optional numeric code
#     archived = models.BooleanField(default=False)
#     created_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return f"{self.name} ({self.get_account_type_display()})"
