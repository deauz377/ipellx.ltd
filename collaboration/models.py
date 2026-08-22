from django.db import models
from django.db.models import Q
from django.utils import timezone

from tenants.models import TenantModel

# Roles a task can be assigned to / a meeting can invite / a message can reach.
# Everyone in the tenant except the person acting -- deliberately wider than
# dashboard.views.team_activity's [MANAGER, STAFF] filter, which silently drops
# Accountants, Sales Staff and Inventory Managers even though the Owner can
# create them and would expect to be able to give them work.


class Task(TenantModel):
    """Work the CEO (or a Manager) assigns to one team member."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    OPEN_STATUSES = ('pending', 'in_progress')

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    assigned_to = models.ForeignKey(
        'tenants.User', on_delete=models.CASCADE, related_name='tasks_assigned_to_me',
    )
    assigned_by = models.ForeignKey(
        'tenants.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tasks_i_assigned',
    )
    due_date = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    completed_at = models.DateTimeField(null=True, blank=True)
    completion_note = models.TextField(blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} -> {self.assigned_to}'

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    @property
    def is_overdue(self):
        return bool(self.due_date and self.is_open and self.due_date < timezone.localdate())

    def complete(self, user, note=''):
        """Mark done. Encapsulated here rather than written inline in the view
        (HR's style) because both the task list and My Work trigger it --
        follows tenants.models.SubscriptionPayment.approve()'s precedent."""
        self.status = 'done'
        self.completed_at = timezone.now()
        self.completion_note = note
        self.save(update_fields=['status', 'completed_at', 'completion_note', 'updated_at'])

    def cancel(self, user, reason=''):
        self.status = 'cancelled'
        self.cancel_reason = reason
        self.save(update_fields=['status', 'cancel_reason', 'updated_at'])


class Meeting(TenantModel):
    """An executive meeting called by the CEO or a Manager."""

    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('held', 'Held'),
        ('cancelled', 'Cancelled'),
    ]

    title = models.CharField(max_length=200)
    agenda = models.TextField(blank=True)
    scheduled_for = models.DateTimeField()
    location = models.CharField(max_length=200, blank=True, help_text='Room, or a video call link.')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    called_by = models.ForeignKey(
        'tenants.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='meetings_i_called',
    )
    attendees = models.ManyToManyField(
        'tenants.User', blank=True, related_name='meetings_invited_to',
    )
    cancel_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['scheduled_for']

    def __str__(self):
        return f'{self.title} ({self.scheduled_for:%d %b %Y %H:%M})'

    @property
    def is_upcoming(self):
        return self.status == 'scheduled' and self.scheduled_for >= timezone.now()

    def cancel(self, user, reason=''):
        self.status = 'cancelled'
        self.cancel_reason = reason
        self.save(update_fields=['status', 'cancel_reason', 'updated_at'])


class Message(TenantModel):
    """One direct message between two people in the same business.

    There is deliberately no Thread model: a conversation is simply every
    Message between two users ordered by sent_at (see `conversation_between`),
    which is all a 1:1 thread needs and one fewer table to keep consistent.
    """

    KIND_CHOICES = [
        ('chat', 'Message'),
        ('report', 'Report'),
    ]

    # A report is still a Message -- same delivery, same unread badge, same
    # thread -- but carries a subject and renders as a titled card rather than
    # a chat bubble, so a formal submission to the CEO is not buried in banter.
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default='chat')
    subject = models.CharField(max_length=150, blank=True)
    sender = models.ForeignKey(
        'tenants.User', on_delete=models.CASCADE, related_name='messages_sent',
    )
    recipient = models.ForeignKey(
        'tenants.User', on_delete=models.CASCADE, related_name='messages_received',
    )
    body = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['sent_at']

    def __str__(self):
        return f'{self.sender} -> {self.recipient}'

    @property
    def is_unread(self):
        return self.read_at is None

    @property
    def is_report(self):
        return self.kind == 'report'

    def mark_read(self):
        if self.read_at is None:
            self.read_at = timezone.now()
            self.save(update_fields=['read_at'])

    @classmethod
    def conversation_between(cls, user_a, user_b):
        return cls.objects.filter(
            Q(sender=user_a, recipient=user_b) | Q(sender=user_b, recipient=user_a)
        ).select_related('sender', 'recipient')

    @classmethod
    def unread_count_for(cls, user):
        return cls.objects.filter(recipient=user, read_at__isnull=True).count()
