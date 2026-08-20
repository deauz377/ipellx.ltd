from django.core.signals import request_finished
from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import TenantModel
from .middleware import get_current_tenant, _local


@receiver(pre_save)
def set_tenant(sender, instance, **kwargs):
    if isinstance(instance, TenantModel) and hasattr(instance, 'tenant') and not instance.tenant:
        tenant = get_current_tenant()
        if tenant:
            instance.tenant = tenant


@receiver(request_finished)
def clear_current_tenant(sender, **kwargs):
    """TenantMiddleware sets _local.tenant near the start of every request,
    but nothing previously cleared it once the request finished. On a
    thread-per-request-reuse server (gunicorn workers with --threads,
    Django's own test Client) that leaves the *previous* request's tenant
    sitting in this thread's storage until the *next* request's middleware
    overwrites it -- harmless for a normal request (middleware always runs
    first), but anything that touches a TenantModel queryset outside of the
    request/middleware cycle on that same thread (management commands,
    signal handlers, or -- concretely -- Django TestCase fixtures created in
    setUp() before any request has been made in that test) would silently
    inherit a stale tenant instead of getting the "no tenant" state a fresh
    thread would have. Resetting here removes that gap.
    """
    _local.tenant = None
    _local.is_super_admin = False