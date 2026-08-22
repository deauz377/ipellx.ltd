from django.urls import path
from . import views

app_name = 'accounting'

urlpatterns = [
    # Dashboard
    path('', views.accounting_dashboard, name='dashboard'),
    
    # Chart of Accounts
    path('chart-of-accounts/', views.ChartOfAccountsListView.as_view(), name='chart_accounts_list'),
    path('chart-of-accounts/create/', views.ChartOfAccountsCreateView.as_view(), name='chart_accounts_create'),
    
    # Journals
    path('journals/', views.JournalListView.as_view(), name='journal_list'),
    path('journals/create/', views.JournalCreateView.as_view(), name='journal_create'),
    
    # Journal Entries
    path('entries/', views.JournalEntryListView.as_view(), name='entry_list'),
    path('entries/create/', views.JournalEntryCreateView.as_view(), name='entry_create'),
    path('entries/<int:pk>/post/', views.post_journal_entry, name='post_entry'),
    
    # Invoices
    path('invoices/', views.InvoiceListView.as_view(), name='invoice_list'),
    path('invoices/<int:pk>/', views.InvoiceDetailView.as_view(), name='invoice_detail'),
    path('invoices/create/', views.InvoiceCreateView.as_view(), name='invoice_create'),
    path('invoices/<int:pk>/edit/', views.InvoiceUpdateView.as_view(), name='invoice_edit'),
    path('invoices/<int:pk>/mark-paid/', views.mark_invoice_paid, name='mark_invoice_paid'),
    
    # Bills
    path('bills/', views.BillListView.as_view(), name='bill_list'),
    path('bills/<int:pk>/', views.BillDetailView.as_view(), name='bill_detail'),
    path('bills/create/', views.BillCreateView.as_view(), name='bill_create'),
    
    # Bank Accounts
    path('bank-accounts/', views.BankAccountListView.as_view(), name='bank_account_list'),
    path('bank-accounts/create/', views.BankAccountCreateView.as_view(), name='bank_account_create'),
    
    # Bank Transactions
    path('transactions/', views.BankTransactionListView.as_view(), name='bank_transaction_list'),
    path('transactions/create/', views.BankTransactionCreateView.as_view(), name='bank_transaction_create'),
    
    # Budgets
    path('budgets/', views.BudgetListView.as_view(), name='budget_list'),
    path('budgets/create/', views.BudgetCreateView.as_view(), name='budget_create'),
    
    # Reports
    path('finance/', views.accountant_dashboard, name='accountant_dashboard'),
    path('reports/trial-balance/', views.trial_balance_report, name='trial_balance'),
    path('reports/bank-reconciliation/', views.bank_reconciliation, name='bank_reconciliation'),

    # Savings
    path('savings/', views.savings_goal_list, name='savings_goal_list'),
    path('savings/create/', views.savings_goal_create, name='savings_goal_create'),
    path('savings/<int:pk>/', views.savings_goal_detail, name='savings_goal_detail'),
]
