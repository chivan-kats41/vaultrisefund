from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

User = get_user_model()


class CustomUserBackend(ModelBackend):
    """
    Authenticates against accounts.Accounts where USERNAME_FIELD = 'email'.

    login_view passes the email (or a phone-derived email) as the `username`
    keyword argument to authenticate(), so we look up by email here.
    We also support direct username (phone) lookup as a fallback so the
    Django admin still works.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None

        # 1. Try email lookup first (primary path — login_view always passes email)
        user = None
        try:
            user = User.objects.get(email__iexact=username)
        except User.DoesNotExist:
            pass

        # 2. Fallback: try username (phone) lookup — covers Django admin login
        if user is None:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                # Run set_password anyway to mitigate timing attacks
                User().set_password(password)
                return None

        # 3. Verify password and active status
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None