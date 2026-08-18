from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash, login
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone
from datetime import timedelta
from django.utils.text import slugify

from .forms import UsernameChangeForm, StyledPasswordChangeForm, SignupForm
from tenants.models import Tenant, User, SubscriptionPlan, SubscriptionPayment

TRIAL_DAYS = 14


def admin_run_migrations(request):
    """Ops endpoint: applies pending Django migrations against whichever
    database this deployment is already configured for. Exists because
    Vercel's serverless runtime has no shell access -- this deployment's
    own environment already holds DATABASE_URL (it uses it for every
    normal request), so triggering `migrate` here means that credential
    never has to leave Vercel's dashboard or get typed/pasted anywhere
    else. Guarded by CRON_SECRET (same secret as the reminder cron
    endpoint) via a Bearer header -- migrate is idempotent, so repeat
    calls are harmless, but a leaked secret would let someone re-trigger
    it at will, which is why this isn't left unauthenticated."""
    expected = f'Bearer {settings.CRON_SECRET}'
    if not settings.CRON_SECRET or request.headers.get('Authorization') != expected:
        return HttpResponseForbidden('Invalid or missing secret')

    from io import StringIO
    from django.core.management import call_command

    output = StringIO()
    try:
        call_command('migrate', interactive=False, stdout=output, stderr=output)
    except Exception as exc:
        return JsonResponse({'ok': False, 'output': output.getvalue(), 'error': str(exc)}, status=500)
    return JsonResponse({'ok': True, 'output': output.getvalue()})


def signup(request):
    if request.user.is_authenticated:
        return redirect('dashboard_overview')

    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            base_subdomain = slugify(data['business_name'])[:80] or 'business'
            subdomain = base_subdomain
            suffix = 1
            while Tenant.objects.filter(subdomain=subdomain).exists():
                suffix += 1
                subdomain = f"{base_subdomain}-{suffix}"

            tenant = Tenant.objects.create(
                name=data['business_name'],
                subdomain=subdomain,
                phone=data['phone'],
                paid_until=timezone.now() + timedelta(days=TRIAL_DAYS),
                on_trial=True,
            )
            user = User.objects.create_user(
                username=data['username'],
                email=data['email'],
                password=data['password1'],
                tenant=tenant,
                role=User.Role.OWNER,
            )
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(
                request,
                f"Welcome to {tenant.name}! Your {TRIAL_DAYS}-day free trial has started.",
            )
            return redirect('dashboard_overview')
    else:
        form = SignupForm()
    return render(request, 'core/signup.html', {'form': form, 'trial_days': TRIAL_DAYS})


@login_required
def subscribe(request):
    tenant = request.user.tenant
    plans = SubscriptionPlan.objects.filter(is_active=True).order_by('price_kes')
    recent_payments = SubscriptionPayment.objects.filter(tenant=tenant).order_by('-submitted_at')[:5]

    if request.method == 'POST':
        plan = get_object_or_404(SubscriptionPlan, pk=request.POST.get('plan_id'), is_active=True)
        reference = request.POST.get('reference', '').strip()
        if not reference:
            messages.error(request, 'Please enter the M-Pesa (or other payment) transaction code.')
        else:
            SubscriptionPayment.objects.create(
                tenant=tenant, plan=plan, reference=reference, amount=plan.price_kes,
                submitted_by=request.user,
            )
            messages.success(
                request,
                'Payment submitted for review. Your access will extend as soon as it\'s approved.',
            )
            return redirect('core:subscribe')

    context = {
        'tenant': tenant,
        'plans': plans,
        'recent_payments': recent_payments,
        'days_left': (tenant.paid_until - timezone.now()).days if tenant.paid_until else None,
    }
    return render(request, 'core/subscribe.html', context)


@login_required
def account_settings(request):
    username_form = UsernameChangeForm(instance=request.user)
    password_form = StyledPasswordChangeForm(user=request.user)

    if request.method == 'POST':
        if 'update_username' in request.POST:
            username_form = UsernameChangeForm(request.POST, instance=request.user)
            if username_form.is_valid():
                username_form.save()
                messages.success(request, 'Username updated successfully.')
                return redirect('core:account_settings')

        elif 'update_password' in request.POST:
            password_form = StyledPasswordChangeForm(user=request.user, data=request.POST)
            if password_form.is_valid():
                user = password_form.save()
                # Keeps the user logged in after changing their own password,
                # instead of the session being invalidated and forcing a re-login.
                update_session_auth_hash(request, user)
                messages.success(request, 'Password updated successfully.')
                return redirect('core:account_settings')

    return render(request, 'core/account_settings.html', {
        'username_form': username_form,
        'password_form': password_form,
    })
