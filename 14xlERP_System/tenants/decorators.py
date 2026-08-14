from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*allowed_roles):
    """Restrict a view to users whose .role is in allowed_roles.

    Super admins always pass. Usage:

        @role_required('OWNER', 'MANAGER')
        def some_view(request):
            ...

    For class-based views, wrap dispatch() instead:

        @method_decorator(role_required('OWNER', 'MANAGER'), name='dispatch')
        class SomeView(LoginRequiredMixin, ListView):
            ...
    """
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if request.user.has_role(*allowed_roles):
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return wrapped
    return decorator
