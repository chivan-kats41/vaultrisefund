"""
Signal Handlers for Users App
File: users/signals.py

Handles:
- Automatic UserProfile creation/update when User is created/saved
- Withdrawal status change notifications (approved / rejected)
- Balance refund when withdrawal is rejected
- Transaction status sync when withdrawal status changes
- Referral bonus tracking

IMPORTANT: Must be imported in apps.py for signals to work!

    class UsersConfig(AppConfig):
        default_auto_field = 'django.db.models.BigAutoField'
        name = 'users'

        def ready(self):
            import users.signals
"""

from django.db.models.signals import post_save, pre_save, pre_delete
from django.dispatch import receiver
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone

from .models import UserProfile, Withdrawal, Transaction, Notification

User = get_user_model()


# ==============================================================================
# USER PROFILE SIGNALS
# ==============================================================================

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Automatically create UserProfile when a new User is created.

    Triggered when:
    - A new user registers
    - A user is created via admin
    - A user is created programmatically

    Safety checks:
    - Only runs for newly created users (created=True)
    - Checks if instance has a valid primary key
    - Prevents duplicate profile creation
    """
    if not created:
        return

    if not instance or not instance.pk:
        print(f"⚠️ Warning: User instance invalid or no PK: {instance}")
        return

    if not instance.is_authenticated:
        print(f"⚠️ Warning: Attempting to create profile for AnonymousUser")
        return

    try:
        if hasattr(instance, 'profile'):
            print(f"ℹ️ Profile already exists for user: {instance.username}")
            return

        profile = UserProfile.objects.create(user=instance)
        profile.generate_referral_code()
        print(f"✅ Profile created for user: {instance.username} (ID: {instance.pk})")

    except Exception as e:
        print(f"❌ Error creating profile for {instance.username}: {str(e)}")
        import traceback
        traceback.print_exc()


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_user_profile(sender, instance, **kwargs):
    """
    Save UserProfile when User is saved.
    Creates the profile if it doesn't exist yet.
    """
    if not instance or not instance.pk:
        return

    if not instance.is_authenticated:
        return

    try:
        if hasattr(instance, 'profile'):
            instance.profile.save()
        else:
            profile = UserProfile.objects.create(user=instance)
            profile.generate_referral_code()
            print(f"ℹ️ Profile created during save for user: {instance.username}")

    except UserProfile.DoesNotExist:
        try:
            profile = UserProfile.objects.create(user=instance)
            profile.generate_referral_code()
            print(f"ℹ️ Profile created (DoesNotExist) for user: {instance.username}")
        except Exception as e:
            print(f"❌ Error creating profile during save: {str(e)}")

    except Exception as e:
        print(f"⚠️ Error saving profile for {instance.username}: {str(e)}")


@receiver(pre_delete, sender=settings.AUTH_USER_MODEL)
def delete_user_profile(sender, instance, **kwargs):
    """
    Log when a user is deleted. Profile is handled by CASCADE automatically.
    Add any custom cleanup logic here if needed.
    """
    try:
        if hasattr(instance, 'profile'):
            print(f"ℹ️ User {instance.username} being deleted — profile will cascade delete")
    except Exception as e:
        print(f"⚠️ Error during user deletion: {str(e)}")


# ==============================================================================
# WITHDRAWAL STATUS CHANGE SIGNAL
# ==============================================================================

@receiver(pre_save, sender=Withdrawal)
def handle_withdrawal_status_change(sender, instance, **kwargs):
    """
    Fires BEFORE a Withdrawal is saved.

    Detects when an admin changes the withdrawal status and:

    ── On COMPLETED ──────────────────────────────────────────────────────────
    • Sends an in-app notification to the user (approved)
    • Sends a confirmation email to the user
    • Marks the linked Transaction as 'completed'

    ── On REJECTED ───────────────────────────────────────────────────────────
    • Refunds the full withdrawal amount back to withdrawal_balance
    • Sends an in-app notification to the user (rejected + reason)
    • Sends a rejection email to the user
    • Marks the linked Transaction as 'failed'

    ── On PROCESSING ─────────────────────────────────────────────────────────
    • Sends an in-app notification so the user knows it is being handled

    NOTE: Balance was already deducted when the request was submitted
    (in api_withdrawal_apply), so we only refund on rejection.
    """

    # Skip brand-new objects (no pk yet means no previous state to compare)
    if not instance.pk:
        return

    # Fetch the current (old) state from the database
    try:
        old = Withdrawal.objects.get(pk=instance.pk)
    except Withdrawal.DoesNotExist:
        return

    # Nothing changed — nothing to do
    if old.status == instance.status:
        return

    new_status = instance.status
    user       = instance.user

    print(
        f"ℹ️ Withdrawal {instance.withdrawal_number}: "
        f"{old.status} → {new_status} for {user.username}"
    )

    # ── COMPLETED (admin approved) ─────────────────────────────────────────
    if new_status == 'completed':
        _notify_withdrawal_completed(instance, user)

    # ── REJECTED (admin rejected) ──────────────────────────────────────────
    elif new_status == 'rejected':
        _refund_withdrawal(instance, user)
        _notify_withdrawal_rejected(instance, user)

    # ── PROCESSING (admin started processing) ─────────────────────────────
    elif new_status == 'processing':
        _notify_withdrawal_processing(instance, user)

    # ── Sync the linked Transaction record status ──────────────────────────
    _sync_transaction_status(instance, new_status)


# ------------------------------------------------------------------------------
# Private helpers for handle_withdrawal_status_change
# ------------------------------------------------------------------------------

def _notify_withdrawal_completed(withdrawal, user):
    """In-app + email notification when withdrawal is approved and paid out."""

    # In-app
    Notification.objects.create(
        user=user,
        title='Withdrawal Approved ✅',
        message=(
            f'Your withdrawal of UGX {withdrawal.amount:,.2f} has been approved. '
            f'UGX {withdrawal.net_amount:,.2f} has been sent to '
            f'{withdrawal.destination_wallet_type} '
            f'({withdrawal.destination_account} — {withdrawal.destination_name}). '
            f'Ref: {withdrawal.withdrawal_number}'
        ),
        notification_type='withdrawal_approved',
        is_important=True,
    )

    # Email
    if user.email:
        try:
            send_mail(
                subject='Your Withdrawal Has Been Processed — Agnicoe Eagle',
                message=(
                    f'Hello {user.username},\n\n'
                    f'Great news! Your withdrawal has been processed successfully.\n\n'
                    f'Amount Requested: UGX {withdrawal.amount:,.2f}\n'
                    f'Fee (10%%):         UGX {withdrawal.withdrawal_fee:,.2f}\n'
                    f'Amount Sent:      UGX {withdrawal.net_amount:,.2f}\n'
                    f'Sent To:          {withdrawal.destination_wallet_type} — '
                    f'{withdrawal.destination_account} ({withdrawal.destination_name})\n'
                    f'Reference:        {withdrawal.withdrawal_number}\n\n'
                    f'If you have any questions, please contact support.\n\n'
                    f'— Agnicoe Eagle Support'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
            print(f"✅ Withdrawal approval email sent to {user.email}")
        except Exception as e:
            print(f"❌ Failed to send withdrawal approval email: {e}")


def _refund_withdrawal(withdrawal, user):
    """
    Refund the full withdrawal amount back to the user's withdrawal_balance.
    Called only when status changes to 'rejected'.
    """
    try:
        profile = user.profile
        balance_before              = profile.withdrawal_balance
        profile.withdrawal_balance += withdrawal.amount

        # Also reverse the total_withdrawn counter so stats stay accurate
        profile.total_withdrawn = max(
            profile.total_withdrawn - withdrawal.amount, 0
        )
        profile.save()

        print(
            f"✅ Refunded UGX {withdrawal.amount:,.2f} to {user.username}. "
            f"New withdrawal_balance: {profile.withdrawal_balance:,.2f}"
        )

        # Record the refund as a transaction for the audit trail
        from uuid import uuid4
        Transaction.objects.create(
            user=user,
            transaction_number=(
                f"TXN{timezone.now().strftime('%Y%m%d%H%M%S')}"
                f"{uuid4().hex[:6].upper()}"
            ),
            transaction_type='system_deduction',   # reuse existing type; description clarifies
            amount=withdrawal.amount,               # positive = credit back
            balance_type='withdrawal_balance',
            balance_before=balance_before,
            balance_after=profile.withdrawal_balance,
            description=(
                f'Refund for rejected withdrawal — {withdrawal.withdrawal_number}. '
                f'Reason: {withdrawal.rejection_reason or "Not specified"}'
            ),
            reference_id=withdrawal.withdrawal_number,
            status='completed',
        )

    except Exception as e:
        print(f"❌ Error refunding withdrawal {withdrawal.withdrawal_number}: {e}")
        import traceback
        traceback.print_exc()


def _notify_withdrawal_rejected(withdrawal, user):
    """In-app + email notification when withdrawal is rejected."""
    reason = withdrawal.rejection_reason or 'No reason provided'

    # In-app
    Notification.objects.create(
        user=user,
        title='Withdrawal Rejected ❌',
        message=(
            f'Your withdrawal request of UGX {withdrawal.amount:,.2f} was rejected. '
            f'Reason: {reason}. '
            f'UGX {withdrawal.amount:,.2f} has been refunded to your withdrawal balance. '
            f'Ref: {withdrawal.withdrawal_number}'
        ),
        notification_type='withdrawal_rejected',
        is_important=True,
    )

    # Email
    if user.email:
        try:
            send_mail(
                subject='Your Withdrawal Request Was Rejected — Agnicoe Eagle',
                message=(
                    f'Hello {user.username},\n\n'
                    f'Unfortunately your withdrawal request has been rejected.\n\n'
                    f'Amount:    UGX {withdrawal.amount:,.2f}\n'
                    f'Reference: {withdrawal.withdrawal_number}\n'
                    f'Reason:    {reason}\n\n'
                    f'The full amount of UGX {withdrawal.amount:,.2f} has been '
                    f'returned to your withdrawal balance.\n\n'
                    f'If you believe this is an error, please contact support.\n\n'
                    f'— Agnicoe Eagle Support'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
            print(f"✅ Withdrawal rejection email sent to {user.email}")
        except Exception as e:
            print(f"❌ Failed to send withdrawal rejection email: {e}")


def _notify_withdrawal_processing(withdrawal, user):
    """In-app notification when withdrawal moves to 'processing'."""
    Notification.objects.create(
        user=user,
        title='Withdrawal Being Processed 🔄',
        message=(
            f'Your withdrawal of UGX {withdrawal.amount:,.2f} is now being processed. '
            f'You will receive UGX {withdrawal.net_amount:,.2f} shortly. '
            f'Ref: {withdrawal.withdrawal_number}'
        ),
        notification_type='system',
        is_important=False,
    )


def _sync_transaction_status(withdrawal, new_status):
    """
    Keep the Transaction record in sync with the Withdrawal status.

    Mapping:
        pending    → pending
        processing → pending   (still in-flight)
        completed  → completed
        rejected   → failed
        cancelled  → failed
    """
    status_map = {
        'pending':    'pending',
        'processing': 'pending',
        'completed':  'completed',
        'rejected':   'failed',
        'cancelled':  'failed',
    }
    tx_status = status_map.get(new_status)
    if not tx_status:
        return

    try:
        Transaction.objects.filter(
            reference_id=withdrawal.withdrawal_number,
            transaction_type='withdrawal',
        ).update(status=tx_status)
        print(
            f"✅ Transaction for {withdrawal.withdrawal_number} "
            f"synced to status: {tx_status}"
        )
    except Exception as e:
        print(f"⚠️ Could not sync transaction status for {withdrawal.withdrawal_number}: {e}")


# ==============================================================================
# REFERRAL SIGNALS
# ==============================================================================

@receiver(post_save, sender=UserProfile)
def handle_referral_bonus(sender, instance, created, **kwargs):
    """
    Handle referral bonuses when a new profile is created with a referrer.

    Uncomment the bonus block below to activate referral rewards.
    """
    if created and instance.referred_by:
        try:
            referrer = instance.referred_by

            # ── Uncomment to activate referral bonus ──────────────────────
            # from decimal import Decimal
            # bonus_amount = Decimal('5000.00')   # UGX 5,000
            # referrer.commission_balance += bonus_amount
            # referrer.referral_earnings  += bonus_amount
            # referrer.save()
            #
            # Notification.objects.create(
            #     user=referrer.user,
            #     title='Referral Bonus Received 🎉',
            #     message=(
            #         f'{instance.user.username} joined using your referral code! '
            #         f'You earned UGX {bonus_amount:,.2f}.'
            #     ),
            #     notification_type='referral',
            #     is_important=True,
            # )
            # ─────────────────────────────────────────────────────────────

            print(
                f"✅ Referral tracked: {instance.user.username} "
                f"referred by {referrer.user.username}"
            )

        except Exception as e:
            print(f"❌ Error processing referral bonus: {e}")


# ==============================================================================
# UTILITY / MANAGEMENT HELPERS
# ==============================================================================

def test_signals():
    """
    Verify signals are registered and database is consistent.
    Run in Django shell:
        from users.signals import test_signals; test_signals()
    """
    print("\n" + "=" * 50)
    print("TESTING USER SIGNALS")
    print("=" * 50 + "\n")

    print(f"✓ User model: {User}")
    print(f"✓ User model name: {User.__name__}")
    print(f"✓ UserProfile model imported successfully")
    print(f"✓ Withdrawal model imported successfully")
    print(f"✓ Signals registered for: {settings.AUTH_USER_MODEL}")

    total_users    = User.objects.count()
    total_profiles = UserProfile.objects.count()
    print(f"\n📊 Database Stats:")
    print(f"   Total Users:    {total_users}")
    print(f"   Total Profiles: {total_profiles}")

    if total_users != total_profiles:
        print(f"\n⚠️  {total_users - total_profiles} users without profiles!")
        print("   Run: from users.signals import create_missing_profiles")
        print("        create_missing_profiles()")
    else:
        print("\n✅ All users have profiles!")

    pending = Withdrawal.objects.filter(status='pending').count()
    print(f"\n   Pending Withdrawals: {pending}")
    print("\n" + "=" * 50)


def create_missing_profiles():
    """
    Create profiles for any users that don't have one.
    Run in Django shell:
        from users.signals import create_missing_profiles; create_missing_profiles()
    """
    print("\n" + "=" * 50)
    print("CREATING MISSING PROFILES")
    print("=" * 50 + "\n")

    users_without_profiles = []
    for user in User.objects.all():
        try:
            _ = user.profile
        except UserProfile.DoesNotExist:
            users_without_profiles.append(user)

    print(f"Found {len(users_without_profiles)} users without profiles\n")

    created_count = 0
    for user in users_without_profiles:
        try:
            profile = UserProfile.objects.create(user=user)
            profile.generate_referral_code()
            created_count += 1
            print(f"✅ Created profile for: {user.username}")
        except Exception as e:
            print(f"❌ Error creating profile for {user.username}: {e}")

    print(f"\n✅ Created {created_count} profiles")
    print("=" * 50 + "\n")