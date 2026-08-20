"""Shared authentication for the Vercel Cron endpoints.

Kept in one module so there is a single implementation to audit rather
than two copies in different apps drifting apart.
"""
import hmac

from django.conf import settings


def cron_request_is_authorised(request):
    """True only when the request carries exactly the Bearer credential
    Vercel Cron sends.

    - Fails closed when CRON_SECRET is unset, so a deployment that forgot
      the variable refuses every caller instead of accepting all of them.
    - Compares in constant time (hmac.compare_digest). The previous `!=`
      comparison short-circuits on the first differing byte, so response
      timing leaked how much of the secret a caller had guessed.
    - Compares bytes rather than str: compare_digest raises TypeError on
      non-ASCII str, which a caller could otherwise trigger deliberately
      to turn a failed auth check into a 500.
    - Strips the incoming header because intermediaries may pad the value;
      settings.CRON_SECRET is stripped at load for the same reason. Neither
      is a substitute for setting the variable cleanly in the hosting
      dashboard -- Vercel rejects the whole build if the stored value has
      surrounding whitespace, because it sends it as an HTTP header.

    The secret is never logged or echoed; callers return a generic refusal.
    """
    expected_secret = settings.CRON_SECRET
    if not expected_secret:
        return False

    provided = request.headers.get('Authorization', '').strip()
    expected = f'Bearer {expected_secret}'
    return hmac.compare_digest(provided.encode('utf-8'), expected.encode('utf-8'))
