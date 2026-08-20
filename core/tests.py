from datetime import datetime, timedelta

from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .emails import send_verification_email
from .tokens import email_verification_token
from tenants.models import User
from tenants.tests import TEST_PASSWORD, create_tenant_and_owner


def verify_url(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    return reverse('core:verify_email', kwargs={'uidb64': uid, 'token': token}), token, uid


class AnonymousAccessDeniedTests(TestCase):
    """Part 19 #1-9: an anonymous visitor is redirected to login for every
    named protected area, enforced by core.middleware.LoginRequiredMiddleware
    (a blanket deny-by-default, not a per-view decorator that could be
    forgotten on a new page)."""

    def assert_login_required(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302, f'{url} did not redirect an anonymous request')
        self.assertIn(reverse('core:login'), response.url)

    def test_root_is_public_but_shows_no_tenant_data(self):
        # '/' is deliberately exempt (dashboard.views.overview branches on
        # request.user itself) -- confirm it renders the public landing
        # page for an anonymous visitor, not any business's dashboard data.
        response = self.client.get(reverse('dashboard_overview'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard/landing.html')

    def test_dashboard(self):
        self.assert_login_required(reverse('dashboard_search'))

    def test_sales(self):
        self.assert_login_required(reverse('sales:sales_overview'))

    def test_invoices(self):
        self.assert_login_required(reverse('sales:invoice_list'))

    def test_customers(self):
        self.assert_login_required(reverse('customers:customer_list'))

    def test_inventory(self):
        self.assert_login_required(reverse('inventory:inventory_overview'))

    def test_payments(self):
        self.assert_login_required(reverse('sales:payment_dashboard'))

    def test_accounting(self):
        self.assert_login_required(reverse('accounting:dashboard'))

    def test_payroll(self):
        self.assert_login_required(reverse('payroll:dashboard'))

    def test_reports(self):
        self.assert_login_required(reverse('sales:product_profit_report'))


@override_settings(REQUIRE_EMAIL_VERIFICATION=True)
class EmailVerificationLifecycleTests(TestCase):
    """Part 19 #10-17."""

    def setUp(self):
        self.tenant, self.user = create_tenant_and_owner('verify-lifecycle-test', username='verifyowner')
        self.user.email_verified = False
        self.user.save(update_fields=['email_verified'])

    def test_new_account_starts_unverified(self):
        self.assertFalse(self.user.email_verified)

    def test_verification_email_is_generated(self):
        mail.outbox = []
        sent = send_verification_email(self.user)
        self.assertTrue(sent)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Verify your iPellX account', mail.outbox[0].subject)
        self.assertIn(self.user.email, mail.outbox[0].to)

    def test_valid_token_verifies_and_redirects_to_login(self):
        url, _token, _uid = verify_url(self.user)
        response = self.client.get(url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)
        self.assertRedirects(response, reverse('core:login'))

    def test_invalid_token_fails(self):
        _url, _token, uid = verify_url(self.user)
        bad_url = reverse('core:verify_email', kwargs={'uidb64': uid, 'token': 'not-a-real-token'})
        response = self.client.get(bad_url)
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)
        self.assertRedirects(response, reverse('core:resend_verification'))

    def test_expired_token_fails(self):
        token = email_verification_token.make_token(self.user)
        original_now = email_verification_token._now
        try:
            # PasswordResetTokenGenerator._now() (which this subclasses) is
            # documented as naive local time, not timezone.now() -- mixing
            # the two here would TypeError inside _num_seconds().
            far_future = datetime.now() + timedelta(days=365)
            email_verification_token._now = lambda: far_future
            self.assertFalse(email_verification_token.check_token(self.user, token))
        finally:
            email_verification_token._now = original_now

    def test_used_token_cannot_be_reused(self):
        url, token, _uid = verify_url(self.user)
        self.client.get(url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)
        # email_verified flipping True changed the hash the token was built
        # from -- the exact same token, checked again, must now fail.
        self.assertFalse(email_verification_token.check_token(self.user, token))

    def test_unverified_user_cannot_access_erp(self):
        response = self.client.post(reverse('core:login'), {
            'username': 'verifyowner', 'password': TEST_PASSWORD, 'role': User.Role.OWNER,
        })
        self.assertEqual(response.status_code, 200)  # re-renders the login form, no redirect
        self.assertContains(response, 'Please verify your email address before signing in.')
        # And no session was actually established by the attempt.
        response2 = self.client.get(reverse('dashboard_search'))
        self.assertEqual(response2.status_code, 302)
        self.assertIn(reverse('core:login'), response2.url)

    def test_wrong_password_does_not_show_verification_message(self):
        """Proves the two failure modes stay distinguishable -- a wrong
        password must never be reported as an unverified-email problem."""
        response = self.client.post(reverse('core:login'), {
            'username': 'verifyowner', 'password': 'TotallyWrongPassword!', 'role': User.Role.OWNER,
        })
        self.assertNotContains(response, 'Please verify your email address before signing in.')

    def test_verified_user_can_log_in(self):
        self.user.email_verified = True
        self.user.save(update_fields=['email_verified'])
        response = self.client.post(reverse('core:login'), {
            'username': 'verifyowner', 'password': TEST_PASSWORD, 'role': User.Role.OWNER,
        }, follow=True)
        self.assertTemplateUsed(response, 'dashboard/overview.html')

    def test_resend_verification_sends_and_is_generic(self):
        mail.outbox = []
        response = self.client.post(reverse('core:resend_verification'), {'email': self.user.email}, follow=True)
        self.assertEqual(len(mail.outbox), 1)
        self.assertContains(response, "If an account exists")

        response2 = self.client.post(
            reverse('core:resend_verification'), {'email': 'no-such-account@example.com'}, follow=True,
        )
        self.assertContains(response2, "If an account exists")

    def test_resend_respects_cooldown(self):
        self.user.verification_sent_at = timezone.now()
        self.user.save(update_fields=['verification_sent_at'])
        mail.outbox = []
        self.client.post(reverse('core:resend_verification'), {'email': self.user.email})
        self.assertEqual(len(mail.outbox), 0)

    def test_resend_does_not_send_for_already_verified_account(self):
        self.user.email_verified = True
        self.user.save(update_fields=['email_verified'])
        mail.outbox = []
        self.client.post(reverse('core:resend_verification'), {'email': self.user.email})
        self.assertEqual(len(mail.outbox), 0)

    def test_signup_email_is_required(self):
        """Verification has nowhere to send a link without one -- signup
        must require email even though other account-creation paths
        (Owner-created team members) do not."""
        response = self.client.post(reverse('core:signup'), {
            'business_name': 'No Email Biz', 'username': 'noemailowner',
            'phone': '', 'password1': 'SomePass123!', 'password2': 'SomePass123!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='noemailowner').exists())


@override_settings(REQUIRE_EMAIL_VERIFICATION=True)
class SignupFlowTests(TestCase):
    def test_signup_does_not_auto_login_and_creates_unverified_owner(self):
        mail.outbox = []
        response = self.client.post(reverse('core:signup'), {
            'business_name': 'Fresh Signup Biz', 'username': 'freshsignupowner',
            'email': 'freshsignup@example.com', 'phone': '',
            'password1': 'FreshPass123!', 'password2': 'FreshPass123!',
        }, follow=True)
        self.assertRedirects(response, reverse('core:signup_check_email'))

        user = User.objects.get(username='freshsignupowner')
        self.assertFalse(user.email_verified)
        self.assertEqual(user.role, User.Role.OWNER)
        self.assertIsNotNone(user.tenant)
        self.assertEqual(len(mail.outbox), 1)

        # Confirm no session was established despite the account existing.
        response2 = self.client.get(reverse('dashboard_search'))
        self.assertEqual(response2.status_code, 302)

    def test_signup_is_atomic_no_orphaned_tenant_on_user_creation_failure(self):
        """Regression test for wrapping Tenant + User creation in
        transaction.atomic(): a failure creating the User must not leave
        the just-created Tenant behind with no owner."""
        from unittest.mock import patch
        from tenants.models import Tenant

        with patch('tenants.models.User.objects.create_user', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('core:signup'), {
                    'business_name': 'Orphan Risk Biz', 'username': 'orphanriskowner',
                    'email': 'orphanrisk@example.com', 'phone': '',
                    'password1': 'OrphanPass123!', 'password2': 'OrphanPass123!',
                })
        self.assertFalse(Tenant.objects.filter(name='Orphan Risk Biz').exists())


class PasswordResetLifecycleTests(TestCase):
    """Part 19 #18-25. Exercises the already-existing, already-wired Django
    PasswordResetView/Done/Confirm/Complete flow end to end."""

    def setUp(self):
        self.tenant, self.user = create_tenant_and_owner('reset-lifecycle-test', username='resetowner')

    def _confirm_get_url(self, user, token=None):
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = token or default_token_generator.make_token(user)
        return reverse('core:password_reset_confirm', kwargs={'uidb64': uid, 'token': token})

    def test_request_works_and_sends_email(self):
        mail.outbox = []
        response = self.client.post(reverse('core:password_reset'), {'email': self.user.email}, follow=True)
        self.assertRedirects(response, reverse('core:password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)

    def test_existing_and_nonexisting_email_get_identical_response(self):
        mail.outbox = []
        r1 = self.client.post(reverse('core:password_reset'), {'email': self.user.email}, follow=True)
        r2 = self.client.post(reverse('core:password_reset'), {'email': 'nobody-here@example.com'}, follow=True)
        self.assertEqual(r1.status_code, r2.status_code)
        self.assertEqual(r1.redirect_chain, r2.redirect_chain)
        # Only the real account actually got an email.
        self.assertEqual(len(mail.outbox), 1)

    def test_valid_token_resets_password(self):
        response = self.client.get(self._confirm_get_url(self.user), follow=True)
        set_password_url = response.request['PATH_INFO']
        response2 = self.client.post(set_password_url, {
            'new_password1': 'BrandNewPass456!', 'new_password2': 'BrandNewPass456!',
        }, follow=True)
        self.assertRedirects(response2, reverse('core:password_reset_complete'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('BrandNewPass456!'))

    def test_invalid_token_fails(self):
        response = self.client.get(self._confirm_get_url(self.user, token='not-a-real-token'), follow=True)
        self.assertContains(response, 'invalid or has already been used')

    def test_expired_token_fails(self):
        token = default_token_generator.make_token(self.user)
        original_now = default_token_generator._now
        try:
            far_future = datetime.now() + timedelta(days=365)
            default_token_generator._now = lambda: far_future
            self.assertFalse(default_token_generator.check_token(self.user, token))
        finally:
            default_token_generator._now = original_now

    def test_reset_token_cannot_be_reused(self):
        token = default_token_generator.make_token(self.user)
        response = self.client.get(self._confirm_get_url(self.user, token=token), follow=True)
        set_password_url = response.request['PATH_INFO']
        self.client.post(set_password_url, {
            'new_password1': 'FirstNewPass789!', 'new_password2': 'FirstNewPass789!',
        })
        # Password hash changed -> the original token, checked fresh, now fails.
        self.user.refresh_from_db()
        self.assertFalse(default_token_generator.check_token(self.user, token))

    def test_old_password_stops_working_new_password_works(self):
        self.assertTrue(self.user.check_password(TEST_PASSWORD))
        response = self.client.get(self._confirm_get_url(self.user), follow=True)
        set_password_url = response.request['PATH_INFO']
        self.client.post(set_password_url, {
            'new_password1': 'FreshPass000!', 'new_password2': 'FreshPass000!',
        })
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password(TEST_PASSWORD))
        self.assertTrue(self.user.check_password('FreshPass000!'))


class SessionSecurityTests(TestCase):
    """Part 19 #43-46."""

    def setUp(self):
        self.tenant, self.user = create_tenant_and_owner('session-security-test', username='sessionowner')

    def test_logout_invalidates_session(self):
        self.client.login(username='sessionowner', password=TEST_PASSWORD)
        self.assertEqual(self.client.get(reverse('dashboard_search')).status_code, 200)
        # LogoutView only accepts POST (Django 5+) -- a GET would 405 and
        # leave the session untouched, which is exactly the bug this test
        # exists to catch, so it has to use the same method the real
        # logout form in auth_base.html uses.
        self.client.post(reverse('core:logout'))
        response = self.client.get(reverse('dashboard_search'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('core:login'), response.url)

    def test_user_b_has_an_independent_session_from_user_a(self):
        _tenant_b, _user_b = create_tenant_and_owner('session-security-b-test', username='sessionowner_b')
        client_a, client_b = Client(), Client()
        client_a.login(username='sessionowner', password=TEST_PASSWORD)
        client_b.login(username='sessionowner_b', password=TEST_PASSWORD)
        self.assertNotEqual(
            client_a.cookies['sessionid'].value, client_b.cookies['sessionid'].value,
        )
        self.assertEqual(client_a.get(reverse('dashboard_search')).status_code, 200)
        self.assertEqual(client_b.get(reverse('dashboard_search')).status_code, 200)

    def test_password_reset_invalidates_other_sessions(self):
        device1, device2 = Client(), Client()
        device1.login(username='sessionowner', password=TEST_PASSWORD)
        device2.login(username='sessionowner', password=TEST_PASSWORD)
        self.assertEqual(device1.get(reverse('dashboard_search')).status_code, 200)
        self.assertEqual(device2.get(reverse('dashboard_search')).status_code, 200)

        # Reset via Django's own flow, from an unrelated (logged-out) client --
        # unlike account_settings' self-service password change, this flow
        # never calls update_session_auth_hash, so every session's stored
        # auth hash goes stale against the new password hash.
        #
        # The reset token's hash includes user.last_login -- refresh from DB
        # first, since device1/device2's logins just updated it there and a
        # token built from the stale in-memory value would fail validation.
        self.user.refresh_from_db()
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        confirm_url = reverse('core:password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
        anon = Client()
        response = anon.get(confirm_url, follow=True)
        set_password_url = response.request['PATH_INFO']
        anon.post(set_password_url, {
            'new_password1': 'PostResetPass111!', 'new_password2': 'PostResetPass111!',
        })

        self.assertEqual(device1.get(reverse('dashboard_search')).status_code, 302)
        self.assertEqual(device2.get(reverse('dashboard_search')).status_code, 302)


class CronAuthTests(TestCase):
    """Authentication for the Vercel Cron endpoints (core.cron_auth).

    The secret used here is a throwaway test literal -- the real one only
    ever exists in the hosting platform's environment variables.
    """

    TEST_SECRET = 'test-only-cron-secret'

    def setUp(self):
        from django.test import RequestFactory
        self.factory = RequestFactory()

    def _request(self, authorization=None):
        headers = {} if authorization is None else {'Authorization': authorization}
        return self.factory.get('/cron/send-payment-reminders/', headers=headers)

    def _check(self, authorization=None):
        from .cron_auth import cron_request_is_authorised
        return cron_request_is_authorised(self._request(authorization))

    def test_correct_secret_is_accepted(self):
        with self.settings(CRON_SECRET=self.TEST_SECRET):
            self.assertTrue(self._check(f'Bearer {self.TEST_SECRET}'))

    def test_wrong_secret_is_rejected(self):
        with self.settings(CRON_SECRET=self.TEST_SECRET):
            self.assertFalse(self._check('Bearer not-the-right-secret'))

    def test_missing_header_is_rejected(self):
        with self.settings(CRON_SECRET=self.TEST_SECRET):
            self.assertFalse(self._check(None))

    def test_bare_secret_without_bearer_prefix_is_rejected(self):
        with self.settings(CRON_SECRET=self.TEST_SECRET):
            self.assertFalse(self._check(self.TEST_SECRET))

    def test_unset_secret_fails_closed(self):
        """A deployment that forgot the variable must refuse every caller,
        not accept them all."""
        with self.settings(CRON_SECRET=''):
            self.assertFalse(self._check('Bearer '))
            self.assertFalse(self._check(None))
            self.assertFalse(self._check('Bearer anything'))

    def test_whitespace_padded_header_still_authenticates(self):
        """Intermediaries can pad a header value; that must not look like a
        wrong secret. This is robustness, not a substitute for storing the
        variable without whitespace -- Vercel rejects the build outright
        when the stored value has any."""
        with self.settings(CRON_SECRET=self.TEST_SECRET):
            self.assertTrue(self._check(f'  Bearer {self.TEST_SECRET}  '))

    def test_non_ascii_header_is_rejected_without_raising(self):
        """hmac.compare_digest raises TypeError on non-ASCII str, which a
        caller could otherwise use to turn a failed check into a 500."""
        with self.settings(CRON_SECRET=self.TEST_SECRET):
            self.assertFalse(self._check('Bearer ünïcödé'))

    def test_endpoint_refuses_and_never_echoes_the_secret(self):
        with self.settings(CRON_SECRET=self.TEST_SECRET):
            response = self.client.get(
                reverse('cron_send_payment_reminders'),
                headers={'Authorization': 'Bearer wrong'},
            )
            self.assertEqual(response.status_code, 403)
            self.assertNotIn(self.TEST_SECRET, response.content.decode())

    def test_migrate_endpoint_refuses_unauthenticated_callers(self):
        with self.settings(CRON_SECRET=self.TEST_SECRET):
            response = self.client.get(reverse('admin_run_migrations'))
            self.assertEqual(response.status_code, 403)
            self.assertNotIn(self.TEST_SECRET, response.content.decode())


@override_settings(REQUIRE_EMAIL_VERIFICATION=False)
class VerificationPausedTests(TestCase):
    """Default configuration: verification switched off, because with no SMTP
    configured the mail goes to the console backend and a customer would be
    left with an account they can never log into."""

    def test_signup_logs_straight_in_and_sends_no_email(self):
        mail.outbox = []
        response = self.client.post(reverse('core:signup'), {
            'business_name': 'Paused Verification Biz', 'username': 'pausedowner',
            'email': 'paused@example.com', 'phone': '',
            'password1': 'PausedPass123!', 'password2': 'PausedPass123!',
        }, follow=True)
        self.assertTemplateUsed(response, 'dashboard/overview.html')
        self.assertEqual(len(mail.outbox), 0)

        user = User.objects.get(username='pausedowner')
        self.assertTrue(user.email_verified)
        self.assertEqual(user.role, User.Role.OWNER)
        self.assertIsNotNone(user.tenant)

    def test_new_account_can_log_in_immediately(self):
        self.client.post(reverse('core:signup'), {
            'business_name': 'Paused Login Biz', 'username': 'pausedlogin',
            'email': 'pausedlogin@example.com', 'phone': '',
            'password1': 'PausedPass123!', 'password2': 'PausedPass123!',
        })
        self.client.logout()
        response = self.client.post(reverse('core:login'), {
            'username': 'pausedlogin', 'password': 'PausedPass123!', 'role': User.Role.OWNER,
        }, follow=True)
        self.assertTemplateUsed(response, 'dashboard/overview.html')

    def test_account_left_unverified_from_before_is_not_blocked(self):
        """Turning the flag off must also un-block accounts created while it
        was on, otherwise pausing would strand exactly the users it is meant
        to rescue."""
        tenant, user = create_tenant_and_owner('paused-unblock-test', username='strandedowner')
        user.email_verified = False
        user.save(update_fields=['email_verified'])

        response = self.client.post(reverse('core:login'), {
            'username': 'strandedowner', 'password': TEST_PASSWORD, 'role': User.Role.OWNER,
        }, follow=True)
        self.assertTemplateUsed(response, 'dashboard/overview.html')
