import logging
from datetime import date, timedelta
from decimal import Decimal
from celery import shared_task
from django.db import transaction

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_daily_earnings(self):
    """Process daily earnings for all active investments."""
    from store.models import UserInvestment, DailyEarningLog
    from users.models import UserProfile

    today     = date.today()
    processed = 0
    errors    = 0

    active = UserInvestment.objects.filter(
        status='active', end_date__gte=today,
    ).select_related('user', 'product')

    try:
        with transaction.atomic():
            for inv in active:
                if inv.last_payout and inv.last_payout >= today:
                    continue
                if DailyEarningLog.objects.filter(investment=inv, date=today).exists():
                    continue

                earning = inv.product.daily_earning * inv.shares
                try:
                    # ✅ FIX: credit to withdrawal_balance on UserProfile, not a balance field on User
                    profile = inv.user  # inv.user IS a UserProfile FK
                    profile.withdrawal_balance += earning
                    profile.total_earnings     += earning
                    profile.save(update_fields=['withdrawal_balance', 'total_earnings'])

                    inv.total_earned += earning
                    inv.last_payout   = today
                    if today >= inv.end_date:
                        inv.status = 'completed'
                    inv.save(update_fields=['total_earned', 'last_payout', 'status'])

                    DailyEarningLog.objects.create(investment=inv, amount=earning, date=today)
                    processed += 1
                except Exception as e:
                    logger.error(f"Error processing earning for investment {inv.id}: {e}")
                    errors += 1
    except Exception as exc:
        logger.error(f"Daily earnings task failed: {exc}")
        raise self.retry(exc=exc, countdown=300)

    logger.info(f"Daily earnings: processed={processed}, errors={errors}")
    return {'processed': processed, 'errors': errors, 'date': str(today)}


@shared_task(bind=True, max_retries=3)
def expire_investments(self):
    """Mark investments as completed when their end date passes."""
    from store.models import UserInvestment
    today = date.today()
    count = UserInvestment.objects.filter(
        status='active', end_date__lt=today
    ).update(status='completed')
    logger.info(f"Expired {count} investments on {today}")
    return {'expired': count}


@shared_task(bind=True, max_retries=5)
def distribute_commissions(self, investment_id):
    """
    Distribute referral commissions when a purchase is made via users/views.py
    api_product_purchase. This task handles the Order-based flow.

    Called from: users/views.py → api_product_purchase → distribute_commissions.delay(order.id)
    But we receive an Order id here, NOT a UserInvestment id.
    We therefore accept EITHER an Order pk OR a UserInvestment pk and handle both.
    """
    from .models import ReferralRelationship, Commission, CommissionRate
    from users.models import UserProfile, Transaction, Notification, Order

    try:
        # ── Try Order first (primary purchase path via users/views.py) ──────
        try:
            order  = Order.objects.select_related('user', 'product').get(id=investment_id)
            buyer_user   = order.user          # auth User
            order_amount = order.total_amount
            source_ref   = order.order_number
        except Order.DoesNotExist:
            # ── Fall back to UserInvestment (BuyInvestmentAPIView path) ─────
            from store.models import UserInvestment
            inv          = UserInvestment.objects.select_related('user__user', 'product').get(id=investment_id)
            buyer_user   = inv.user.user       # UserProfile → auth User
            order_amount = inv.amount_paid
            source_ref   = f"INV-{inv.id}"

        # ── Find upline referral relationships ────────────────────────────
        upline = ReferralRelationship.objects.filter(
            referee=buyer_user
        ).select_related('referrer', 'referrer__profile').order_by('level')

        if not upline.exists():
            logger.info(f"No referral relationships found for {buyer_user.username}")
            return {'investment_id': investment_id, 'commissions_distributed': 0}

        commissions_given = 0

        with transaction.atomic():
            for rel in upline:
                referrer         = rel.referrer
                referrer_profile = referrer.profile
                level            = rel.level

                # ── Get commission rate ───────────────────────────────────
                commission_rate = CommissionRate.get_rate(
                    level=level, vip_level=referrer_profile.vip_level
                )
                if commission_rate <= 0:
                    logger.info(f"Zero rate for L{level}, skipping")
                    continue

                commission_amount = (order_amount * commission_rate) / Decimal('100.00')

                # ── Credit commission to referrer's commission_balance ────
                bal_before = referrer_profile.commission_balance
                referrer_profile.commission_balance += commission_amount
                referrer_profile.referral_earnings  += commission_amount
                referrer_profile.save(update_fields=['commission_balance', 'referral_earnings'])

                # ── Create Commission record ──────────────────────────────
                commission = Commission.objects.create(
                    referrer          = referrer,
                    referee           = buyer_user,
                    relationship      = rel,
                    level             = level,
                    order_amount      = order_amount,
                    commission_rate   = commission_rate,
                    commission_amount = commission_amount,
                    status            = 'pending',
                )

                # ── Create Transaction record ─────────────────────────────
                txn_number = f"COM{commission.id}_{source_ref}"
                txn = Transaction.objects.create(
                    user               = referrer,
                    transaction_number = txn_number,
                    transaction_type   = 'promotion_commission',
                    amount             = commission_amount,
                    balance_type       = 'commission_balance',
                    balance_before     = bal_before,
                    balance_after      = referrer_profile.commission_balance,
                    description        = f"Level {level} commission from {buyer_user.username}",
                    reference_id       = source_ref,
                    status             = 'completed',
                )

                # ── Mark commission as paid ───────────────────────────────
                commission.mark_as_paid(transaction=txn)

                # ── Update relationship stats & activate if first purchase ─
                rel.add_purchase(order_amount)
                rel.add_commission(commission_amount)
                if not rel.is_active:
                    rel.activate()   # ✅ FIX: always activate, not just on first purchase

                # ── Notify referrer ───────────────────────────────────────
                Notification.objects.create(
                    user              = referrer,
                    title             = "Commission Earned! 💰",
                    message           = (
                        f"UGX {commission_amount:,.2f} commission from "
                        f"{buyer_user.username} (Level {level})"
                    ),
                    notification_type = 'referral',
                    is_important      = True,
                )

                commissions_given += 1
                logger.info(
                    f"Commission L{level}: {referrer.username} "
                    f"+UGX {commission_amount} from {buyer_user.username}"
                )

        return {
            'investment_id':           investment_id,
            'commissions_distributed': commissions_given,
        }

    except Exception as exc:
        logger.error(f"distribute_commissions failed for id={investment_id}: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60)