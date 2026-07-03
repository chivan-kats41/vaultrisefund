import logging
from datetime import date, timedelta
from decimal import Decimal
from celery import shared_task
from django.db import transaction

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_daily_earnings(self):
    """
    Runs daily (via Celery beat).
    Credits each active investment's daily earning to the investor's balance.
    """
    from .models import UserInvestment, DailyEarningLog
    from users.models import UserProfile

    today     = date.today()
    processed = 0
    errors    = 0

    active = UserInvestment.objects.filter(
        status='active',
        end_date__gte=today,
    ).select_related('user', 'product')

    try:
        with transaction.atomic():
            for inv in active:
                # Skip if already paid today
                if inv.last_payout and inv.last_payout >= today:
                    continue
                if DailyEarningLog.objects.filter(investment=inv, date=today).exists():
                    continue

                earning = inv.product.daily_earning * inv.shares

                try:
                    # FIX: inv.user is already a UserProfile (see store/models.py FK)
                    profile = UserProfile.objects.select_for_update().get(pk=inv.user_id)
                    profile.balance += earning
                    profile.save(update_fields=['balance'])

                    inv.total_earned += earning
                    inv.last_payout   = today
                    if today >= inv.end_date:
                        inv.status = 'completed'
                    inv.save(update_fields=['total_earned', 'last_payout', 'status'])

                    DailyEarningLog.objects.create(
                        investment=inv,
                        amount=earning,
                        date=today,
                    )
                    processed += 1

                except Exception as e:
                    logger.error(f"Error processing daily earning for investment {inv.id}: {e}")
                    errors += 1

    except Exception as exc:
        logger.error(f"Daily earnings task failed: {exc}")
        raise self.retry(exc=exc, countdown=300)

    logger.info(f"Daily earnings done — processed={processed}, errors={errors}, date={today}")
    return {'processed': processed, 'errors': errors, 'date': str(today)}


@shared_task(bind=True, max_retries=3)
def expire_investments(self):
    """
    Runs daily (via Celery beat).
    Marks any investment whose end_date has passed as completed.
    """
    from .models import UserInvestment

    today = date.today()
    count = UserInvestment.objects.filter(
        status='active',
        end_date__lt=today,
    ).update(status='completed')

    logger.info(f"Expired {count} investments on {today}")
    return {'expired': count}


@shared_task(bind=True, max_retries=5)
def distribute_commissions(self, investment_id):
    """
    Fires after a UserInvestment is created (called from BuyInvestmentAPIView).
    Walks the upline chain (L1 → L2 → L3) and credits each referrer's
    commission_balance with the correct percentage of the investment amount.

    Rates are read from invitation.models.CommissionRate so they can be
    adjusted from the Django admin without touching code.
    """
    from .models import UserInvestment
    from invitation.models import ReferralRelationship, Commission, CommissionRate
    from users.models import UserProfile, Transaction, Notification

    try:
        inv = UserInvestment.objects.select_related('user', 'product').get(id=investment_id)
    except UserInvestment.DoesNotExist:
        logger.error(f"distribute_commissions: investment {investment_id} not found")
        return

    amount = inv.amount_paid
    # inv.user is a UserProfile instance (store/models.py FK points to users.UserProfile)
    buyer_profile = inv.user
    buyer_user    = buyer_profile.user  # the actual auth User

    # Find all upline relationships for this buyer (up to 3 levels)
    upline = ReferralRelationship.objects.filter(
        referee=buyer_user
    ).select_related('referrer', 'referrer__profile')[:3]

    if not upline.exists():
        logger.info(f"No upline found for investment {investment_id} — no commissions distributed")
        return

    with transaction.atomic():
        for rel in upline:
            referrer      = rel.referrer          # auth User
            level         = rel.level              # 1, 2, or 3

            # FIX: read rate from CommissionRate model, not hardcoded dict
            try:
                ref_profile = UserProfile.objects.select_for_update().get(user=referrer)
            except UserProfile.DoesNotExist:
                logger.warning(f"No profile for referrer {referrer} — skipping")
                continue

            rate              = CommissionRate.get_rate(level=level, vip_level=ref_profile.vip_level)
            commission_amount = (amount * rate) / Decimal('100')

            if commission_amount <= 0:
                continue

            # FIX: credit UserProfile.commission_balance, not User.balance
            balance_before                = ref_profile.commission_balance
            ref_profile.commission_balance += commission_amount
            ref_profile.referral_earnings  += commission_amount
            ref_profile.save(update_fields=['commission_balance', 'referral_earnings'])

            # Create Commission record
            comm = Commission.objects.create(
                referrer          = referrer,
                referee           = buyer_user,
                relationship      = rel,
                level             = level,
                order_amount      = amount,
                commission_rate   = rate,
                commission_amount = commission_amount,
                status            = 'paid',
            )

            # Create Transaction record for the referrer's ledger
            Transaction.objects.create(
                user               = referrer,
                transaction_number = f"COM{comm.id}_{inv.id}",
                transaction_type   = 'promotion_commission',
                amount             = commission_amount,
                balance_type       = 'commission_balance',
                balance_before     = balance_before,
                balance_after      = ref_profile.commission_balance,
                description        = f"Level {level} commission — {buyer_user.username} invested UGX {amount:,.0f}",
                reference_id       = str(inv.id),
                status             = 'completed',
            )

            # Mark relationship active on first purchase
            rel.add_purchase(amount)
            rel.add_commission(commission_amount)
            if rel.total_purchases == 1:
                rel.activate()

            # Notify referrer
            Notification.objects.create(
                user              = referrer,
                title             = "Commission Earned!",
                message           = (
                    f"UGX {commission_amount:,.0f} credited — "
                    f"{buyer_user.username} invested (Level {level})"
                ),
                notification_type = 'referral',
                is_important      = True,
            )

            logger.info(
                f"Commission L{level}: {referrer.username} "
                f"+UGX {commission_amount:,.0f} (rate={rate}%, inv={investment_id})"
            )

    return {
        'investment_id':            investment_id,
        'commissions_distributed':  len(upline),
    }