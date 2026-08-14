from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
from tenants.models import TenantModel
from decimal import Decimal
from datetime import datetime


class ChartOfAccounts(TenantModel):
    """
    Chart of Accounts - account heads for GL
    """
    ACCOUNT_TYPE_CHOICES = [
        ('asset', 'Asset'),
        ('liability', 'Liability'),
        ('equity', 'Equity'),
        ('revenue', 'Revenue'),
        ('expense', 'Expense'),
    ]

    account_number = models.CharField(max_length=20, unique=True)
    account_name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES)
    description = models.TextField(blank=True)
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Chart of Accounts'
        verbose_name_plural = 'Chart of Accounts'
        ordering = ['account_number']

    def __str__(self):
        return f"{self.account_number} - {self.account_name}"

    def get_balance(self):
        """Calculate current balance of account"""
        debit = self.journal_entries.filter(entry_type='debit').aggregate(
            total=models.Sum('amount'))['total'] or 0
        credit = self.journal_entries.filter(entry_type='credit').aggregate(
            total=models.Sum('amount'))['total'] or 0
        
        if self.account_type in ['asset', 'expense']:
            return self.opening_balance + debit - credit
        else:  # liability, equity, revenue
            return self.opening_balance - debit + credit


class Journal(TenantModel):
    """
    Journals for recording transactions
    """
    JOURNAL_TYPE_CHOICES = [
        ('general', 'General Journal'),
        ('sales', 'Sales Journal'),
        ('purchase', 'Purchase Journal'),
        ('cash', 'Cash Journal'),
        ('bank', 'Bank Journal'),
    ]

    name = models.CharField(max_length=100)
    journal_type = models.CharField(max_length=20, choices=JOURNAL_TYPE_CHOICES)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Journal'
        verbose_name_plural = 'Journals'

    def __str__(self):
        return f"{self.name} ({self.get_journal_type_display()})"


class JournalEntry(TenantModel):
    """
    Individual journal entries for GL transactions
    """
    ENTRY_TYPE_CHOICES = [
        ('debit', 'Debit'),
        ('credit', 'Credit'),
    ]

    journal = models.ForeignKey(Journal, on_delete=models.PROTECT, related_name='entries')
    reference_number = models.CharField(max_length=50, unique=True)
    entry_date = models.DateField()
    account = models.ForeignKey(ChartOfAccounts, on_delete=models.PROTECT, related_name='journal_entries')
    entry_type = models.CharField(max_length=10, choices=ENTRY_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(0)])
    description = models.TextField(blank=True)
    related_document = models.CharField(max_length=100, blank=True)  # Invoice, Bill, etc.
    is_posted = models.BooleanField(default=False)
    posted_date = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_journal_entries')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Journal Entry'
        verbose_name_plural = 'Journal Entries'
        ordering = ['-entry_date', '-id']

    def __str__(self):
        return f"{self.reference_number} - {self.account.account_name}"


class Invoice(TenantModel):
    """
    Accounting invoices - for customer billing (distinct from sales invoices)
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('issued', 'Issued'),
        ('sent', 'Sent'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]

    invoice_number = models.CharField(max_length=50, unique=True)
    invoice_date = models.DateField(default=timezone.now)
    due_date = models.DateField()
    customer = models.ForeignKey('customers.Customer', on_delete=models.SET_NULL, null=True, blank=True, related_name='accounting_invoices')
    customer_name = models.CharField(max_length=100)
    customer_email = models.EmailField(blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    payment_terms = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)
    terms_and_conditions = models.TextField(blank=True)
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_accounting_invoices')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Invoice'
        verbose_name_plural = 'Invoices'
        ordering = ['-invoice_date']

    def __str__(self):
        return f"{self.invoice_number}"

    @property
    def balance_due(self):
        return self.total_amount - self.paid_amount

    @property
    def is_overdue(self):
        from datetime import date
        return date.today() > self.due_date and self.status != 'paid'


class InvoiceItem(TenantModel):
    """
    Line items for accounting invoices
    """
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        verbose_name = 'Invoice Item'
        verbose_name_plural = 'Invoice Items'

    def __str__(self):
        return f"{self.invoice} - {self.description}"


class Bill(TenantModel):
    """
    Purchase bills / Accounts Payable
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('received', 'Received'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]

    bill_number = models.CharField(max_length=50, unique=True)
    bill_date = models.DateField(default=timezone.now)
    due_date = models.DateField()
    vendor = models.CharField(max_length=100)
    vendor_email = models.EmailField(blank=True)
    vendor_phone = models.CharField(max_length=20, blank=True)
    
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    payment_terms = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Bill'
        verbose_name_plural = 'Bills'
        ordering = ['-bill_date']

    def __str__(self):
        return f"{self.bill_number}"

    @property
    def balance_due(self):
        return self.total_amount - self.paid_amount


class BillItem(TenantModel):
    """
    Line items for bills
    """
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name='items')
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        verbose_name = 'Bill Item'
        verbose_name_plural = 'Bill Items'

    def __str__(self):
        return f"{self.bill} - {self.description}"


class BankAccount(TenantModel):
    """
    Bank and Cash accounts
    """
    ACCOUNT_TYPE_CHOICES = [
        ('checking', 'Checking Account'),
        ('savings', 'Savings Account'),
        ('cash', 'Cash'),
        ('mpesa', 'M-Pesa Account'),
    ]

    account_name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES)
    account_number = models.CharField(max_length=50)
    bank_name = models.CharField(max_length=100, blank=True)
    branch_code = models.CharField(max_length=20, blank=True)
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    current_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='KES')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Bank Account'
        verbose_name_plural = 'Bank Accounts'

    def __str__(self):
        return f"{self.account_name} ({self.account_number})"


class BankTransaction(TenantModel):
    """
    Bank and cash transactions
    """
    TRANSACTION_TYPE_CHOICES = [
        ('deposit', 'Deposit'),
        ('withdrawal', 'Withdrawal'),
        ('transfer', 'Transfer'),
        ('check', 'Check'),
    ]

    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    transaction_date = models.DateField()
    reference_number = models.CharField(max_length=50, blank=True)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    balance_after = models.DecimalField(max_digits=15, decimal_places=2)
    reconciled = models.BooleanField(default=False)
    reconciled_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Bank Transaction'
        verbose_name_plural = 'Bank Transactions'
        ordering = ['-transaction_date']

    def __str__(self):
        return f"{self.bank_account} - {self.description}"


class BankReconciliation(TenantModel):
    """
    Bank reconciliation records
    """
    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name='reconciliations')
    reconciliation_date = models.DateField()
    bank_balance = models.DecimalField(max_digits=15, decimal_places=2)
    book_balance = models.DecimalField(max_digits=15, decimal_places=2)
    difference = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('matched', 'Matched'),
        ('reconciled', 'Reconciled'),
    ], default='pending')
    notes = models.TextField(blank=True)
    reconciled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reconciled_bank_accounts')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Bank Reconciliation'
        verbose_name_plural = 'Bank Reconciliations'

    def __str__(self):
        return f"{self.bank_account} - {self.reconciliation_date}"


class Budget(TenantModel):
    """
    Budget planning and forecasting
    """
    name = models.CharField(max_length=100)
    fiscal_year = models.IntegerField()
    budget_period = models.CharField(max_length=20, choices=[
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('annual', 'Annual'),
    ])
    status = models.CharField(max_length=20, choices=[
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('active', 'Active'),
        ('closed', 'Closed'),
    ], default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Budget'
        verbose_name_plural = 'Budgets'

    def __str__(self):
        return f"{self.name} (FY {self.fiscal_year})"


class BudgetLine(TenantModel):
    """
    Budget line items
    """
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(ChartOfAccounts, on_delete=models.PROTECT)
    period = models.CharField(max_length=20)
    budgeted_amount = models.DecimalField(max_digits=15, decimal_places=2)
    actual_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    variance = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'Budget Line'
        verbose_name_plural = 'Budget Lines'

    def __str__(self):
        return f"{self.budget} - {self.account}"


class FinancialReport(TenantModel):
    """
    Financial reports configuration
    """
    REPORT_TYPE_CHOICES = [
        ('income_statement', 'Income Statement'),
        ('balance_sheet', 'Balance Sheet'),
        ('cash_flow', 'Cash Flow'),
        ('trial_balance', 'Trial Balance'),
        ('general_ledger', 'General Ledger'),
    ]

    name = models.CharField(max_length=100)
    report_type = models.CharField(max_length=30, choices=REPORT_TYPE_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=[
        ('draft', 'Draft'),
        ('finalized', 'Finalized'),
        ('archived', 'Archived'),
    ], default='draft')
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Financial Report'
        verbose_name_plural = 'Financial Reports'

    def __str__(self):
        return f"{self.name} ({self.get_report_type_display()})"


class MPesaIntegration(TenantModel):
    """
    M-Pesa payment integration configuration
    """
    business_shortcode = models.CharField(max_length=10)
    consumer_key = models.CharField(max_length=255)
    consumer_secret = models.CharField(max_length=255)
    passkey = models.CharField(max_length=255)
    api_endpoint = models.URLField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'M-Pesa Integration'
        verbose_name_plural = 'M-Pesa Integrations'

    def __str__(self):
        return f"M-Pesa ({self.business_shortcode})"


class MPesaTransaction(TenantModel):
    """
    M-Pesa payment transactions
    """
    STATUS_CHOICES = [
        ('initiated', 'Initiated'),
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    mpesa_integration = models.ForeignKey(MPesaIntegration, on_delete=models.PROTECT)
    transaction_id = models.CharField(max_length=100, unique=True)
    phone_number = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='initiated')
    reference = models.CharField(max_length=100, blank=True)
    receipt_number = models.CharField(max_length=100, blank=True)
    response_code = models.CharField(max_length=10, blank=True)
    response_description = models.TextField(blank=True)
    transaction_date = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'M-Pesa Transaction'
        verbose_name_plural = 'M-Pesa Transactions'

    def __str__(self):
        return f"{self.phone_number} - {self.amount}"


class TaxConfiguration(TenantModel):
    """
    Tax configuration (VAT, income tax, etc.)
    """
    tax_type = models.CharField(max_length=50)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2)
    tax_account = models.ForeignKey(ChartOfAccounts, on_delete=models.PROTECT)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Tax Configuration'
        verbose_name_plural = 'Tax Configurations'

    def __str__(self):
        return f"{self.tax_type} ({self.tax_rate}%)"


class SavingsGoal(TenantModel):
    """A business savings pot — money set aside for a purpose (equipment,
    rent buffer, expansion, emergencies). A simple deposit/withdrawal
    ledger, kept separate from day-to-day bank accounts so savings don't
    get mixed up with operating cash."""
    name = models.CharField(max_length=100)
    target_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Optional. Leave blank if you're not saving toward a specific amount.",
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('tenants.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def balance(self):
        deposits = self.transactions.filter(transaction_type='deposit').aggregate(t=models.Sum('amount'))['t'] or 0
        withdrawals = self.transactions.filter(transaction_type='withdrawal').aggregate(t=models.Sum('amount'))['t'] or 0
        return deposits - withdrawals

    @property
    def progress_percent(self):
        if not self.target_amount or self.target_amount <= 0:
            return None
        pct = (self.balance / self.target_amount) * 100
        return min(round(pct), 100)


class SavingsTransaction(TenantModel):
    TRANSACTION_TYPE_CHOICES = [
        ('deposit', 'Deposit'),
        ('withdrawal', 'Withdrawal'),
    ]
    savings_goal = models.ForeignKey(SavingsGoal, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    note = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey('tenants.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.get_transaction_type_display()} of {self.amount} - {self.savings_goal.name}"
