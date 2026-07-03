from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.conf import settings
from django.utils import timezone
from decimal import Decimal

from .models import (
    ReferralRelationship,
    Commission,
    CommissionRate,
    InvitationClick,
)
from users.models import Order, Transaction, Notification, UserProfile


# ==================== REFERRAL RELATIONSHIP CREATION ====================

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_referral_relationships(sender, instance, created, **kwargs):
    """
    When a new user registers, create ReferralRelationship rows
    for their direct referrer (L1) and that referrer's referrer (L2/L3).
    """
    if not created:
        return

    user = instance
    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        return

    if not profile.referred_by:
        return

    direct_referrer_profile = profile.referred_by
    if not direct_referrer_profile or not hasattr(direct_referrer_profile, 'user'):
        return

    direct_referrer = direct_referrer_profile.user

    # ── Level 1 ──────────────────────────────────────────────────────────
    try:
        rel_l1, created_l1 = ReferralRelationship.objects.get_or_create(
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
            direct_referrer_profile.total_referrals += 1
            direct_referrer_profile.save(update_fields=['total_referrals'])
            Notification.objects.create(
                user              = direct_referrer,
                title             = "New Referral! 🎉",
                message           = f"{user.username} joined using your referral link!",
                notification_type = 'referral',
                is_important      = True,
            )
    except Exception as e:
        print(f"Error creating L1 relationship: {e}")
        return

    # ── Level 2 ──────────────────────────────────────────────────────────
    if direct_referrer_profile.referred_by:
        l2_profile = direct_referrer_profile.referred_by
        if l2_profile and hasattr(l2_profile, 'user'):
            l2_user = l2_profile.user
            try:
                rel_l2, created_l2 = ReferralRelationship.objects.get_or_create(
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
                        user              = l2_user,
                        title             = "Level 2 Referral",
                        message           = f"Your network grew! {user.username} joined as Level 2.",
                        notification_type = 'referral',
                    )
            except Exception as e:
                print(f"Error creating L2 relationship: {e}")

            # ── Level 3 ──────────────────────────────────────────────────
            if l2_profile.referred_by:
                l3_profile = l2_profile.referred_by
                if l3_profile and hasattr(l3_profile, 'user'):
                    l3_user = l3_profile.user
                    try:
                        rel_l3, created_l3 = ReferralRelationship.objects.get_or_create(
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
                                user              = l3_user,
                                title             = "Level 3 Referral",
                                message           = f"Network expanded! {user.username} joined as Level 3.",
                                notification_type = 'referral',
                            )
                    except Exception as e:
                        print(f"Error creating L3 relationship: {e}")


# ==================== ORDER COMMISSION SIGNAL ====================

@receiver(post_save, sender=Order)
def process_order_commissions(sender, instance, created, **kwargs):
    """
    When an Order is created (via users/views.py api_product_purchase),
    distribute commissions to the buyer's referral upline and activate
    their ReferralRelationship.

    NOTE: distribute_commissions Celery task does the same thing for
    the UserInvestment path. This signal handles the Order path so both
    purchase flows are covered.
    """
    if not created:
        return

    order        = instance
    buyer        = order.user       # auth User
    order_amount = order.total_amount

    if order.status not in ['normal', 'finish']:
        return

    upline = ReferralRelationship.objects.filter(
        referee=buyer
    ).select_related('referrer', 'referrer__profile')

    if not upline.exists():
        return

    for relationship in upline:
        referrer         = relationship.referrer
        referrer_profile = referrer.profile
        level            = relationship.level

        commission_rate = CommissionRate.get_rate(
            level=level, vip_level=referrer_profile.vip_level
        )
        if commission_rate <= 0:
            continue

        commission_amount = (order_amount * commission_rate) / Decimal('100.00')

        try:
            bal_before = referrer_profile.commission_balance

            commission = Commission.objects.create(
                referrer          = referrer,
                referee           = buyer,
                relationship      = relationship,
                level             = level,
                order_amount      = order_amount,
                commission_rate   = commission_rate,
                commission_amount = commission_amount,
                status            = 'pending',
            )

            referrer_profile.commission_balance += commission_amount
            referrer_profile.referral_earnings  += commission_amount
            referrer_profile.save(update_fields=['commission_balance', 'referral_earnings'])

            txn = Transaction.objects.create(
                user               = referrer,
                transaction_number = f"COM{commission.id}_{order.order_number}",
                transaction_type   = 'promotion_commission',
                amount             = commission_amount,
                balance_type       = 'commission_balance',
                balance_before     = bal_before,
                balance_after      = referrer_profile.commission_balance,
                description        = f"Level {level} commission from {buyer.username}",
                reference_id       = order.order_number,
                status             = 'completed',
            )

            commission.mark_as_paid(transaction=txn)

            # ✅ FIX: update relationship stats and always activate
            relationship.add_purchase(order_amount)
            relationship.add_commission(commission_amount)
            if not relationship.is_active:
                relationship.activate()

            Notification.objects.create(
                user              = referrer,
                title             = "Commission Earned! 💰",
                message           = (
                    f"UGX {commission_amount:,.2f} from "
                    f"{buyer.username} (Level {level})"
                ),
                notification_type = 'referral',
                is_important      = True,
            )

        except Exception as e:
            print(f"Error processing commission for {referrer.username}: {e}")
            continue


# ==================== ORDER CANCELLATION REVERSAL ====================

@receiver(pre_save, sender=Order)
def handle_order_cancellation(sender, instance, **kwargs):
    """Reverse commissions when an order is cancelled."""
    if not instance.pk:
        return
    try:
        old_order = Order.objects.get(pk=instance.pk)
    except Order.DoesNotExist:
        return

    if old_order.status == 'cancelled' or instance.status != 'cancelled':
        return

    commissions = Commission.objects.filter(
        relationship__referee=instance.user,
        status='paid',
    ).select_related('referrer', 'referrer__profile')

    for commission in commissions:
        referrer         = commission.referrer
        referrer_profile = referrer.profile
        amount           = commission.commission_amount

        try:
            bal_before = referrer_profile.commission_balance
            referrer_profile.commission_balance = max(
                Decimal('0.00'), referrer_profile.commission_balance - amount
            )
            referrer_profile.referral_earnings = max(
                Decimal('0.00'), referrer_profile.referral_earnings - amount
            )
            referrer_profile.save(update_fields=['commission_balance', 'referral_earnings'])

            Transaction.objects.create(
                user               = referrer,
                transaction_number = f"REV{commission.id}_{instance.order_number}",
                transaction_type   = 'system_deduction',
                amount             = -amount,
                balance_type       = 'commission_balance',
                balance_before     = bal_before,
                balance_after      = referrer_profile.commission_balance,
                description        = f"Commission reversal — Order {instance.order_number} cancelled",
                reference_id       = instance.order_number,
                status             = 'completed',
            )

            commission.cancel()

            rel = commission.relationship
            rel.total_purchase_amount   = max(Decimal('0.00'), rel.total_purchase_amount - instance.total_amount)
            rel.total_commission_earned = max(Decimal('0.00'), rel.total_commission_earned - amount)
            rel.total_purchases         = max(0, rel.total_purchases - 1)
            # ✅ Deactivate if no purchases remain
            if rel.total_purchases == 0:
                rel.is_active = False
            rel.save(update_fields=[
                'total_purchase_amount', 'total_commission_earned',
                'total_purchases', 'is_active',
            ])

            Notification.objects.create(
                user              = referrer,
                title             = "Commission Reversed",
                message           = (
                    f"Order {instance.order_number} cancelled. "
                    f"UGX {amount:,.2f} reversed."
                ),
                notification_type = 'system',
            )

        except Exception as e:
            print(f"Error reversing commission for {referrer.username}: {e}")
            continue


@receiver(post_save, sender=InvitationClick)
def update_click_conversion(sender, instance, created, **kwargs):
    pass