from django import forms
from django.contrib.auth import get_user_model
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


class RoleAwareLoginForm(AuthenticationForm):
    """Login form that also asks the user to declare their role.

    After the normal username/password check succeeds, the declared role
    must match the account's actual role (super admins are exempt, since
    they aren't tied to a single role). This catches, e.g., a cashier's
    login being used from the "Owner" option by mistake, and gives a clear
    error instead of silently granting/denying access.
    """
    role = forms.ChoiceField(choices=User.Role.choices)

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


class SignupForm(forms.Form):
    """Public signup: creates a new business (Tenant) plus its first
    account, which is always the Owner."""
    business_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. RealKuku'}))
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-control'}))
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
