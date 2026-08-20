from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm


class VerifiedAdminAuthenticationForm(AdminAuthenticationForm):
    """Closes a real self-bypass: a new signup's account is granted
    is_staff=True/is_superuser=True as soon as role=OWNER is set (see
    tenants.models.User.save()), before its email is verified. Without this,
    that account could skip core.forms.RoleAwareLoginForm's verification
    gate entirely by logging in directly at /admin/login/, which uses this
    separate form instead."""

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.email_verified:
            raise forms.ValidationError(
                "Please verify your email address before signing in.",
                code='email_unverified',
            )
