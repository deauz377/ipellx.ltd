from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from tenants.models import Tenant

User = get_user_model()


class UsernameChangeForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
        }


class StyledPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
        # PasswordChangeForm doesn't set this by default (unlike
        # UserCreationForm) -- account_settings.html already renders
        # new_password1.help_text, so this is what makes that show anything.
        self.fields['new_password1'].help_text = password_validation.password_validators_help_text_html()


class RoleAwareLoginForm(AuthenticationForm):
    """Login form that also asks the user to declare their role.

    After the normal username/password check succeeds, the declared role
    must match the account's actual role (super admins are exempt, since
    they aren't tied to a single role). This catches, e.g., a cashier's
    login being used from the "Owner" option by mistake, and gives a clear
    error instead of silently granting/denying access.
    """
    role = forms.ChoiceField(choices=User.Role.choices)

    def confirm_login_allowed(self, user):
        # Runs inside AuthenticationForm.clean(), right after username/password
        # verify successfully and before the role check below -- this is
        # what lets a correct-password-but-unverified login show a distinct,
        # actionable message instead of Django's generic "invalid login"
        # (which is what happens if verification is gated via is_active
        # instead: ModelBackend filters inactive users out of authenticate()
        # before user_cache is ever set, so a custom message here would never
        # be reached). super() first preserves Django's own is_active check.
        super().confirm_login_allowed(user)
        if settings.REQUIRE_EMAIL_VERIFICATION and not user.email_verified:
            raise forms.ValidationError(
                "Please verify your email address before signing in.",
                code='email_unverified',
            )

    def clean(self):
        cleaned_data = super().clean()
        user = getattr(self, 'user_cache', None)
        role = cleaned_data.get('role')
        if user is not None and role and not user.is_super_admin and user.role != role:
            raise forms.ValidationError(
                "That account isn't registered as %(role)s. Check your role and try again.",
                code='role_mismatch',
                params={'role': dict(User.Role.choices).get(role, role)},
            )
        return cleaned_data


NON_OWNER_ROLES = (
    User.Role.MANAGER, User.Role.ACCOUNTANT, User.Role.SALES_STAFF,
    User.Role.INVENTORY_MANAGER, User.Role.STAFF,
)


class TeamMemberCreationForm(forms.Form):
    """Owner-only: creates a non-Owner login within the Owner's own
    tenant. Deliberately excludes Role.OWNER from the choices -- User.save()
    grants Django admin superuser access whenever role is set to OWNER, so
    that option must never be selectable here."""
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    role = forms.ChoiceField(
        choices=[(role, role.label) for role in NON_OWNER_ROLES],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    password2 = forms.CharField(label='Confirm password', widget=forms.PasswordInput(attrs={'class': 'form-control'}))

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('That username is already taken. Usernames must be unique across the whole platform.')
        return username

    def clean_role(self):
        role = self.cleaned_data['role']
        if role not in NON_OWNER_ROLES:
            raise forms.ValidationError('Invalid role.')
        return role

    def clean(self):
        cleaned_data = super().clean()
        p1, p2 = cleaned_data.get('password1'), cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Passwords don't match.")
        if p1 and len(p1) < 8:
            raise forms.ValidationError("Password must be at least 8 characters.")
        return cleaned_data


class ResendVerificationForm(forms.Form):
    """Deliberately has nothing to validate beyond 'is this a well-formed
    email' -- core.views.resend_verification() looks the address up itself
    and always responds the same way whether or not an account exists, so
    there is nothing here for a clean_email() to safely report back."""
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'you@example.com'}))


class SignupForm(forms.Form):
    """Public signup: creates a new business (Tenant) plus its first
    account, which is always the Owner."""
    business_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. RealKuku'}))
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control'}))
    # Required (unlike core.views.add_team_member's internal team accounts,
    # which can go without one) -- signup's new email-verification step has
    # nowhere to send a link without it.
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))
    phone = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    password2 = forms.CharField(label='Confirm password', widget=forms.PasswordInput(attrs={'class': 'form-control'}))

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('That username is already taken. Usernames must be unique across the whole platform — try adding your business name, e.g. "peter_bidiiauto".')
        return username

    def clean_business_name(self):
        name = self.cleaned_data['business_name']
        if Tenant.objects.filter(name__iexact=name).exists():
            raise forms.ValidationError('A business with that name is already registered.')
        return name

    def clean(self):
        cleaned_data = super().clean()
        p1, p2 = cleaned_data.get('password1'), cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Passwords don't match.")
        if p1 and len(p1) < 8:
            raise forms.ValidationError("Password must be at least 8 characters.")
        return cleaned_data
