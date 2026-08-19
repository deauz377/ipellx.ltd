import threading
from django.db import DatabaseError
from django.utils.deprecation import MiddlewareMixin

_local = threading.local()


def get_current_tenant():
    return getattr(_local, 'tenant', None)


def is_super_admin():
    return getattr(_local, 'is_super_admin', False)


class TenantMiddleware(MiddlewareMixin):
    def process_request(self, request):
        from .models import Tenant  # Import here to avoid circular import

        # A logged-in user's own tenant is the source of truth for which
        # business's data they see — this matters as soon as more than one
        # business shares the same deployed URL (no per-client subdomain).
        # Subdomain-based resolution below is only a fallback for requests
        # where we don't yet know who's asking (login page, signup, etc.).
        if hasattr(request, 'user') and request.user.is_authenticated and request.user.tenant_id:
            try:
                tenant = request.user.tenant
            except (Tenant.DoesNotExist, DatabaseError):
                # Same reasoning as the anonymous branch below: a DB hiccup
                # or a tenant_id pointing at a since-deleted row must not
                # take the whole request down for every logged-in user.
                _local.tenant = None
                _local.is_super_admin = False
                request.tenant = None
                return
            _local.tenant = tenant
            _local.is_super_admin = bool(request.user.is_super_admin)
            request.tenant = tenant
            return

        # Get tenant from subdomain (used for anonymous/pre-login requests)
        host = request.get_host().split(':')[0]  # Remove port
        subdomain = host.split('.')[0] if '.' in host else None

        if subdomain and subdomain != '127' and subdomain != 'localhost':
            try:
                tenant = Tenant.objects.get(subdomain=subdomain)
                _local.tenant = tenant
                _local.is_super_admin = False
                request.tenant = tenant
            except Tenant.DoesNotExist:
                # Handle invalid tenant
                _local.tenant = None
                _local.is_super_admin = False
                request.tenant = None
            except DatabaseError:
                # A lapsed connection, paused DB, or missing table would
                # otherwise take down every anonymous request site-wide
                # (this lookup runs before login on every page, including
                # the landing page). Degrade to "no tenant" instead of a
                # hard 500 so at least the public/login pages stay up.
                _local.tenant = None
                _local.is_super_admin = False
                request.tenant = None
        else:
            # Default to 'default' tenant for localhost or no subdomain
            try:
                tenant = Tenant.objects.get(subdomain='default')
                _local.tenant = tenant
                _local.is_super_admin = False
                request.tenant = tenant
            except Tenant.DoesNotExist:
                _local.tenant = None
                _local.is_super_admin = False
                request.tenant = None
            except DatabaseError:
                _local.tenant = None
                _local.is_super_admin = False
                request.tenant = None

        # For super admin, allow access to all
        if hasattr(request, 'user') and request.user.is_authenticated and request.user.is_super_admin:
            _local.is_super_admin = True

class SubscriptionGateMiddleware(MiddlewareMixin):
    """Blocks access once a tenant's trial/subscription has lapsed,
    redirecting to the Subscribe page instead. Platform-level super admins
    (is_super_admin=True) are never gated — they need access to review and
    approve other businesses' payments."""

    ALLOWED_PATH_PREFIXES = (
        '/subscribe', '/logout', '/login', '/signup', '/static', '/media', '/admin',
    )

    def process_request(self, request):
        if not (hasattr(request, 'user') and request.user.is_authenticated):
            return None
        if request.user.is_super_admin:
            return None
        if any(request.path.startswith(p) for p in self.ALLOWED_PATH_PREFIXES):
            return None

        from .models import Tenant
        try:
            tenant = request.user.tenant
        except (Tenant.DoesNotExist, DatabaseError):
            # Same reasoning as TenantMiddleware: this runs on every
            # authenticated request to a non-exempt path, so a DB hiccup
            # or a stale tenant_id here must not take the whole site down
            # for every logged-in visitor. Let the request through rather
            # than gate on a subscription state we failed to read.
            return None
        if tenant is None:
            return None

        from django.utils import timezone
        if tenant.paid_until and tenant.paid_until >= timezone.now():
            return None

        from django.shortcuts import redirect
        from django.contrib import messages
        messages.warning(request, "Your free trial or subscription has ended. Subscribe to keep using the system.")
        return redirect('core:subscribe')
