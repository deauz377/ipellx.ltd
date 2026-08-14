from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Tenant, User, SubscriptionPlan, SubscriptionPayment


class TenantScopedAdminMixin:
    """Restricts an admin's queryset and editable objects to the logged-in
    user's own tenant, unless they're a true platform-level super admin
    (is_super_admin=True). Prevents one business's Owner from browsing or
    editing another business's records through /admin/."""

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_super_admin:
            return qs
        if self.tenant_filter_field == 'pk':
            return qs.filter(pk=request.user.tenant_id)
        return qs.filter(**{f"{self.tenant_filter_field}_id": request.user.tenant_id})

    def has_view_or_change_permission(self, request, obj=None):
        has_base = super().has_view_or_change_permission(request, obj)
        if not has_base or obj is None or request.user.is_super_admin:
            return has_base
        return self._same_tenant(request, obj)

    def has_delete_permission(self, request, obj=None):
        has_base = super().has_delete_permission(request, obj)
        if not has_base or obj is None or request.user.is_super_admin:
            return has_base
        return self._same_tenant(request, obj)

    def _same_tenant(self, request, obj):
        target_id = obj.pk if self.tenant_filter_field == 'pk' else getattr(obj, f"{self.tenant_filter_field}_id")
        return target_id == request.user.tenant_id


@admin.register(Tenant)
class TenantAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    tenant_filter_field = 'pk'  # Tenant *is* the tenant — compare directly
    list_display = ('name', 'subdomain', 'phone', 'on_trial', 'paid_until', 'created_on')
    search_fields = ('name', 'subdomain')
    fields = ('name', 'subdomain', 'phone', 'address', 'receipt_footer', 'paid_until', 'on_trial')

    def has_add_permission(self, request):
        # Creating new tenants is a platform-level action (this is how a
        # new business gets onto the system) — regular Owners shouldn't
        # do this from the admin; it belongs in the signup flow.
        return request.user.is_super_admin


@admin.register(User)
class UserAdmin(TenantScopedAdminMixin, DjangoUserAdmin):
    tenant_filter_field = 'tenant'
    list_display = ('username', 'email', 'tenant', 'role', 'is_super_admin', 'is_staff', 'is_active')
    list_filter = ('tenant', 'role', 'is_super_admin', 'is_staff', 'is_active')
    fieldsets = DjangoUserAdmin.fieldsets + (
        ('Tenant & role', {'fields': ('tenant', 'role', 'is_super_admin')}),
    )

    def has_add_permission(self, request):
        # New accounts for a business should come from that business's own
        # Owner (once we build the "invite teammate" flow), not from
        # another business's Owner via /admin/.
        return request.user.is_super_admin or super().has_add_permission(request)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # Even with queryset scoping above, the tenant dropdown itself must
        # not let a non-super-admin Owner pick a *different* business to
        # attach a new user to.
        if db_field.name == 'tenant' and not request.user.is_super_admin:
            kwargs['queryset'] = Tenant.objects.filter(pk=request.user.tenant_id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    # Platform-wide — every business needs to see the same plan list, so
    # this is intentionally NOT tenant-scoped, but only a platform super
    # admin should be able to manage it.
    list_display = ('name', 'price_kes', 'duration_days', 'is_active')

    def has_module_permission(self, request):
        return request.user.is_authenticated and request.user.is_super_admin

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)


@admin.register(SubscriptionPayment)
class SubscriptionPaymentAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'plan', 'reference', 'amount', 'status', 'submitted_at')
    list_filter = ('status', 'plan')
    search_fields = ('tenant__name', 'reference')
    actions = ['approve_payments']

    def has_module_permission(self, request):
        return request.user.is_authenticated and request.user.is_super_admin

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)

    @admin.action(description='Approve selected payments (extends tenant access)')
    def approve_payments(self, request, queryset):
        count = 0
        for payment in queryset.filter(status='pending'):
            payment.approve(reviewer=request.user)
            count += 1
        self.message_user(request, f"Approved {count} payment(s).")
