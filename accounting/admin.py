from django.contrib import admin
from .models import (
    ChartOfAccounts, Journal, JournalEntry, Invoice, InvoiceItem,
    Bill, BillItem, BankAccount, BankTransaction, BankReconciliation,
    Budget, BudgetLine, FinancialReport, TaxConfiguration,
    MPesaIntegration, MPesaTransaction
)


@admin.register(ChartOfAccounts)
class ChartOfAccountsAdmin(admin.ModelAdmin):
    list_display = ('account_number', 'account_name', 'account_type', 'opening_balance', 'is_active')
    list_filter = ('account_type', 'is_active')
    search_fields = ('account_number', 'account_name')
    ordering = ('account_number',)


@admin.register(Journal)
class JournalAdmin(admin.ModelAdmin):
    list_display = ('name', 'journal_type', 'is_active', 'created_at')
    list_filter = ('journal_type', 'is_active')
    search_fields = ('name',)


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ('reference_number', 'journal', 'account', 'entry_type', 'amount', 'is_posted', 'entry_date')
    list_filter = ('journal', 'entry_type', 'is_posted', 'entry_date')
    search_fields = ('reference_number', 'account__account_name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'customer_name', 'invoice_date', 'total_amount', 'paid_amount', 'status')
    list_filter = ('status', 'invoice_date', 'due_date')
    search_fields = ('invoice_number', 'customer_name', 'customer_email')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'description', 'quantity', 'unit_price', 'amount')
    search_fields = ('invoice__invoice_number', 'description')


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ('bill_number', 'vendor', 'bill_date', 'total_amount', 'paid_amount', 'status')
    list_filter = ('status', 'bill_date', 'due_date')
    search_fields = ('bill_number', 'vendor')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(BillItem)
class BillItemAdmin(admin.ModelAdmin):
    list_display = ('bill', 'description', 'quantity', 'unit_price', 'amount')
    search_fields = ('bill__bill_number', 'description')


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('account_name', 'account_type', 'account_number', 'current_balance', 'is_active')
    list_filter = ('account_type', 'is_active')
    search_fields = ('account_name', 'account_number', 'bank_name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = ('bank_account', 'transaction_date', 'transaction_type', 'description', 'amount', 'reconciled')
    list_filter = ('transaction_type', 'transaction_date', 'reconciled')
    search_fields = ('bank_account__account_name', 'reference_number', 'description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(BankReconciliation)
class BankReconciliationAdmin(admin.ModelAdmin):
    list_display = ('bank_account', 'reconciliation_date', 'bank_balance', 'book_balance', 'difference', 'status')
    list_filter = ('status', 'reconciliation_date')
    search_fields = ('bank_account__account_name',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ('name', 'fiscal_year', 'budget_period', 'status', 'created_at')
    list_filter = ('fiscal_year', 'budget_period', 'status')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(BudgetLine)
class BudgetLineAdmin(admin.ModelAdmin):
    list_display = ('budget', 'account', 'period', 'budgeted_amount', 'actual_amount', 'variance')
    list_filter = ('budget', 'period')
    search_fields = ('account__account_name',)


@admin.register(FinancialReport)
class FinancialReportAdmin(admin.ModelAdmin):
    list_display = ('name', 'report_type', 'start_date', 'end_date', 'status')
    list_filter = ('report_type', 'status', 'start_date')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(TaxConfiguration)
class TaxConfigurationAdmin(admin.ModelAdmin):
    list_display = ('tax_type', 'tax_rate', 'tax_account', 'is_active')
    list_filter = ('tax_type', 'is_active')
    search_fields = ('tax_type',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(MPesaIntegration)
class MPesaIntegrationAdmin(admin.ModelAdmin):
    list_display = ('business_shortcode', 'is_active', 'created_at')
    list_filter = ('is_active',)
    fieldsets = (
        ('Business Information', {
            'fields': ('business_shortcode',)
        }),
        ('Credentials', {
            'fields': ('consumer_key', 'consumer_secret', 'passkey'),
            'classes': ('collapse',)
        }),
        ('Configuration', {
            'fields': ('api_endpoint',)
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(MPesaTransaction)
class MPesaTransactionAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'amount', 'status', 'transaction_id', 'transaction_date')
    list_filter = ('status', 'transaction_date')
    search_fields = ('phone_number', 'transaction_id', 'receipt_number')
    readonly_fields = ('transaction_date', 'updated_at')
