from django.contrib.auth.hashers import make_password, check_password
import re
from decimal import Decimal
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from .models import JournalEntry, JournalLine


def hash_pw(raw):
    return make_password(raw)

def verify_pw(stored, raw):
    return check_password(raw, stored)

def validate_password_complexity(pwd):
    if not pwd or len(pwd) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r'[a-z]', pwd):
        return False, "Password must contain a lowercase letter."
    if not re.search(r'[A-Z]', pwd):
        return False, "Password must contain an uppercase letter."
    if not re.search(r'\d', pwd):
        return False, "Password must contain a digit."
    if not re.search(r'[^A-Za-z0-9]', pwd):
        return False, "Password must contain a special character."
    return True, ""


class JournalError(Exception):
    pass

def _as_decimal(value):
    try:
        return Decimal(value)
    except Exception:
        return Decimal('0.00')

@transaction.atomic
def post_journal_entry(date, ref, narration, lines, source=None):
    """
    Post a balanced journal entry.

    Args:
      date: datetime.date instance
      ref: string reference (e.g. 'Bill/2025/0001')
      narration: text
      lines: list of dicts. Each dict:
         {
           'account': Account instance OR account pk,
           'debit': Decimal or numeric (0 if credit),
           'credit': Decimal or numeric (0 if debit),
           'narration': optional str,
           'partner': optional model instance (Contact/vendor/customer)
         }
      source: optional model instance (e.g., vendor bill) - will be linked to JournalEntry.source

    Returns:
      JournalEntry instance
    Raises:
      JournalError if not balanced or invalid input
    """
    total_debit = Decimal('0.00')
    total_credit = Decimal('0.00')

    norm_lines = []
    for ln in lines:
        debit = _as_decimal(ln.get('debit') or 0)
        credit = _as_decimal(ln.get('credit') or 0)
        if debit != Decimal('0.00') and credit != Decimal('0.00'):
            raise JournalError("Line cannot have both debit and credit non-zero")
        if debit == Decimal('0.00') and credit == Decimal('0.00'):
            raise JournalError("Line must have either debit or credit non-zero")
        total_debit += debit
        total_credit += credit
        norm_lines.append({
            'account': ln['account'],
            'debit': debit,
            'credit': credit,
            'narration': ln.get('narration') or '',
            'partner': ln.get('partner')
        })

    # rounding/precision check: allow tiny difference? better strict
    if total_debit != total_credit:
        raise JournalError(f"Unbalanced entry: debits {total_debit} != credits {total_credit}")

    # create header
    je = JournalEntry.objects.create(
        date=date,
        ref=ref,
        narration=narration
    )
    # link source if provided
    if source is not None:
        try:
            je.content_type = ContentType.objects.get_for_model(source.__class__)
            je.object_id = int(source.pk)
            je.save(update_fields=['content_type', 'object_id'])
        except Exception:
            # ignore linking errors, but keep the journal posted
            pass

    # create lines
    jl_objs = []
    for ln in norm_lines:
        account = ln['account']
        # allow passing pk too
        if not hasattr(account, 'pk'):
            # try fetch Account by pk
            from .models import Account
            account = Account.objects.get(pk=int(account))
        partner = ln.get('partner')
        partner_ct = None
        partner_oid = None
        if partner is not None:
            partner_ct = ContentType.objects.get_for_model(partner.__class__)
            partner_oid = int(partner.pk)
        jl = JournalLine.objects.create(
            entry=je,
            account=account,
            debit=ln['debit'],
            credit=ln['credit'],
            narration=ln.get('narration') or '',
            partner_content_type=partner_ct,
            partner_object_id=partner_oid,
            date=date
        )
        jl_objs.append(jl)

    return je