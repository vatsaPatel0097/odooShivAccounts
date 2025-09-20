from django.core.management.base import BaseCommand
from core.models import Account   # CHANGE 'yourapp' to your real app name

class Command(BaseCommand):
    help = "Seed default Chart of Accounts (safe: get_or_create)"

    def handle(self, *args, **options):
        defaults = [
            ('Cash A/c', 'asset', '1000'),
            ('Bank A/c', 'asset', '1010'),
            ('Debtors A/c', 'asset', '1020'),
            ('Creditors A/c', 'liability', '2000'),
            ('Sales Income A/c', 'income', '4000'),
            ('Purchase Expense A/c', 'expense', '5000'),
            ('Other Expense A/c', 'expense', '5100'),
        ]
        created = 0
        for name, typ, code in defaults:
            a, was_created = Account.objects.get_or_create(name=name, defaults={'account_type': typ, 'code': code})
            if was_created:
                self.stdout.write(self.style.SUCCESS(f"Created {name}"))
                created += 1
        if created == 0:
            self.stdout.write(self.style.WARNING("No new accounts created; defaults already exist."))
        else:
            self.stdout.write(self.style.SUCCESS("Seeding complete."))
