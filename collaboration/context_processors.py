from django.db import DatabaseError


def unread_messages(request):
    """Unread direct-message count, available on every page for the nav badge.

    Without this a message only surfaces if the recipient happens to open My
    Work -- which is exactly how two real messages sat unread. One COUNT per
    render for signed-in users; anonymous pages (landing, login) skip it.

    Database errors are swallowed deliberately: a decorative nav badge must
    never be the reason a page 500s. Same reasoning as the DatabaseError
    guards in tenants.middleware.
    """
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {'nav_unread_messages': 0}

    try:
        from .models import Message
        return {'nav_unread_messages': Message.unread_count_for(user)}
    except DatabaseError:
        return {'nav_unread_messages': 0}
