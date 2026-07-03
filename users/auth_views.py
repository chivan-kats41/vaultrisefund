"""
Authentication Views for User Registration, Login, and Logout
File: users/auth_views.py

UPDATED: Now uses EMAIL authentication to match accounts.Accounts model
USERNAME_FIELD = 'email'

Handles:
- User registration with email
- User login with email
- User logout
- Referral code tracking
- Referral relationship building (L1 / L2 / L3) — called AFTER referred_by is saved
"""

from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate, get_user_model
from django.contrib import messages
from django.db import transaction
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from decimal import Decimal
import re

from .models import UserProfile

User = get_user_model()


# ==================== VALIDATORS ====================

def validate_email(email):
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(email_regex, email) is not None


def validate_phone_number(phone):
    phone = phone.replace(' ', '').replace('-', '')
    if re.match(r'^\d{9,10}$', phone):
        return True
    return False


def format_phone_number(phone):
    phone = phone.replace(' ', '').replace('-', '')
    if phone.startswith('0'):
        phone = phone[1:]
    if not phone.startswith('256'):
        phone = '256' + phone
    return phone


# ==================== REFERRAL HELPER ====================

def _build_referral_relationships(user, referrer_profile):
    """
    Build L1 / L2 / L3 ReferralRelationship rows for a newly registered user.

    WHY THIS EXISTS
    ---------------
    The invitation/signals.py previously tried to do this inside a post_save
    signal on User. That signal fires immediately after create_user(), which
    is BEFORE register_view() sets profile.referred_by. So the signal always
    saw referred_by = None and created nothing.

    This function is called EXPLICITLY from register_view() AFTER
    profile.referred_by has been saved to the database, so the chain is
    always correct.

    Args:
        user             - the newly created auth User instance
        referrer_profile - the UserProfile of the person who shared their link
    """
    try:
        from invitation.models import ReferralRelationship
        from .models import Notification
    except ImportError as e:
        print(f"Could not import invitation models: {e}")
        return

    if not referrer_profile or not hasattr(referrer_profile, 'user'):
        return

    direct_referrer = referrer_profile.user

    # Level 1
    try:
        _, created_l1 = ReferralRelationship.objects.get_or_create(
            referrer=direct_referrer,
            referee=user,
            level=1,
            defaults={
                'is_active':               False,
                'total_purchases':         0,
                'total_purchase_amount':   Decimal('0.00'),
                'total_commission_earned': Decimal('0.00'),
            }
        )
        if created_l1:
            referrer_profile.total_referrals = (referrer_profile.total_referrals or 0) + 1
            referrer_profile.save(update_fields=['total_referrals'])

            Notification.objects.create(
                user=direct_referrer,
                title='New referral joined!',
                message=f'{user.nickname} registered using your invite link.',
                notification_type='referral',
                is_important=True,
            )
            print(f"L1 relationship created: {direct_referrer.username} -> {user.username}")
        else:
            print(f"L1 relationship already exists: {direct_referrer.username} -> {user.username}")

    except Exception as e:
        print(f"Error creating L1 relationship: {e}")
        import traceback
        traceback.print_exc()
        return  # don't attempt L2/L3 if L1 failed

    # Level 2
    l2_profile = referrer_profile.referred_by
    if not l2_profile or not hasattr(l2_profile, 'user'):
        return

    l2_user = l2_profile.user
    try:
        _, created_l2 = ReferralRelationship.objects.get_or_create(
            referrer=l2_user,
            referee=user,
            level=2,
            defaults={
                'is_active':               False,
                'total_purchases':         0,
                'total_purchase_amount':   Decimal('0.00'),
                'total_commission_earned': Decimal('0.00'),
            }
        )
        if created_l2:
            Notification.objects.create(
                user=l2_user,
                title='Level 2 network growth',
                message=f'{user.nickname} joined as your Level 2 referral.',
                notification_type='referral',
            )
            print(f"L2 relationship created: {l2_user.username} -> {user.username}")
        else:
            print(f"L2 relationship already exists: {l2_user.username} -> {user.username}")

    except Exception as e:
        print(f"Error creating L2 relationship: {e}")
        import traceback
        traceback.print_exc()
        return  # don't attempt L3 if L2 failed

    # Level 3
    l3_profile = l2_profile.referred_by
    if not l3_profile or not hasattr(l3_profile, 'user'):
        return

    l3_user = l3_profile.user
    try:
        _, created_l3 = ReferralRelationship.objects.get_or_create(
            referrer=l3_user,
            referee=user,
            level=3,
            defaults={
                'is_active':               False,
                'total_purchases':         0,
                'total_purchase_amount':   Decimal('0.00'),
                'total_commission_earned': Decimal('0.00'),
            }
        )
        if created_l3:
            Notification.objects.create(
                user=l3_user,
                title='Level 3 network growth',
                message=f'{user.nickname} joined as your Level 3 referral.',
                notification_type='referral',
            )
            print(f"L3 relationship created: {l3_user.username} -> {user.username}")
        else:
            print(f"L3 relationship already exists: {l3_user.username} -> {user.username}")

    except Exception as e:
        print(f"Error creating L3 relationship: {e}")
        import traceback
        traceback.print_exc()


# ==================== REGISTRATION ====================

@require_http_methods(["GET", "POST"])
def register_view(request):
    if request.user.is_authenticated:
        return redirect('account')

    if request.method == 'POST':
        phone           = request.POST.get('phone', '').strip()
        email           = request.POST.get('email', '').strip().lower()
        password        = request.POST.get('password', '').strip()
        nickname        = request.POST.get('nickname', '').strip()
        invitation_code = request.POST.get('invitation_code', '').strip()

        print("=" * 50)
        print("REGISTRATION DEBUG:")
        print(f"Phone:           {phone}")
        print(f"Email:           {email}")
        print(f"Nickname:        {nickname}")
        print(f"Invitation code: {invitation_code or '(none)'}")
        print("=" * 50)

        # Validation
        if not all([phone, email, password, nickname]):
            messages.error(request, 'All fields are required')
            return render(request, 'register.html')

        if not validate_email(email):
            messages.error(request, 'Invalid email format')
            return render(request, 'register.html')

        if not validate_phone_number(phone):
            messages.error(request, 'Invalid phone number format')
            return render(request, 'register.html')

        formatted_phone = format_phone_number(phone)

        if len(password) < 6:
            messages.error(request, 'Password must be at least 6 characters')
            return render(request, 'register.html')

        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered')
            return render(request, 'register.html')

        if User.objects.filter(username=formatted_phone).exists():
            messages.error(request, 'Phone number already registered')
            return render(request, 'register.html')

        try:
            with transaction.atomic():
                print(f"Creating user: email={email}, username={formatted_phone}")

                # ✅ Create User — nickname is now saved directly on the user
                # record (Accounts.nickname) as the single source of truth
                # for display, instead of being derived from first_name or
                # relying on UserProfile.nickname.
                user = User.objects.create_user(
                    username=formatted_phone,
                    email=email,
                    password=password,
                    first_name=nickname,
                    last_name='',
                    nickname=nickname,
                )
                print(f"User created: ID={user.pk}, Email={user.email}, Username={user.username}, Nickname={user.nickname}")
                print(f"Password check: {user.check_password(password)}")

                # Get or create profile
                # (post_save signal on User may have already created it)
                try:
                    profile = UserProfile.objects.get(user=user)
                    print("Profile already exists (created by signal)")
                except UserProfile.DoesNotExist:
                    profile = UserProfile.objects.create(user=user)
                    print("Profile created manually")

                # Kept in sync for any legacy code still reading profile.nickname,
                # but user.nickname (set above) is now the source of truth for display.
                profile.nickname     = nickname
                profile.phone_number = formatted_phone

                if not profile.referral_code:
                    profile.generate_referral_code()  # saves internally
                else:
                    profile.save()

                print(f"Profile saved: Nickname={profile.nickname}, Referral={profile.referral_code}")

                # ── Referral linking ──────────────────────────────────────
                #
                # KEY STEP ORDER:
                #   1. Find the referrer profile by invitation code
                #   2. Set profile.referred_by and SAVE it to the DB
                #   3. THEN call _build_referral_relationships()
                #
                # This order matters because _build_referral_relationships()
                # walks up the chain using referred_by fields, which must
                # already be in the database.
                #
                if invitation_code:
                    try:
                        referrer_profile = UserProfile.objects.get(referral_code=invitation_code)

                        # Step 1: persist the link
                        profile.referred_by = referrer_profile
                        profile.save(update_fields=['referred_by'])
                        print(f"referred_by set to: {referrer_profile.user.username}")

                        # Step 2: build L1/L2/L3 rows now that referred_by is in DB
                        _build_referral_relationships(user, referrer_profile)

                    except UserProfile.DoesNotExist:
                        print(f"Invalid referral code: {invitation_code}")
                        messages.warning(
                            request,
                            'Invalid invitation code, but account created successfully'
                        )

                # ✅ Do NOT auto-login after registration — send the user to
                # the login page instead so they sign in with the credentials
                # they just created, rather than landing straight on the
                # account page. (LOGIN_REDIRECT_URL only applies to the
                # login view itself, so this had to be changed here.)
                print("Account created — redirecting to login page")

                messages.success(
                    request,
                    f'Welcome {nickname}! Your account has been created successfully. '
                    f'Your registration ID is {user.registration_id}. '
                    f'Please log in to continue.'
                )
                return redirect('login')

        except Exception as e:
            print(f"Registration Error: {str(e)}")
            import traceback
            traceback.print_exc()
            messages.error(request, f'Registration failed: {str(e)}')
            return render(request, 'register.html')

    return render(request, 'register.html')


# ==================== LOGIN ====================

@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect('account')

    if request.method == 'POST':
        username_input = request.POST.get('username', '').strip()
        password       = request.POST.get('password', '').strip()

        print("=" * 50)
        print("LOGIN DEBUG:")
        print(f"Username input: {username_input}")
        print("=" * 50)

        if not username_input or not password:
            messages.error(request, 'Please enter both email/phone and password')
            return render(request, 'login.html')

        user_email = None

        if '@' in username_input:
            user_email = username_input.lower()
            print(f"Input detected as EMAIL: {user_email}")
        else:
            formatted_phone = format_phone_number(username_input)
            print(f"Input detected as PHONE: {formatted_phone}")
            try:
                user_obj   = User.objects.get(username=formatted_phone)
                user_email = user_obj.email
                print(f"Found user by phone, email: {user_email}")
            except User.DoesNotExist:
                print(f"User NOT found with phone: {formatted_phone}")
                messages.error(request, 'Invalid email/phone or password')
                return render(request, 'login.html')

        print(f"Authenticating with email: {user_email}")
        user = authenticate(request, username=user_email, password=password)
        print(f"Authentication result: {user}")

        if user is not None:
            print("Authentication successful")
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')

            try:
                profile = UserProfile.objects.get(user=user)
                profile.last_login_at = timezone.now()
                profile.save(update_fields=['last_login_at'])
                print("Profile updated: last_login_at")
            except UserProfile.DoesNotExist:
                profile = UserProfile.objects.create(user=user)
                profile.generate_referral_code()
                print("Profile created during login")

            # ✅ user.nickname is now the source of truth for display name
            display_name = user.nickname if user.nickname else user.username
            messages.success(request, f'Welcome back, {display_name}!')

            next_url = request.GET.get('next', 'account')
            print(f"Redirecting to: {next_url}")
            print("=" * 50)
            return redirect(next_url)

        else:
            print("Authentication FAILED")
            try:
                test_user      = User.objects.get(email=user_email)
                password_valid = test_user.check_password(password)
                print(f"Direct password check: {password_valid}")
                if not password_valid:
                    print("PASSWORD IS INCORRECT")
            except Exception as e:
                print(f"Error checking password: {e}")
            print("=" * 50)
            messages.error(request, 'Invalid email/phone or password')
            return render(request, 'login.html')

    return render(request, 'login.html')


# ==================== LOGOUT ====================

def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully')
    return redirect('login')


def register_redirect(request):
    return redirect('register', permanent=True)


def login_redirect(request):
    return redirect('login', permanent=True)