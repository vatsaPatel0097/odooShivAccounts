from django.contrib import admin
from .models import User, Contact, Product, Tax, Account
# Register your models here.
admin.site.register(User)
admin.site.register(Contact)
admin.site.register(Product)
admin.site.register(Tax)
admin.site.register(Account)
