from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from tenants.models import User
from tenants.tests import TEST_PASSWORD, TwoTenantTestCase

from .models import Meeting, Message, Task


def make_member(tenant, username, role=User.Role.STAFF):
    return User.objects.create_user(
        username=username, password=TEST_PASSWORD, tenant=tenant,
        role=role, email_verified=True,
    )


class PortalTestCase(TwoTenantTestCase):
    """Two tenants, each with an Owner plus staff."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.staff_a = make_member(cls.tenant_a, 'staff_a_portal')
        cls.staff_b = make_member(cls.tenant_b, 'staff_b_portal')
        cls.manager_a = make_member(cls.tenant_a, 'manager_a_portal', role=User.Role.MANAGER)

    def login_staff_a(self):
        self.client.login(username='staff_a_portal', password=TEST_PASSWORD)


class TaskWorkflowTests(PortalTestCase):
    """The loop that makes this functional: CEO assigns -> member sees it in
    My Work -> member completes -> it reflects back on the CEO Dashboard."""

    def test_assign_appears_in_my_work_and_completes(self):
        self.login_a()
        response = self.client.post(reverse('collaboration:task_create'), {
            'title': 'Chase overdue invoices', 'description': 'Top 5 debtors',
            'assigned_to': self.staff_a.pk, 'due_date': '', 'priority': 'high',
        })
        self.assertEqual(response.status_code, 302)
        task = Task.objects.get(title='Chase overdue invoices')
        self.assertEqual(task.assigned_to, self.staff_a)
        self.assertEqual(task.assigned_by, self.user_a)
        self.assertEqual(task.tenant, self.tenant_a)
        self.assertEqual(task.status, 'pending')

        self.client.logout()
        self.login_staff_a()
        my_work = self.client.get(reverse('collaboration:my_work'))
        self.assertContains(my_work, 'Chase overdue invoices')

        done = self.client.post(
            reverse('collaboration:task_complete', kwargs={'pk': task.pk}),
            {'completion_note': 'All five called.'},
        )
        self.assertEqual(done.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, 'done')
        self.assertIsNotNone(task.completed_at)
        self.assertEqual(task.completion_note, 'All five called.')

        self.client.logout()
        self.login_a()
        ceo = self.client.get(reverse('ceo_dashboard'))
        self.assertEqual(ceo.context['portal_open_task_count'], 0)

    def test_overdue_flag(self):
        task = Task.objects.create(
            tenant=self.tenant_a, title='Late', assigned_to=self.staff_a,
            assigned_by=self.user_a, due_date=timezone.localdate() - timedelta(days=2),
        )
        self.assertTrue(task.is_overdue)
        task.complete(self.staff_a)
        self.assertFalse(task.is_overdue, 'a finished task is not overdue')

    def test_only_the_assignee_can_complete(self):
        task = Task.objects.create(
            tenant=self.tenant_a, title='Not yours',
            assigned_to=self.staff_a, assigned_by=self.user_a,
        )
        # Even the Owner who assigned it cannot report it done for someone else.
        self.login_a()
        response = self.client.post(
            reverse('collaboration:task_complete', kwargs={'pk': task.pk}), {},
        )
        self.assertEqual(response.status_code, 403)
        task.refresh_from_db()
        self.assertEqual(task.status, 'pending')

    def test_staff_cannot_assign_tasks(self):
        self.login_staff_a()
        self.assertEqual(self.client.get(reverse('collaboration:task_create')).status_code, 403)
        self.assertEqual(self.client.get(reverse('collaboration:task_list')).status_code, 403)

    def test_manager_can_assign(self):
        self.client.login(username='manager_a_portal', password=TEST_PASSWORD)
        self.assertEqual(self.client.get(reverse('collaboration:task_create')).status_code, 200)

    def test_my_work_is_open_to_every_role(self):
        self.login_staff_a()
        self.assertEqual(self.client.get(reverse('collaboration:my_work')).status_code, 200)

    def test_empty_state_is_safe(self):
        self.login_staff_a()
        response = self.client.get(reverse('collaboration:my_work'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nothing assigned to you')


class TaskTenantIsolationTests(PortalTestCase):
    """tenants.User is not a TenantModel, so nothing scopes it implicitly --
    these guards are the only thing preventing cross-business assignment."""

    def test_cannot_assign_to_another_tenants_user_by_raw_post(self):
        self.login_a()
        response = self.client.post(reverse('collaboration:task_create'), {
            'title': 'Cross tenant', 'description': '',
            'assigned_to': self.staff_b.pk, 'due_date': '', 'priority': 'normal',
        })
        self.assertEqual(response.status_code, 200)  # redisplayed with errors
        self.assertFalse(Task.objects.filter(title='Cross tenant').exists())

    def test_dropdown_never_lists_another_tenants_user(self):
        self.login_a()
        response = self.client.get(reverse('collaboration:task_create'))
        choices = response.context['form'].fields['assigned_to'].queryset
        self.assertIn(self.staff_a, choices)
        self.assertNotIn(self.staff_b, choices)

    def test_cannot_see_or_cancel_another_tenants_task(self):
        task_b = Task.objects.create(
            tenant=self.tenant_b, title='B task',
            assigned_to=self.staff_b, assigned_by=self.user_b,
        )
        self.login_a()
        self.assertNotContains(self.client.get(reverse('collaboration:task_list')), 'B task')
        self.assertEqual(
            self.client.post(reverse('collaboration:task_cancel', kwargs={'pk': task_b.pk})).status_code,
            404,
        )
        task_b.refresh_from_db()
        self.assertEqual(task_b.status, 'pending')

    def test_ceo_dashboard_counts_exclude_other_tenants(self):
        Task.objects.create(
            tenant=self.tenant_b, title='B open',
            assigned_to=self.staff_b, assigned_by=self.user_b,
        )
        self.login_a()
        response = self.client.get(reverse('ceo_dashboard'))
        self.assertEqual(response.context['portal_open_task_count'], 0)


class MeetingTests(PortalTestCase):
    def test_call_meeting_with_attendees(self):
        self.login_a()
        when = (timezone.now() + timedelta(days=2)).strftime('%Y-%m-%dT%H:%M')
        response = self.client.post(reverse('collaboration:meeting_create'), {
            'title': 'Exec review', 'agenda': 'Q3 numbers', 'scheduled_for': when,
            'location': 'Boardroom', 'attendees': [self.staff_a.pk],
        })
        self.assertEqual(response.status_code, 302)
        meeting = Meeting.objects.get(title='Exec review')
        self.assertEqual(meeting.tenant, self.tenant_a)
        self.assertEqual(meeting.called_by, self.user_a)
        self.assertIn(self.staff_a, meeting.attendees.all())

        self.client.logout()
        self.login_staff_a()
        self.assertContains(self.client.get(reverse('collaboration:my_work')), 'Exec review')

    def test_cannot_invite_another_tenants_user(self):
        self.login_a()
        when = (timezone.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
        response = self.client.post(reverse('collaboration:meeting_create'), {
            'title': 'Leaky meeting', 'agenda': '', 'scheduled_for': when,
            'location': '', 'attendees': [self.staff_b.pk],
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Meeting.objects.filter(title='Leaky meeting').exists())

    def test_staff_cannot_call_meetings(self):
        self.login_staff_a()
        self.assertEqual(self.client.get(reverse('collaboration:meeting_create')).status_code, 403)

    def test_cancel_meeting(self):
        meeting = Meeting.objects.create(
            tenant=self.tenant_a, title='Scrap this',
            scheduled_for=timezone.now() + timedelta(days=1), called_by=self.user_a,
        )
        self.login_a()
        response = self.client.post(
            reverse('collaboration:meeting_cancel', kwargs={'pk': meeting.pk}),
            {'cancel_reason': 'Clash'},
        )
        self.assertEqual(response.status_code, 302)
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, 'cancelled')
        self.assertEqual(meeting.cancel_reason, 'Clash')
        self.assertFalse(meeting.is_upcoming)


class MessagingTests(PortalTestCase):
    def test_two_way_conversation_and_unread_counts(self):
        self.login_a()
        self.client.post(
            reverse('collaboration:conversation', kwargs={'user_id': self.staff_a.pk}),
            {'body': 'Can you handle the Nakuru delivery?'},
        )
        sent = Message.objects.get(sender=self.user_a, recipient=self.staff_a)
        self.assertEqual(sent.tenant, self.tenant_a)
        self.assertTrue(sent.is_unread)
        self.assertEqual(Message.unread_count_for(self.staff_a), 1)

        # Opening the thread is what marks it read.
        self.client.logout()
        self.login_staff_a()
        thread = self.client.get(
            reverse('collaboration:conversation', kwargs={'user_id': self.user_a.pk}),
        )
        self.assertContains(thread, 'Nakuru delivery')
        sent.refresh_from_db()
        self.assertFalse(sent.is_unread)
        self.assertEqual(Message.unread_count_for(self.staff_a), 0)

        self.client.post(
            reverse('collaboration:conversation', kwargs={'user_id': self.user_a.pk}),
            {'body': 'Yes, leaving now.'},
        )
        self.assertEqual(Message.unread_count_for(self.user_a), 1)
        self.assertEqual(Message.conversation_between(self.user_a, self.staff_a).count(), 2)

    def test_cannot_open_conversation_with_another_tenants_user(self):
        self.login_a()
        response = self.client.get(
            reverse('collaboration:conversation', kwargs={'user_id': self.staff_b.pk}),
        )
        self.assertEqual(response.status_code, 404)

    def test_cannot_message_yourself(self):
        self.login_a()
        response = self.client.get(
            reverse('collaboration:conversation', kwargs={'user_id': self.user_a.pk}),
        )
        self.assertEqual(response.status_code, 403)

    def test_third_party_cannot_read_someone_elses_thread(self):
        """A conversation only ever renders messages between the requester and
        the person named in the URL, so another pair's messages are unreachable."""
        Message.objects.create(
            tenant=self.tenant_a, sender=self.user_a,
            recipient=self.manager_a, body='Private to manager',
        )
        self.login_staff_a()
        response = self.client.get(
            reverse('collaboration:conversation', kwargs={'user_id': self.user_a.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Private to manager')

    def test_empty_message_rejected(self):
        self.login_a()
        self.client.post(
            reverse('collaboration:conversation', kwargs={'user_id': self.staff_a.pk}),
            {'body': '   '},
        )
        self.assertEqual(Message.objects.count(), 0)

    def test_inbox_lists_only_own_tenant(self):
        self.login_a()
        response = self.client.get(reverse('collaboration:message_inbox'))
        self.assertContains(response, 'staff_a_portal')
        self.assertNotContains(response, 'staff_b_portal')


class CeoDashboardPortalTests(PortalTestCase):
    def test_portal_sections_render_for_owner(self):
        self.login_a()
        response = self.client.get(reverse('ceo_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CEO Portal')
        self.assertContains(response, 'staff_a_portal')

    def test_roster_excludes_self_and_other_tenants(self):
        self.login_a()
        roster = self.client.get(reverse('ceo_dashboard')).context['portal_team']
        usernames = {m.username for m in roster}
        self.assertIn('staff_a_portal', usernames)
        self.assertIn('manager_a_portal', usernames)
        self.assertNotIn('owner_a', usernames)
        self.assertNotIn('staff_b_portal', usernames)


class UnreadBadgeTests(PortalTestCase):
    """The nav badge exists because two real messages sat unread -- nothing
    told the recipient anything had arrived."""

    def test_badge_count_appears_on_any_page_and_clears_when_read(self):
        Message.objects.create(
            tenant=self.tenant_a, sender=self.user_a,
            recipient=self.manager_a, body='Please review the stock budget.',
        )
        self.client.login(username='manager_a_portal', password=TEST_PASSWORD)

        # Visible from an unrelated page, not just the messaging screens.
        anywhere = self.client.get(reverse('dashboard_overview'))
        self.assertEqual(anywhere.context['nav_unread_messages'], 1)

        # Opening the thread clears it.
        self.client.get(reverse('collaboration:conversation', kwargs={'user_id': self.user_a.pk}))
        after = self.client.get(reverse('dashboard_overview'))
        self.assertEqual(after.context['nav_unread_messages'], 0)

    def test_badge_counts_only_your_own_unread(self):
        Message.objects.create(
            tenant=self.tenant_a, sender=self.user_a,
            recipient=self.manager_a, body='For the manager only',
        )
        self.login_staff_a()
        response = self.client.get(reverse('dashboard_overview'))
        self.assertEqual(response.context['nav_unread_messages'], 0)

    def test_badge_is_zero_for_anonymous_visitors(self):
        response = self.client.get(reverse('dashboard_overview'))
        self.assertEqual(response.context['nav_unread_messages'], 0)

    def test_message_to_a_lookalike_account_in_another_business_is_not_delivered(self):
        """Guards the exact confusion that prompted this: two businesses each
        had a similarly-named manager, and a message sent to one was looked
        for while signed in as the other."""
        lookalike = make_member(self.tenant_b, 'manager_a_portalz', role=User.Role.MANAGER)
        Message.objects.create(
            tenant=self.tenant_a, sender=self.user_a,
            recipient=self.manager_a, body='Intended for business A',
        )
        self.assertEqual(Message.unread_count_for(self.manager_a), 1)
        self.assertEqual(Message.unread_count_for(lookalike), 0)
