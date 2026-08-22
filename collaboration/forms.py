from django import forms

from core.forms import NON_OWNER_ROLES
from tenants.models import User

from .models import Meeting, Message, Task


def team_queryset(tenant, exclude_user=None, include_owners=False):
    """Everyone in `tenant` who can be given work or messaged.

    tenants.User is NOT a TenantModel, so TenantManager does not scope it --
    the tenant filter here is the only thing keeping another business's staff
    out of these dropdowns, which is why it is never omitted.
    """
    if tenant is None:
        return User.objects.none()
    qs = User.objects.filter(tenant=tenant)
    if not include_owners:
        qs = qs.filter(role__in=list(NON_OWNER_ROLES))
    if exclude_user is not None:
        qs = qs.exclude(pk=exclude_user.pk)
    return qs.order_by('role', 'username')


class TenantScopedFormMixin:
    """Sets every people-picker's queryset per request rather than at class
    definition time.

    A queryset written in a field declaration or Meta is evaluated once at
    import, before any request exists, and that result is reused for the life
    of the process -- the exact bug fixed earlier in sales/inventory forms,
    where the dropdown silently offered (and accepted) every tenant's rows.
    """

    people_fields = ()

    def __init__(self, *args, tenant=None, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        self.actor = actor
        for name in self.people_fields:
            if name in self.fields:
                self.fields[name].queryset = team_queryset(tenant, exclude_user=actor)

    def _reject_foreign_users(self, users, field_name):
        """Second line of defence: even if a queryset were ever mis-set, a
        raw POST naming another tenant's user id must not get through."""
        for user in users:
            if user is not None and user.tenant_id != getattr(self.tenant, 'pk', None):
                self.add_error(field_name, 'That person is not part of your business.')
                return


class TaskForm(TenantScopedFormMixin, forms.ModelForm):
    people_fields = ('assigned_to',)

    class Meta:
        model = Task
        fields = ['title', 'description', 'assigned_to', 'due_date', 'priority']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Follow up on overdue invoices'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'What exactly needs doing?'}),
            'assigned_to': forms.Select(attrs={'class': 'form-select'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean_assigned_to(self):
        assignee = self.cleaned_data.get('assigned_to')
        self._reject_foreign_users([assignee], 'assigned_to')
        return assignee


class MeetingForm(TenantScopedFormMixin, forms.ModelForm):
    people_fields = ('attendees',)

    class Meta:
        model = Meeting
        fields = ['title', 'agenda', 'scheduled_for', 'location', 'attendees']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Monthly executive review'}),
            'agenda': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Points to cover'}),
            'scheduled_for': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Boardroom, or a meeting link'}),
            'attendees': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '8'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # datetime-local inputs only pre-fill from this exact format.
        self.fields['scheduled_for'].input_formats = ['%Y-%m-%dT%H:%M']

    def clean_attendees(self):
        attendees = self.cleaned_data.get('attendees')
        if attendees:
            self._reject_foreign_users(list(attendees), 'attendees')
        return attendees


class MessageForm(forms.ModelForm):
    """Only the body is submitted -- the recipient comes from the URL and is
    re-checked against the sender's tenant in the view, so it can never be
    supplied (or tampered with) through the form."""

    class Meta:
        model = Message
        fields = ['body']
        widgets = {
            'body': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3, 'placeholder': 'Write a message...',
            }),
        }

    def clean_body(self):
        body = self.cleaned_data.get('body', '').strip()
        if not body:
            raise forms.ValidationError('Message cannot be empty.')
        return body


class TaskCompleteForm(forms.Form):
    completion_note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Anything to report back? (optional)'}),
    )
