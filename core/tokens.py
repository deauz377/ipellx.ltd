from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    """Signup email-verification links. Same HMAC/timestamp machinery as
    Django's own password-reset tokens, but never interchangeable with one:

    - `key_salt` is a distinct namespace, so a password-reset token can
      never validate here (and vice versa) even on a hash coincidence.
    - `email_verified` is part of the hashed value, not just checked
      separately. verify_email() flips it True as its side effect, which
      changes the hash `check_token()` recomputes -- so the token that was
      just used (and every other outstanding token for that user) fails
      immediately after, with no separate "used" flag to track.
    """
    key_salt = 'core.tokens.EmailVerificationTokenGenerator'

    def _make_hash_value(self, user, timestamp):
        return f'{user.pk}{user.password}{user.email_verified}{user.email}{timestamp}'

    def check_token(self, user, token):
        if user is not None and user.email_verified:
            return False
        return super().check_token(user, token)


email_verification_token = EmailVerificationTokenGenerator()
