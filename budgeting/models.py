from decimal import Decimal

from django.db import models
from django.utils import timezone

from tenants.models import TenantModel


class Budget(TenantModel):
    """A spending plan for one category over one date range. Deliberately
    separate from accounting.Budget/BudgetLine (formal, Chart-of-Accounts-tied,
    fiscal-year budgeting for the Accounting module) -- this is the
    everyday, business-owner-facing version: pick a category, an amount, a
    date range, done. See budgeting app docstring / project plan for why
    these are two different models rather than one forced to serve both.

    spent_amount and everything derived from it are computed live from the
    existing Expense/Order records on every read, not cached on this model
    -- so there is no separate "sync" step and nothing can drift out of
    date. This mirrors dashboard.views.ceo_dashboard's own preference for
    live-computed figures over stored-and-maintained ones.
    """

    PERIOD_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]

    # Kept in sync with expenses.Expense.CATEGORY_CHOICES (minus 'stock_purchases',
    # which has no Expense equivalent -- purchases are recorded as supplier
    # Orders in this ERP, not Expenses) so a budget category always has a
    # real, queryable source of "amount spent".
    CATEGORY_CHOICES = [
        ('stock_purchases', 'Stock/Purchases'),
        ('salaries', 'Salaries & Wages'),
        ('rent', 'Rent'),
        ('electricity', 'Electricity'),
        ('water', 'Water'),
        ('transport', 'Transport'),
        ('marketing', 'Marketing'),
        ('gas_fuel', 'Gas/Fuel'),
        ('maintenance', 'Maintenance'),
        ('food_production', 'Food/Production'),
        ('other', 'Other expenses'),
    ]

    ALERT_THRESHOLDS = (100, 90, 75, 50)

    name = models.CharField(max_length=100)
    period = models.CharField(max_length=10, choices=PERIOD_CHOICES, default='monthly')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    # Only used (and only meaningful) when category='other' -- lets the
    # user label what "other" actually means for this budget without
    # needing a new choice added to the model for every one-off category.
    custom_category = models.CharField(max_length=100, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField()
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey('tenants.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date', 'name']

    def __str__(self):
        return f'{self.name} ({self.get_category_display()}, {self.get_period_display()})'

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError('End date cannot be before start date.')

    @property
    def display_category(self):
        if self.category == 'other' and self.custom_category:
            return self.custom_category
        return self.get_category_display()

    def _spend_window(self):
        """The overlap of this budget's own date range with "so far" --
        spending after today hasn't happened yet, so it's excluded even if
        end_date is in the future (e.g. a monthly budget spanning the rest
        of the month)."""
        today = timezone.localdate()
        window_end = min(self.end_date, today)
        if window_end < self.start_date:
            return None, None
        return self.start_date, window_end

    @property
    def spent_amount(self):
        from .utils import category_spend
        start, end = self._spend_window()
        return category_spend(self.tenant, self.category, start, end)

    @property
    def remaining_amount(self):
        return self.amount - self.spent_amount

    @property
    def usage_percent(self):
        if not self.amount:
            return Decimal('0')
        return (self.spent_amount / self.amount) * 100

    @property
    def is_over_budget(self):
        return self.spent_amount > self.amount

    @property
    def over_amount(self):
        excess = self.spent_amount - self.amount
        return excess if excess > 0 else Decimal('0')

    @property
    def alert_level(self):
        """Highest threshold reached, as an int (50/75/90/100), 'over' past
        100%, or None if under 50%. Purely a computed display value -- no
        Alert/notification model, nothing to trigger; the dashboard/detail
        views just render whatever this currently is."""
        if self.is_over_budget:
            return 'over'
        pct = self.usage_percent
        for threshold in self.ALERT_THRESHOLDS:
            if pct >= threshold:
                return threshold
        return None

    def covers(self, day):
        return self.start_date <= day <= self.end_date
