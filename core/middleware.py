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
    # Safaricom's servers POST the STK Push result here directly -- there is
    # no logged-in user on the other end of that request.
    '/sales/mpesa/callback/',
    # The customer-facing payment page -- secured by an unguessable token
    # in the URL itself, not a login. The customer paying an invoice was
    # never asked to have an account here at all.
    '/pay/',
    # Vercel Cron calls these directly; they check CRON_SECRET themselves
    # rather than relying on a logged-in user (there isn't one).
    '/cron/',
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

        # Exact match, not startswith — every path starts with "/", so a
        # prefix rule here would exempt the entire site. Root is public so
        # logged-out visitors see the landing page instead of a login wall;
        # dashboard.views.overview() branches on request.user itself to
        # decide which one to render.
        if path == '/':
            return None

        if any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES):
            return None

        if request.user.is_authenticated:
            return None

        return redirect_to_login(request.get_full_path(), login_url=settings.LOGIN_URL)


class NoCacheMiddleware(MiddlewareMixin):
    """
    Marks every response as private and not cacheable, except the static
    assets WhiteNoise serves. Without this, Django (and this project sets
    no Cache-Control anywhere else) leaves responses free for any shared
    cache or proxy sitting in front of the app -- browser, corporate
    network, mobile carrier, CDN -- to store and hand back to a different
    visitor. Every other page here renders per-user/per-tenant data, so
    "cacheable" and "shareable" are never correct for it: a page built for
    one logged-in session must never be reusable for the next request that
    happens to hit the same URL without going through login first.
    """

    def process_response(self, request, response):
        if request.path.startswith('/static/') or request.path.startswith('/media/'):
            return response

        response['Cache-Control'] = 'private, no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        return response
