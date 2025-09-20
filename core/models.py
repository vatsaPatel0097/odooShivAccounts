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

class Product(models.Model):
    PRODUCT_TYPE = [
        ('goods', 'Goods'),
        ('service', 'Service'),
    ]

    name = models.CharField(max_length=200)
    product_type = models.CharField(max_length=10, choices=PRODUCT_TYPE, default='goods')
    category = models.CharField(max_length=100, blank=True, null=True)

    # Prices & taxes (master defaults)
    sales_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sale_tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    purchase_tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    hsn = models.CharField(max_length=50, blank=True, null=True)
    image = models.ImageField(upload_to='products/', blank=True, null=True)

    created_by = models.ForeignKey('User', null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    archived = models.BooleanField(default=False)

    def __str__(self):
        return self.name