from django.contrib import messages as django_messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from tenants.decorators import role_required
from tenants.models import User

from .forms import MeetingForm, MessageForm, TaskCompleteForm, TaskForm, team_queryset
from .models import Meeting, Message, Task

# Who may hand out work. Matches how Approvals and HR already treat
# OWNER+MANAGER as the supervisory pair.
ASSIGNER_ROLES = ('OWNER', 'MANAGER')


def _tenant_user_or_404(request, user_id):
    """Fetch another person in the *requester's own* tenant.

    tenants.User is not a TenantModel, so nothing scopes this automatically --
    passing tenant= here is what stops a user id from another business being
    used to open a conversation or read someone else's details.
    """
    return get_object_or_404(User, pk=user_id, tenant=request.user.tenant)


# --------------------------------------------------------------------------
# My Work -- every role. Without this the CEO's actions would be write-only.
# --------------------------------------------------------------------------

@login_required
def my_work(request):
    user = request.user
    open_tasks = Task.objects.filter(
        assigned_to=user, status__in=Task.OPEN_STATUSES,
    ).select_related('assigned_by').order_by('due_date', '-created_at')
    recent_done = Task.objects.filter(assigned_to=user, status='done').order_by('-completed_at')[:5]

    upcoming_meetings = Meeting.objects.filter(
        attendees=user, status='scheduled', scheduled_for__gte=timezone.now(),
    ).order_by('scheduled_for')

    # One row per correspondent, newest message first.
    conversations = []
    partner_ids = set(
        Message.objects.filter(Q(sender=user) | Q(recipient=user))
        .values_list('sender_id', flat=True)
    ) | set(
        Message.objects.filter(Q(sender=user) | Q(recipient=user))
        .values_list('recipient_id', flat=True)
    )
    partner_ids.discard(user.pk)
    for partner in User.objects.filter(pk__in=partner_ids, tenant=user.tenant):
        thread = Message.conversation_between(user, partner)
        latest = thread.last()
        conversations.append({
            'partner': partner,
            'latest': latest,
            'unread': thread.filter(recipient=user, read_at__isnull=True).count(),
        })
    conversations.sort(key=lambda c: c['latest'].sent_at if c['latest'] else timezone.now(), reverse=True)

    return render(request, 'collaboration/my_work.html', {
        'open_tasks': open_tasks,
        'recent_done': recent_done,
        'upcoming_meetings': upcoming_meetings,
        'conversations': conversations,
        'unread_total': Message.unread_count_for(user),
        'can_assign': request.user.has_role(*ASSIGNER_ROLES),
    })


# --------------------------------------------------------------------------
# Tasks
# --------------------------------------------------------------------------

@role_required(*ASSIGNER_ROLES)
def task_list(request):
    tasks = Task.objects.select_related('assigned_to', 'assigned_by').order_by('status', 'due_date')
    return render(request, 'collaboration/task_list.html', {'tasks': tasks})


@role_required(*ASSIGNER_ROLES)
def task_create(request):
    initial = {}
    preset = request.GET.get('assigned_to')
    if preset:
        # Only pre-fills the form; the queryset and clean_assigned_to still
        # decide whether this person is actually assignable.
        initial['assigned_to'] = preset

    if request.method == 'POST':
        form = TaskForm(request.POST, tenant=request.user.tenant, actor=request.user)
        if form.is_valid():
            task = form.save(commit=False)
            task.tenant = request.user.tenant
            task.assigned_by = request.user
            task.save()
            django_messages.success(request, f'Task assigned to {task.assigned_to.username}.')
            return redirect('collaboration:task_list')
    else:
        form = TaskForm(initial=initial, tenant=request.user.tenant, actor=request.user)
    return render(request, 'collaboration/task_form.html', {'form': form, 'title': 'Assign Task'})


@login_required
def task_complete(request, pk):
    task = get_object_or_404(Task, pk=pk)
    # Only the person the work was given to can report it done -- a supervisor
    # marking someone else's task complete would make the record a fiction.
    if task.assigned_to_id != request.user.pk:
        raise PermissionDenied
    if request.method == 'POST':
        form = TaskCompleteForm(request.POST)
        if form.is_valid():
            task.complete(request.user, note=form.cleaned_data.get('completion_note', ''))
            django_messages.success(request, 'Task marked done.')
            return redirect('collaboration:my_work')
    else:
        form = TaskCompleteForm()
    return render(request, 'collaboration/task_complete.html', {'form': form, 'task': task})


@role_required(*ASSIGNER_ROLES)
def task_cancel(request, pk):
    task = get_object_or_404(Task, pk=pk)
    # A Manager may cancel what they assigned; the Owner may cancel anything.
    if task.assigned_by_id != request.user.pk and request.user.role != 'OWNER':
        raise PermissionDenied
    if request.method == 'POST':
        task.cancel(request.user, reason=request.POST.get('cancel_reason', '').strip())
        django_messages.success(request, 'Task cancelled.')
        return redirect('collaboration:task_list')
    return render(request, 'collaboration/task_cancel.html', {'task': task})


# --------------------------------------------------------------------------
# Meetings
# --------------------------------------------------------------------------

@role_required(*ASSIGNER_ROLES)
def meeting_list(request):
    meetings = Meeting.objects.select_related('called_by').prefetch_related('attendees')
    return render(request, 'collaboration/meeting_list.html', {'meetings': meetings})


@role_required(*ASSIGNER_ROLES)
def meeting_create(request):
    if request.method == 'POST':
        form = MeetingForm(request.POST, tenant=request.user.tenant, actor=request.user)
        if form.is_valid():
            meeting = form.save(commit=False)
            meeting.tenant = request.user.tenant
            meeting.called_by = request.user
            meeting.save()
            form.save_m2m()
            django_messages.success(request, f'Meeting "{meeting.title}" scheduled.')
            return redirect('collaboration:meeting_list')
    else:
        form = MeetingForm(tenant=request.user.tenant, actor=request.user)
    return render(request, 'collaboration/meeting_form.html', {'form': form, 'title': 'Call a Meeting'})


@role_required(*ASSIGNER_ROLES)
def meeting_cancel(request, pk):
    meeting = get_object_or_404(Meeting, pk=pk)
    if meeting.called_by_id != request.user.pk and request.user.role != 'OWNER':
        raise PermissionDenied
    if request.method == 'POST':
        meeting.cancel(request.user, reason=request.POST.get('cancel_reason', '').strip())
        django_messages.success(request, 'Meeting cancelled.')
        return redirect('collaboration:meeting_list')
    return render(request, 'collaboration/meeting_cancel.html', {'meeting': meeting})


# --------------------------------------------------------------------------
# Messaging (two-way, 1:1)
# --------------------------------------------------------------------------

@login_required
def conversation(request, user_id):
    partner = _tenant_user_or_404(request, user_id)
    if partner.pk == request.user.pk:
        raise PermissionDenied

    if request.method == 'POST':
        form = MessageForm(request.POST)
        if form.is_valid():
            message = form.save(commit=False)
            message.tenant = request.user.tenant
            message.sender = request.user
            message.recipient = partner
            message.save()
            return redirect('collaboration:conversation', user_id=partner.pk)
    else:
        form = MessageForm()

    thread = Message.conversation_between(request.user, partner)
    # Opening the thread is what marks their messages read.
    thread.filter(recipient=request.user, read_at__isnull=True).update(read_at=timezone.now())

    return render(request, 'collaboration/conversation.html', {
        'partner': partner,
        'thread': thread,
        'form': form,
    })


@login_required
def message_inbox(request):
    """Pick someone to message. Restricted to the requester's own tenant."""
    people = team_queryset(request.user.tenant, exclude_user=request.user, include_owners=True)
    rows = []
    for person in people:
        thread = Message.conversation_between(request.user, person)
        rows.append({
            'person': person,
            'latest': thread.last(),
            'unread': thread.filter(recipient=request.user, read_at__isnull=True).count(),
        })
    return render(request, 'collaboration/message_inbox.html', {'rows': rows})


# --------------------------------------------------------------------------
# Shared helper used by the CEO Dashboard
# --------------------------------------------------------------------------

def ceo_portal_context(request):
    """Portal data for dashboard.views.ceo_dashboard.

    Lives here so the models and their scoping rules stay in one app; the
    dashboard just renders what this returns.
    """
    tenant = request.user.tenant
    team = list(team_queryset(tenant, exclude_user=request.user).annotate(
        open_task_count=Count(
            'tasks_assigned_to_me',
            filter=Q(tasks_assigned_to_me__status__in=Task.OPEN_STATUSES),
            distinct=True,
        ),
    ))

    unread_by_sender = dict(
        Message.objects.filter(recipient=request.user, read_at__isnull=True)
        .values_list('sender_id')
        .annotate(n=Count('id'))
    )
    for member in team:
        member.unread_from_them = unread_by_sender.get(member.pk, 0)

    open_tasks = Task.objects.filter(
        status__in=Task.OPEN_STATUSES,
    ).select_related('assigned_to').order_by('due_date', '-created_at')[:10]

    upcoming_meetings = Meeting.objects.filter(
        status='scheduled', scheduled_for__gte=timezone.now(),
    ).prefetch_related('attendees').order_by('scheduled_for')[:5]

    return {
        'portal_team': team,
        'portal_open_tasks': open_tasks,
        'portal_open_task_count': Task.objects.filter(status__in=Task.OPEN_STATUSES).count(),
        'portal_overdue_count': Task.objects.filter(
            status__in=Task.OPEN_STATUSES, due_date__lt=timezone.localdate(),
        ).count(),
        'portal_upcoming_meetings': upcoming_meetings,
        'portal_unread_total': Message.unread_count_for(request.user),
    }
