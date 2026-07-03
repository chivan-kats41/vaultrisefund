import random
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager


def generate_registration_id():
    """
    Generate a unique 6-digit registration ID (100000–999999).

    Retries on collision. 6 digits gives 900,000 possible values, so
    collisions are rare, but we check anyway to guarantee uniqueness.
    """
    while True:
        candidate = str(random.randint(100000, 999999))
        if not Accounts.objects.filter(registration_id=candidate).exists():
            return candidate


class MyAccountManager(BaseUserManager):
    def create_user(self, first_name, last_name, username, email, password=None, nickname=None):
        if not email:
            raise ValueError("Invalid user email address")
        if not username:
            raise ValueError("User must have a username")

        user = self.model(
            email      = self.normalize_email(email),
            username   = username,
            first_name = first_name,
            last_name  = last_name,
            # ✅ Falls back to first_name if no nickname was supplied at signup,
            # so there's always something friendly to display instead of username.
            nickname   = nickname or first_name,
            is_active  = True,          # ← was False (default), caused all site
                                        #   registrations to be locked out silently
            registration_id = generate_registration_id(),
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, first_name, last_name, username, email, password):
        user = self.create_user(
            email      = self.normalize_email(email),
            username   = username,
            first_name = first_name,
            last_name  = last_name,
            password   = password,
        )
        user.is_admin      = True
        user.is_staff      = True
        user.is_active     = True
        user.is_superadmin = True
        user.save(using=self._db)
        return user


class Accounts(AbstractBaseUser):
    first_name   = models.CharField(max_length=50)
    last_name    = models.CharField(max_length=50)
    username     = models.CharField(max_length=50, unique=True)
    email        = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=50, blank=True)

    # ✅ Display name shown across the site (homepage header, dashboards, etc.)
    # instead of the raw username. Not required to be unique — many users can
    # share a display nickname.
    nickname     = models.CharField(max_length=50, blank=True)

    # ✅ 6-digit registration/member ID shown to the user (e.g. "ID: 880661"),
    # distinct from the internal auto-increment primary key.
    registration_id = models.CharField(
        max_length=6, unique=True, blank=True, null=True,
        help_text="Unique 6-digit member/registration ID shown to the user."
    )

    date_joined   = models.DateTimeField(auto_now_add=True)
    last_login    = models.DateTimeField(auto_now_add=True)
    is_admin      = models.BooleanField(default=False)
    is_staff      = models.BooleanField(default=False)
    is_superadmin = models.BooleanField(default=False)
    is_active     = models.BooleanField(default=True)  # ← changed from False to True

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name', 'username']

    objects = MyAccountManager()

    class Meta:
        verbose_name        = 'Account'
        verbose_name_plural = 'Accounts'

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        # Safety net: guarantees every account has a registration_id even if
        # it was created some other way than MyAccountManager.create_user()
        # (e.g. bulk_create, a fixture, or a pre-existing row from before
        # this field existed).
        if not self.registration_id:
            self.registration_id = generate_registration_id()
        # ✅ Same safety net as registration_id: guarantees a nickname exists
        # even for accounts created via bulk_create, fixtures, or admin.
        if not self.nickname:
            self.nickname = self.first_name or f"User{self.registration_id or ''}"
        super().save(*args, **kwargs)

    def has_perm(self, perm, obj=None):
        return self.is_admin

    def has_module_perms(self, app_label):
        return True