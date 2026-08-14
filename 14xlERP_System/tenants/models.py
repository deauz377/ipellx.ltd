from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError


class TenantManager(models.Manager):
    def get_queryset(self):
        queryset = super().get_queryset()
        from .middleware import get_current_tenant, is_super_admin  # Import here
        tenant = get_current_tenant()
        if tenant and not is_super_admin() and not hasattr(self, '_ignore_tenant'):
            return queryset.filter(tenant=tenant)
        return queryset

    def for_tenant(self, tenant):
        self._tenant = tenant
        return self

    def ignore_tenant(self):
        self._ignore_tenant = True
        return self


class Tenant(models.Model):
    name = models.CharField(max_length=100, unique=True)
    subdomain = models.CharField(max_length=100, unique=True)  # For subdomain routing
    phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=255, blank=True)
    receipt_footer = models.CharField(
        max_length=200, blank=True, default='Thank you for your business!',
        help_text='Message shown at the bottom of printed receipts.',
    )
    paid_until = models.DateTimeField()
    on_trial = models.BooleanField(default=True)
    created_on = models.DateField(auto_now_add=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    class Role(models.TextChoices):
        OWNER = 'OWNER', 'Owner'
        MANAGER = 'MANAGER', 'Manager'
        STAFF = 'STAFF', 'Staff'

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STAFF)
    is_super_admin = models.BooleanField(default=False)
    encrypted_ssn = models.CharField(max_length=11, blank=True, null=True)  # Placeholder for encryption

    class Meta:
        permissions = [
            ('view_tenant_data', 'Can view tenant data'),
            ('edit_tenant_data', 'Can edit tenant data'),
            ('delete_tenant_data', 'Can delete tenant data'),
        ]

    def clean(self):
        if self.is_super_admin and not self.is_staff:
            raise ValidationError("Super admin must be staff.")
        super().clean()

    def save(self, *args, **kwargs):
        # Owners get full Django admin access automatically, so promoting
        # someone to Owner (e.g. via the admin's role dropdown) is enough —
        # no separate is_staff/is_superuser toggling needed.
        if self.role == self.Role.OWNER:
            self.is_staff = True
            self.is_superuser = True
        super().save(*args, **kwargs)

    def has_role(self, *roles):
        return self.is_super_admin or self.role in roles


# Base model for tenant-specific models
class TenantModel(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True, related_name='+')

    objects = TenantManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if hasattr(self, 'tenant') and not self.tenant:
            # Set tenant from request if not set
            from django.utils.deprecation import MiddlewareMixin
            # But better to set in views
            pass
        super().save(*args, **kwargs)


class SubscriptionPlan(models.Model):
    """A billing plan a business can subscribe to (e.g. Monthly, Yearly).
    Platform-wide — not tied to any one tenant."""
    name = models.CharField(max_length=50)
    price_kes = models.DecimalField(max_digits=10, decimal_places=2)
    duration_days = models.PositiveIntegerField(help_text="How many days of access this plan grants.")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} - KES {self.price_kes} / {self.duration_days} days"


class SubscriptionPayment(models.Model):
    """A payment a business has submitted towards a subscription. Starts
    'pending' until a platform admin (is_super_admin=True) reviews it and
    extends the tenant's paid_until date."""
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='subscription_payments')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT)
    reference = models.CharField(max_length=100, help_text="M-Pesa code or other payment reference.")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    submitted_by = models.ForeignKey('tenants.User', on_delete=models.SET_NULL, null=True, related_name='+')
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey('tenants.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    reviewed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.tenant.name} - {self.plan.name} - {self.status}"

    def approve(self, reviewer):
        from django.utils import timezone
        now = timezone.now()
        base = self.tenant.paid_until if self.tenant.paid_until and self.tenant.paid_until > now else now
        self.tenant.paid_until = base + timezone.timedelta(days=self.plan.duration_days)
        self.tenant.on_trial = False
        self.tenant.save(update_fields=['paid_until', 'on_trial'])
        self.status = 'approved'
        self.reviewed_by = reviewer
        self.reviewed_at = now
        self.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])
