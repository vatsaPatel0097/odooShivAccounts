from django.contrib import admin
from .models import *
# Register your models here.
admin.site.register(User)
admin.site.register(Contact)
admin.site.register(Product)
admin.site.register(Tax)
admin.site.register(Account)

class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0
    readonly_fields = ('account','debit','credit','partner','narration','date')

@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ('ref','date','narration')
    inlines = [JournalLineInline]
    readonly_fields = ('created_at','date','ref','narration')

admin.site.register(PurchaseOrder)
admin.site.register(PurchaseOrderLine)
admin.site.register(VendorBill)
admin.site.register(VendorBillLine)
admin.site.register(Payment)
