from django.db import models,transaction 
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from decimal import Decimal
from datetime import date,datetime
import uuid
from django.http import JsonResponse

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

class JournalEntry(models.Model):
    """
    A header for a group of journal lines representing a single accounting event.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    date = models.DateField(db_index=True)
    ref = models.CharField(max_length=200, blank=True, null=True)  # e.g. "Bill/2025/0001"
    narration = models.TextField(blank=True, null=True)

    # optional generic link back to source object (bill, payment, invoice)
    content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    source = GenericForeignKey('content_type', 'object_id')
    created_by = models.CharField(max_length=200, blank=True, null=True)


    class Meta:
        ordering = ['-date', '-id']

    def __str__(self):
        return f"{self.ref or 'JE'} @ {self.date} - {self.narration or ''}"


class JournalLine(models.Model):
    """
    Individual debit/credit line. Sum of debits must equal sum of credits per JournalEntry.
    partner is optional (useful for partner ledger).
    """
    entry = models.ForeignKey(JournalEntry, related_name='lines', on_delete=models.CASCADE)
    account = models.ForeignKey('core.Account', on_delete=models.PROTECT)  # adjust app label if needed
    partner_content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    partner_object_id = models.PositiveIntegerField(null=True, blank=True)
    partner = GenericForeignKey('partner_content_type', 'partner_object_id')

    debit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    narration = models.CharField(max_length=255, blank=True, null=True)
    # optional fields
    date = models.DateField(db_index=True)

    class Meta:
        ordering = ['entry__date', 'entry_id']

    def __str__(self):
        side = 'Dr' if self.debit and self.debit > 0 else 'Cr'
        amt = self.debit if self.debit else self.credit
        return f"{self.account} {side} {amt}"


class VendorBill(models.Model):
    DRAFT = 'draft'
    CONFIRMED = 'confirmed'
    CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
    ]

    vendor = models.ForeignKey('core.Contact', on_delete=models.PROTECT)  # your Contact model
    bill_date = models.DateField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    reference = models.CharField(max_length=200, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    # link to journal entry created when confirming
    journal_entry = models.ForeignKey(
        'JournalEntry',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='vendor_bills'
    )

    created_by = models.CharField(max_length=200, blank=True, null=True)  # or FK to user if you have custom user
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Bill/{self.pk} - {self.vendor}"

    @transaction.atomic
    def confirm(self):
        """
        Confirm the bill and post accounting entries.
        This method:
          - calculates net & tax totals from lines
          - finds seeded accounts (Purchase Expense, Tax Input, Creditors)
          - posts a balanced journal entry via post_journal_entry()
          - sets state to CONFIRMED and stores journal_entry
        Raises exceptions if already confirmed or something unbalanced.
        """
        if self.status == self.CONFIRMED:
            raise ValueError("Bill already confirmed")

        # compute totals
        net_total = Decimal('0.00')
        tax_total = Decimal('0.00')
        for L in self.lines.all():
            net_amt = (Decimal(L.unit_price or 0) * Decimal(L.qty or 0))
            net_total += net_amt
            tax_total += Decimal(L.tax_amount or 0)

        total = net_total + tax_total

        # locate accounts (prefer by code/name deterministic)
        from .models import Account  # local import to avoid circulars
        # Prefer fetching by code if you seeded; else fallback to contains
        try:
            purchase_exp = Account.objects.get(name__iexact='Purchase Expense A/c')
        except Account.DoesNotExist:
            purchase_exp = Account.objects.filter(account_type='expense').first()

        # optional tax input account
        tax_input_acc = Account.objects.filter(name__icontains='Tax').first()

        try:
            creditors_acc = Account.objects.get(name__iexact='Creditors A/c')
        except Account.DoesNotExist:
            # fallback: liability account
            creditors_acc = Account.objects.filter(account_type='liability').first()

        # Build journal lines: debit purchases, debit tax (if separate), credit creditors
        lines = []
        # debit purchase expense for net_total
        if net_total > 0:
            lines.append({
                'account': purchase_exp,
                'debit': net_total,
                'credit': 0,
                'narration': f'Purchase (bill {self.pk})',
                'partner': self.vendor
            })

        # debit tax input if available
        if tax_total and tax_total != Decimal('0.00'):
            if tax_input_acc:
                lines.append({
                    'account': tax_input_acc,
                    'debit': tax_total,
                    'credit': 0,
                    'narration': f'Input tax (bill {self.pk})',
                    'partner': self.vendor
                })
            else:
                # If no tax account, add tax into purchase expense (so totals still balance)
                lines[0]['debit'] = lines[0]['debit'] + tax_total

        # credit creditors
        lines.append({
            'account': creditors_acc,
            'debit': 0,
            'credit': total,
            'narration': f'Payable to {self.vendor}',
            'partner': self.vendor
        })

        # post journal entry using helper
        from .utils import post_journal_entry, JournalError
        je = post_journal_entry(
            date=self.bill_date or timezone.now().date(),
            ref=f"Bill/{self.pk}",
            narration=f"Vendor bill {self.pk} for {self.vendor}",
            lines=lines,
            source=self
        )


        # save JE on bill and mark confirmed
        self.journal_entry = je
        self.status = self.CONFIRMED
        self.save(update_fields=['journal_entry', 'state'])

        return je


class VendorBillLine(models.Model):
    bill = models.ForeignKey(VendorBill, related_name='lines', on_delete=models.CASCADE)
    product = models.ForeignKey('core.Product', null=True, blank=True, on_delete=models.PROTECT)
    hsn = models.CharField(max_length=32, blank=True, null=True)
    account = models.ForeignKey('core.Account', null=True, blank=True, on_delete=models.PROTECT)
    qty = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    tax_percent = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        # compute tax_amount and line_total automatically before save (simple percent tax)
        net = (Decimal(self.unit_price or 0) * Decimal(self.qty or 0))
        tax_amt = Decimal('0.00')
        try:
            tax_amt = (net * (Decimal(self.tax_percent or 0) / Decimal('100.00')))
        except Exception:
            tax_amt = Decimal('0.00')
        self.tax_amount = tax_amt.quantize(Decimal('0.01'))
        self.line_total = (net + self.tax_amount).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product} x{self.qty} @ {self.unit_price}"

class Payment(models.Model):
    PAYMENT_METHODS = [('cash','Cash'), ('bank','Bank'), ('cheque','Cheque'), ('other','Other')]

    bill = models.ForeignKey('core.VendorBill', related_name='payments', on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    account = models.ForeignKey('core.Account', on_delete=models.PROTECT)  # Cash/Bank account used
    method = models.CharField(max_length=32, choices=PAYMENT_METHODS, default='bank')
    reference = models.CharField(max_length=200, blank=True, null=True)  # cheque no / txn ref
    created_by = models.CharField(max_length=200, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    journal_entry = models.ForeignKey('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f"Payment/{self.pk} - {self.amount} for Bill {self.bill_id}"

    @transaction.atomic
    def post(self):
        """
        Post the payment as a JournalEntry:
          Debit: Creditor (liability)  = amount  (reduces creditor)
          Credit: Bank/Cash (asset) = amount  (reduces asset)
        Also marks bill paid/part-paid.
        """
        if self.journal_entry:
            raise ValueError("Payment already posted")

        # compute outstanding on bill
        bill = self.bill
        # total bill amount
        total_bill = Decimal('0.00')
        for L in bill.lines.all():
            total_bill += Decimal(L.line_total or 0)
        # total payments already done
        paid_already = Decimal('0.00')
        for p in bill.payments.exclude(pk=self.pk):
            paid_already += Decimal(p.amount or 0)

        outstanding = total_bill - paid_already
        if Decimal(self.amount) > outstanding:
            # allow overpayment? For now block
            raise ValueError("Payment exceeds outstanding amount")

        # find creditors account (liability) and the cash/bank account is self.account
        from .models import Account
        try:
            creditors_acc = Account.objects.get(name__iexact='Creditors A/c')
        except Account.DoesNotExist:
            creditors_acc = Account.objects.filter(account_type='liability').first()

        # Build lines: debit creditors (reduce liability), credit bank/cash (reduce asset)
        lines = [
            {'account': creditors_acc, 'debit': Decimal(self.amount), 'credit': 0, 'narration': f'Payment for Bill/{bill.pk}', 'partner': bill.vendor},
            {'account': self.account, 'debit': 0, 'credit': Decimal(self.amount), 'narration': f'Paid via {self.method} ref:{self.reference or ""}', 'partner': bill.vendor},
        ]

        from .utils import post_journal_entry
        je = post_journal_entry(date=self.date, ref=f"Payment/{self.pk}", narration=f"Payment {self.pk} for Bill/{bill.pk}", lines=lines, source=self)
        self.journal_entry = je
        self.save(update_fields=['journal_entry'])

        # update bill state
        new_paid = paid_already + Decimal(self.amount)
        if new_paid >= total_bill:
            bill.state = bill.CONFIRMED if bill.state != bill.CONFIRMED else bill.state
            # we may want a separate 'paid' state; update if you added it
            # If you defined 'paid' state on VendorBill change accordingly:
            if hasattr(bill, 'PAID'):
                bill.state = bill.PAID
        bill.save(update_fields=['state'])
        return je


class PurchaseOrder(models.Model):
    DRAFT = 'draft'
    SENT = 'sent'
    CANCELLED = 'cancelled'
    STATE_CHOICES = [(DRAFT,'Draft'), (SENT,'Sent'), (CANCELLED,'Cancelled')]

    vendor = models.ForeignKey('core.Contact', on_delete=models.PROTECT)
    po_date = models.DateField(default=timezone.now)

    # generated values
    po_number = models.CharField(max_length=40, unique=True, blank=True, null=True)
    reference_id = models.CharField(max_length=60, unique=True, blank=True, null=True)

    state = models.CharField(max_length=20, choices=STATE_CHOICES, default=DRAFT)

    untaxed_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    tax_total     = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    grand_total   = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

    created_by = models.CharField(max_length=200, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.po_number or 'PO/'+str(self.pk)} - {self.vendor}"

    def _safe_po_date(self):
        """
        Return a date object for self.po_date. If it's already a date, return it.
        If it's a string, try to parse common formats, otherwise return today.
        """
        pd = getattr(self, 'po_date', None)
        if isinstance(pd, date):
            return pd
        if isinstance(pd, str):
            # try iso YYYY-MM-DD
            try:
                return date.fromisoformat(pd)
            except Exception:
                pass
        # try common other formats
        for fmt in ("%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(pd, fmt).date()
            except Exception:
                pass
        # fallback
        return timezone.now().date()

    def _generate_po_number(self):
        """
        Generate PO/2025/0001 style number. Uses a safe date conversion.
        """
        year = self._safe_po_date().year
        last = PurchaseOrder.objects.filter(created_at__year=year).order_by('id').last()
        if last and last.po_number:
            try:
                last_seq = int(last.po_number.split('/')[-1])
            except Exception:
                last_seq = last.id or 0
            seq = last_seq + 1
        else:
            seq = 1
        return f"PO/{year}/{str(seq).zfill(4)}"

    def _generate_reference(self):
        pd_safe = self._safe_po_date()
        date_str = pd_safe.strftime("%Y%m%d")
        last = PurchaseOrder.objects.filter(created_at__date=pd_safe).order_by('id').last()
        if last and last.reference_id:
            try:
                last_seq = int(last.reference_id.split('-')[-1])
            except Exception:
                last_seq = last.id or 0
            seq = last_seq + 1
        else:
            seq = 1
        return f"REQ-{date_str}-{str(seq).zfill(4)}"

    @transaction.atomic
    def save(self, *args, **kwargs):
        new = self.pk is None
        if new and not self.po_number:
            candidate = self._generate_po_number()
            i = 0
            while PurchaseOrder.objects.filter(po_number=candidate).exists():
                i += 1
                candidate = f"{candidate}-{i}"
            self.po_number = candidate

        if new and not self.reference_id:
            candidate_ref = self._generate_reference()
            i = 0
            while PurchaseOrder.objects.filter(reference_id=candidate_ref).exists():
                i += 1
                candidate_ref = f"{candidate_ref}-{i}"
            self.reference_id = candidate_ref

        super().save(*args, **kwargs)

    def recompute_totals(self):
        lines = self.lines.all()
        untaxed = sum((l.untaxed_amount for l in lines), Decimal('0.00'))
        tax = sum((l.tax_amount for l in lines), Decimal('0.00'))
        grand = untaxed + tax
        self.untaxed_total = untaxed.quantize(Decimal('0.01'))
        self.tax_total = tax.quantize(Decimal('0.01'))
        self.grand_total = grand.quantize(Decimal('0.01'))
        self.save(update_fields=["untaxed_total", "tax_total", "grand_total"])


class PurchaseOrderLine(models.Model):
    # Use 'order' here or 'po' — just be consistent. I've used 'order'.
    order = models.ForeignKey(PurchaseOrder, related_name='lines', on_delete=models.CASCADE)
    # make product nullable to avoid migration errors when existing rows are null
    product = models.ForeignKey('core.Product', on_delete=models.PROTECT, null=True, blank=True)
    hsn = models.CharField(max_length=32, blank=True, null=True)
    qty = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('1.00'))
    unit_price = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))
    tax_percent = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal('0.00'))

    @property
    def untaxed_amount(self):
        return (self.qty or Decimal('0.00')) * (self.unit_price or Decimal('0.00'))

    @property
    def tax_amount(self):
        return (self.untaxed_amount * (self.tax_percent or Decimal('0.00')) / Decimal('100.00'))

    @property
    def line_total(self):
        return self.untaxed_amount + self.tax_amount

    def save(self, *args, **kwargs):
        # ensure hsn if product present
        if self.product and not self.hsn:
            self.hsn = getattr(self.product, 'hsn', '') or ''
        super().save(*args, **kwargs)