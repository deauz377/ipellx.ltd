from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.urls import reverse_lazy
from django.db.models import Sum, Q
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from tenants.decorators import role_required
from .models import (
    ChartOfAccounts, Journal, JournalEntry, Invoice, InvoiceItem,
    Bill, BillItem, BankAccount, BankTransaction, Budget, BudgetLine,
    FinancialReport, TaxConfiguration, MPesaIntegration, BankReconciliation,
    SavingsGoal, SavingsTransaction
)
from .forms import (
    ChartOfAccountsForm, JournalForm, JournalEntryForm, InvoiceForm,
    BillForm, BankAccountForm, BankTransactionForm, BudgetForm,
    TaxConfigurationForm, MPesaIntegrationForm, BankReconciliationForm
)


class ManagerRequiredMixin:
    """Restricts a class-based view to OWNER/MANAGER/ACCOUNTANT — accounting
    data (bank accounts, journals, budgets) shouldn't be visible to Staff."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.has_role('OWNER', 'MANAGER', 'ACCOUNTANT'):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


@role_required('OWNER', 'MANAGER', 'ACCOUNTANT')
def accounting_dashboard(request):
    """Accounting dashboard overview"""
    tenant = request.user.tenant

    receivable_invoices = Invoice.objects.filter(tenant=tenant, status__in=['partial', 'issued'])
    payable_bills = Bill.objects.filter(tenant=tenant, status__in=['partial', 'received'])
    total_receivables = sum((invoice.total_amount - invoice.paid_amount) for invoice in receivable_invoices) or 0
    total_payables = sum((bill.total_amount - bill.paid_amount) for bill in payable_bills) or 0

    context = {
        'total_invoices': Invoice.objects.filter(tenant=tenant).count() if tenant else 0,
        'total_journal_entries': JournalEntry.objects.filter(tenant=tenant).count() if tenant else 0,
        'chart_accounts': ChartOfAccounts.objects.filter(tenant=tenant).count() if tenant else 0,
        'invoices': Invoice.objects.filter(tenant=tenant, status__in=['issued', 'sent']).count() if tenant else 0,
        'bills': Bill.objects.filter(tenant=tenant, status__in=['received', 'partial']).count() if tenant else 0,
        'total_receivables': total_receivables,
        'total_payables': total_payables,
        'bank_accounts': BankAccount.objects.filter(tenant=tenant).count() if tenant else 0,
        'recent_invoices': Invoice.objects.filter(tenant=tenant)[:5] if tenant else [],
        'recent_bills': Bill.objects.filter(tenant=tenant)[:5] if tenant else [],
    }
    return render(request, 'accounting/dashboard.html', context)


class ChartOfAccountsListView(ManagerRequiredMixin, LoginRequiredMixin, ListView):
    model = ChartOfAccounts
    template_name = 'accounting/chart_of_accounts_list.html'
    context_object_name = 'accounts'
    paginate_by = 20

    def get_queryset(self):
        tenant = self.request.user.tenant
        if tenant:
            return ChartOfAccounts.objects.filter(tenant=tenant).order_by('account_number')
        return ChartOfAccounts.objects.none()


class ChartOfAccountsCreateView(ManagerRequiredMixin, LoginRequiredMixin, CreateView):
    model = ChartOfAccounts
    form_class = ChartOfAccountsForm
    template_name = 'accounting/chart_of_accounts_form.html'
    success_url = reverse_lazy('accounting:chart_accounts_list')

    def form_valid(self, form):
        form.instance.tenant = self.request.user.tenant
        messages.success(self.request, 'Chart of accounts created successfully!')
        return super().form_valid(form)


class JournalListView(ManagerRequiredMixin, LoginRequiredMixin, ListView):
    model = Journal
    template_name = 'accounting/journal_list.html'
    context_object_name = 'journals'
    paginate_by = 10

    def get_queryset(self):
        tenant = self.request.user.tenant
        if tenant:
            return Journal.objects.filter(tenant=tenant)
        return Journal.objects.none()


class JournalCreateView(ManagerRequiredMixin, LoginRequiredMixin, CreateView):
    model = Journal
    form_class = JournalForm
    template_name = 'accounting/journal_form.html'
    success_url = reverse_lazy('accounting:journal_list')

    def form_valid(self, form):
        form.instance.tenant = self.request.user.tenant
        messages.success(self.request, 'Journal created successfully!')
        return super().form_valid(form)


class JournalEntryListView(ManagerRequiredMixin, LoginRequiredMixin, ListView):
    model = JournalEntry
    template_name = 'accounting/journal_entry_list.html'
    context_object_name = 'entries'
    paginate_by = 20

    def get_queryset(self):
        tenant = self.request.user.tenant
        if tenant:
            return JournalEntry.objects.filter(tenant=tenant).order_by('-entry_date')
        return JournalEntry.objects.none()


class JournalEntryCreateView(ManagerRequiredMixin, LoginRequiredMixin, CreateView):
    model = JournalEntry
    form_class = JournalEntryForm
    template_name = 'accounting/journal_entry_form.html'
    success_url = reverse_lazy('accounting:entry_list')

    def form_valid(self, form):
        form.instance.tenant = self.request.user.tenant
        form.instance.created_by = self.request.user
        messages.success(self.request, 'Journal entry created successfully!')
        return super().form_valid(form)


@role_required('OWNER', 'MANAGER', 'ACCOUNTANT')
def post_journal_entry(request, pk):
    """Post a journal entry to GL"""
    entry = get_object_or_404(JournalEntry, pk=pk)
    if request.method == 'POST':
        entry.is_posted = True
        entry.posted_date = timezone.now()
        entry.save()
        messages.success(request, 'Journal entry posted successfully!')
        return redirect('accounting:entry_list')
    return render(request, 'accounting/post_journal_entry.html', {'entry': entry})


class InvoiceListView(ManagerRequiredMixin, LoginRequiredMixin, ListView):
    model = Invoice
    template_name = 'accounting/invoice_list.html'
    context_object_name = 'invoices'
    paginate_by = 20

    def get_queryset(self):
        tenant = self.request.user.tenant
        if tenant:
            return Invoice.objects.filter(tenant=tenant).order_by('-invoice_date')
        return Invoice.objects.none()


class InvoiceDetailView(ManagerRequiredMixin, LoginRequiredMixin, DetailView):
    model = Invoice
    template_name = 'accounting/invoice_detail.html'
    context_object_name = 'invoice'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['items'] = self.object.items.all()
        return context


class InvoiceCreateView(ManagerRequiredMixin, LoginRequiredMixin, CreateView):
    model = Invoice
    form_class = InvoiceForm
    template_name = 'accounting/invoice_form.html'
    success_url = reverse_lazy('accounting:invoice_list')

    def form_valid(self, form):
        form.instance.tenant = self.request.user.tenant
        form.instance.created_by = self.request.user
        messages.success(self.request, 'Invoice created successfully!')
        return super().form_valid(form)


class InvoiceUpdateView(ManagerRequiredMixin, LoginRequiredMixin, UpdateView):
    model = Invoice
    form_class = InvoiceForm
    template_name = 'accounting/invoice_form.html'
    success_url = reverse_lazy('accounting:invoice_list')

    def form_valid(self, form):
        messages.success(self.request, 'Invoice updated successfully!')
        return super().form_valid(form)


@role_required('OWNER', 'MANAGER', 'ACCOUNTANT')
def mark_invoice_paid(request, pk):
    """Mark invoice as paid"""
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method == 'POST':
        invoice.status = 'paid'
        invoice.paid_amount = invoice.total_amount
        invoice.save()
        messages.success(request, 'Invoice marked as paid!')
        return redirect('accounting:invoice_detail', pk=pk)
    return render(request, 'accounting/mark_invoice_paid.html', {'invoice': invoice})


class BillListView(ManagerRequiredMixin, LoginRequiredMixin, ListView):
    model = Bill
    template_name = 'accounting/bill_list.html'
    context_object_name = 'bills'
    paginate_by = 20

    def get_queryset(self):
        tenant = self.request.user.tenant
        if tenant:
            return Bill.objects.filter(tenant=tenant).order_by('-bill_date')
        return Bill.objects.none()


class BillDetailView(ManagerRequiredMixin, LoginRequiredMixin, DetailView):
    model = Bill
    template_name = 'accounting/bill_detail.html'
    context_object_name = 'bill'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['items'] = self.object.items.all()
        return context


class BillCreateView(ManagerRequiredMixin, LoginRequiredMixin, CreateView):
    model = Bill
    form_class = BillForm
    template_name = 'accounting/bill_form.html'
    success_url = reverse_lazy('accounting:bill_list')

    def form_valid(self, form):
        form.instance.tenant = self.request.user.tenant
        messages.success(self.request, 'Bill created successfully!')
        return super().form_valid(form)


class BankAccountListView(ManagerRequiredMixin, LoginRequiredMixin, ListView):
    model = BankAccount
    template_name = 'accounting/bank_account_list.html'
    context_object_name = 'accounts'
    paginate_by = 10

    def get_queryset(self):
        tenant = self.request.user.tenant
        if tenant:
            return BankAccount.objects.filter(tenant=tenant)
        return BankAccount.objects.none()


class BankAccountCreateView(ManagerRequiredMixin, LoginRequiredMixin, CreateView):
    model = BankAccount
    form_class = BankAccountForm
    template_name = 'accounting/bank_account_form.html'
    success_url = reverse_lazy('accounting:bank_account_list')

    def form_valid(self, form):
        form.instance.tenant = self.request.user.tenant
        messages.success(self.request, 'Bank account created successfully!')
        return super().form_valid(form)


class BankTransactionListView(ManagerRequiredMixin, LoginRequiredMixin, ListView):
    model = BankTransaction
    template_name = 'accounting/bank_transaction_list.html'
    context_object_name = 'transactions'
    paginate_by = 20

    def get_queryset(self):
        tenant = self.request.user.tenant
        if tenant:
            return BankTransaction.objects.filter(tenant=tenant).order_by('-transaction_date')
        return BankTransaction.objects.none()


class BankTransactionCreateView(ManagerRequiredMixin, LoginRequiredMixin, CreateView):
    model = BankTransaction
    form_class = BankTransactionForm
    template_name = 'accounting/bank_transaction_form.html'
    success_url = reverse_lazy('accounting:bank_transaction_list')

    def form_valid(self, form):
        form.instance.tenant = self.request.user.tenant
        messages.success(self.request, 'Bank transaction created successfully!')
        return super().form_valid(form)


class BudgetListView(ManagerRequiredMixin, LoginRequiredMixin, ListView):
    model = Budget
    template_name = 'accounting/budget_list.html'
    context_object_name = 'budgets'
    paginate_by = 10

    def get_queryset(self):
        tenant = self.request.user.tenant
        if tenant:
            return Budget.objects.filter(tenant=tenant).order_by('-fiscal_year')
        return Budget.objects.none()


class BudgetCreateView(ManagerRequiredMixin, LoginRequiredMixin, CreateView):
    model = Budget
    form_class = BudgetForm
    template_name = 'accounting/budget_form.html'
    success_url = reverse_lazy('accounting:budget_list')

    def form_valid(self, form):
        form.instance.tenant = self.request.user.tenant
        messages.success(self.request, 'Budget created successfully!')
        return super().form_valid(form)


@role_required('OWNER', 'MANAGER', 'ACCOUNTANT')
def accountant_dashboard(request):
    """The finance work queue: what is owed, what is due, what is unfunded.

    Separate from accounting_dashboard, which is a totals summary. Every card
    here is something to act on rather than a number to admire -- "7 invoices
    over 30 days late" is a task; "KES 240,000 receivable" is trivia.
    """
    from .accountant_dashboard import build_context
    return render(request, 'accounting/accountant_dashboard.html', build_context(request))


@role_required('OWNER', 'MANAGER', 'ACCOUNTANT')
def trial_balance_report(request):
    """Generate trial balance report"""
    tenant = request.user.tenant
    accounts = ChartOfAccounts.objects.filter(tenant=tenant) if tenant else []
    
    context = {
        'accounts': accounts,
        'total_debits': sum(acc.get_balance() for acc in accounts if acc.account_type in ['asset', 'expense']),
        'total_credits': sum(acc.get_balance() for acc in accounts if acc.account_type in ['liability', 'equity', 'revenue']),
    }
    return render(request, 'accounting/trial_balance.html', context)


@role_required('OWNER', 'MANAGER', 'ACCOUNTANT')
def bank_reconciliation(request):
    """Bank reconciliation view"""
    from decimal import Decimal
    tenant = request.user.tenant
    accounts = BankAccount.objects.filter(tenant=tenant) if tenant else []
    
    if request.method == 'POST':
        bank_balance = Decimal(request.POST.get('bank_balance', 0))
        book_balance = Decimal(request.POST.get('book_balance', 0))
        difference = bank_balance - book_balance

        # bank_account comes straight from POST data -- must be verified as
        # this tenant's own BankAccount before use, not just accepted as-is.
        bank_account = get_object_or_404(BankAccount, pk=request.POST.get('bank_account'), tenant=tenant)

        reconciliation = BankReconciliation.objects.create(
            tenant=tenant,
            bank_account=bank_account,
            reconciliation_date=datetime.strptime(request.POST.get('reconciliation_date'), '%Y-%m-%d').date(),
            bank_balance=bank_balance,
            book_balance=book_balance,
            difference=difference,
            reconciled_by=request.user
        )
        messages.success(request, 'Bank reconciliation completed!')
        return redirect('accounting:dashboard')
    
    return render(request, 'accounting/bank_reconciliation.html', {'accounts': accounts})


@role_required('OWNER')
def savings_goal_list(request):
    """List all business savings goals with their current balance."""
    goals = SavingsGoal.objects.filter(tenant=request.user.tenant, is_active=True)
    total_saved = sum((g.balance for g in goals), Decimal('0'))
    return render(request, 'accounting/savings_goal_list.html', {'goals': goals, 'total_saved': total_saved})


@role_required('OWNER')
def savings_goal_create(request):
    """Create a new savings goal (a named pot to save toward)."""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        target_amount = request.POST.get('target_amount', '').strip()
        notes = request.POST.get('notes', '').strip()
        if not name:
            messages.error(request, 'Please give the savings goal a name.')
            return render(request, 'accounting/savings_goal_form.html')
        goal = SavingsGoal.objects.create(
            tenant=request.user.tenant, name=name,
            target_amount=Decimal(target_amount) if target_amount else None,
            notes=notes, created_by=request.user,
        )
        messages.success(request, f'Savings goal "{goal.name}" created.')
        return redirect('accounting:savings_goal_detail', pk=goal.pk)
    return render(request, 'accounting/savings_goal_form.html')


@role_required('OWNER')
def savings_goal_detail(request, pk):
    """View a savings goal's transaction history, and deposit or
    withdraw money from it. Withdrawals can't exceed the current
    balance — this is meant to protect savings, not just track them."""
    goal = get_object_or_404(SavingsGoal, pk=pk, tenant=request.user.tenant)

    if request.method == 'POST':
        transaction_type = request.POST.get('transaction_type')
        amount_str = request.POST.get('amount', '').strip()
        date_str = request.POST.get('date', '').strip()
        note = request.POST.get('note', '').strip()

        try:
            amount = Decimal(amount_str)
            if amount <= 0:
                raise ValueError
        except Exception:
            messages.error(request, 'Please enter a valid amount greater than zero.')
            return redirect('accounting:savings_goal_detail', pk=goal.pk)

        entry_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else timezone.localdate()

        if transaction_type == 'withdrawal' and amount > goal.balance:
            messages.error(request, f"Can't withdraw KES {amount:,.2f} — the goal only has KES {goal.balance:,.2f} saved.")
            return redirect('accounting:savings_goal_detail', pk=goal.pk)

        if transaction_type not in ('deposit', 'withdrawal'):
            messages.error(request, 'Invalid transaction type.')
            return redirect('accounting:savings_goal_detail', pk=goal.pk)

        SavingsTransaction.objects.create(
            tenant=request.user.tenant, savings_goal=goal, transaction_type=transaction_type,
            amount=amount, date=entry_date, note=note, recorded_by=request.user,
        )
        messages.success(request, f"{transaction_type.title()} of KES {amount:,.2f} recorded.")
        return redirect('accounting:savings_goal_detail', pk=goal.pk)

    transactions = goal.transactions.all()
    return render(request, 'accounting/savings_goal_detail.html', {'goal': goal, 'transactions': transactions})
