from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.utils.deprecation import MiddlewareMixin

# URL prefixes that stay reachable without being logged in.
# Django admin has its own separate login screen, so it's exempt here.
EXEMPT_PREFIXES = (
    '/login/',
    '/signup/',
    '/logout/',
    '/password-reset/',
    '/admin/',
    '/static/',
    '/media/',
)


class LoginRequiredMiddleware(MiddlewareMixin):
    """
    Requires a logged-in user for every page in the system except the
    ones listed in EXEMPT_PREFIXES above. Without this, any page in the
    app (dashboard, sales, inventory, accounting, etc.) is reachable by
    anyone who has the URL, logged in or not.
    """

    def process_request(self, request):
        path = request.path

        if any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES):
            return None

        if request.user.is_authenticated:
            return None

        return redirect_to_login(request.get_full_path(), login_url=settings.LOGIN_URL)
