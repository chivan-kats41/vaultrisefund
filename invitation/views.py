"""
Views for the Invitation System
File: invitation/views.py
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Sum, Q
from decimal import Decimal
import logging

from .models import ReferralRelationship, Commission, CommissionRate
from users.models import UserProfile

logger = logging.getLogger(__name__)


# ==================== PAGE VIEWS ====================

@login_required
def team(request):
    return render(request, 'invitation/invite.html')


@login_required
def level(request):
    return render(request, 'invitation/team.html')


# ==================== API ENDPOINTS ====================

@login_required
@require_http_methods(["GET"])
def get_invitation_stats(request):
    try:
        user    = request.user
        profile = user.profile

        try:
            rate_l1 = CommissionRate.objects.get(level=1, vip_level=0, is_active=True).rate
        except CommissionRate.DoesNotExist:
            rate_l1 = Decimal('12.00')

        try:
            rate_l2 = CommissionRate.objects.get(level=2, vip_level=0, is_active=True).rate
        except CommissionRate.DoesNotExist:
            rate_l2 = Decimal('8.00')

        try:
            rate_l3 = CommissionRate.objects.get(level=3, vip_level=0, is_active=True).rate
        except CommissionRate.DoesNotExist:
            rate_l3 = Decimal('16.00')

        def level_stats(lvl):
            return ReferralRelationship.objects.filter(
                referrer=user, level=lvl
            ).aggregate(
                total=Count('id'),
                active=Count('id', filter=Q(is_active=True))
            )

        s1 = level_stats(1)
        s2 = level_stats(2)
        s3 = level_stats(3)

        base_url       = request.build_absolute_uri('/').rstrip('/')
        promotion_link = f"{base_url}/register/?ref={profile.referral_code}"

        return JsonResponse({
            'currency':       'UGX',
            'commission':     str(profile.commission_balance),
            'promotion_link': promotion_link,

            'yield_level_1':       float(rate_l1),
            'invitation_sum_1':    s1['total'] or 0,
            'invitation_active_1': s1['active'] or 0,

            'yield_level_2':       float(rate_l2),
            'invitation_sum_2':    s2['total'] or 0,
            'invitation_active_2': s2['active'] or 0,

            'yield_level_3':       float(rate_l3),
            'invitation_sum_3':    s3['total'] or 0,
            'invitation_active_3': s3['active'] or 0,
        })

    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'User profile not found'}, status=404)
    except Exception as e:
        logger.error(f'Error in get_invitation_stats: {e}', exc_info=True)
        return JsonResponse({'error': 'Internal server error'}, status=500)


@login_required
@require_http_methods(["GET"])
def get_team_members(request):
    try:
        user  = request.user
        level = request.GET.get('level', '1')

        try:
            level = int(level)
            if level not in [1, 2, 3]:
                return JsonResponse({'error': 'Level must be 1, 2, or 3'}, status=400)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Level must be an integer'}, status=400)

        relationships = ReferralRelationship.objects.filter(
            referrer=user, level=level
        ).select_related('referee').order_by('-created_at')

        members = []
        for rel in relationships:
            referee = rel.referee

            # ✅ FIX: safely get or create profile — never crash on missing profile
            try:
                referee_profile = UserProfile.objects.get(user=referee)
            except UserProfile.DoesNotExist:
                try:
                    referee_profile = UserProfile.objects.create(user=referee)
                    referee_profile.generate_referral_code()
                    logger.info(f"Auto-created missing profile for {referee.username}")
                except Exception as create_err:
                    logger.warning(
                        f"Could not create profile for {referee.username}: {create_err}"
                    )
                    # Still show the member with masked username, just no phone
                    phone  = referee.username
                    masked = (
                        f"{phone[:2]}*******{phone[-2:]}" if len(phone) > 10
                        else f"{phone[:2]}*****{phone[-2:]}" if len(phone) >= 4
                        else phone
                    )
                    members.append({
                        'id':              masked,
                        'registerTime':    referee.date_joined.strftime('%Y-%m-%d %H:%M:%S'),
                        'purchased':       rel.is_active,
                        'total_purchases': rel.total_purchases,
                        'total_amount':    float(rel.total_purchase_amount),
                    })
                    continue

            # Mask phone/username for privacy
            phone = referee_profile.phone_number or referee.username
            if len(phone) > 10:
                masked = f"{phone[:2]}*******{phone[-2:]}"
            elif len(phone) >= 4:
                masked = f"{phone[:2]}*****{phone[-2:]}"
            else:
                masked = phone

            members.append({
                'id':              masked,
                'registerTime':    referee.date_joined.strftime('%Y-%m-%d %H:%M:%S'),
                'purchased':       rel.is_active,       # True once they invest
                'total_purchases': rel.total_purchases,
                'total_amount':    float(rel.total_purchase_amount),
            })

        return JsonResponse({
            'totalInvite': relationships.count(),
            'active':      relationships.filter(is_active=True).count(),
            'members':     members,
        })

    except Exception as e:
        logger.error(f'Error in get_team_members: {e}', exc_info=True)
        return JsonResponse({'error': 'Internal server error'}, status=500)


@login_required
@require_http_methods(["GET"])
def get_commission_summary(request):
    try:
        user        = request.user
        commissions = Commission.objects.filter(referrer=user)

        summary = {
            'total': {
                'count':  commissions.count(),
                'amount': float(
                    commissions.aggregate(total=Sum('commission_amount'))['total'] or 0
                ),
            },
            'by_status': {},
            'by_level':  {},
            'recent':    [],
        }

        for status in ['paid', 'pending', 'cancelled']:
            sc = commissions.filter(status=status)
            summary['by_status'][status] = {
                'count':  sc.count(),
                'amount': float(
                    sc.aggregate(total=Sum('commission_amount'))['total'] or 0
                ),
            }

        for lvl in [1, 2, 3]:
            lc = commissions.filter(level=lvl, status='paid')
            summary['by_level'][lvl] = {
                'count':  lc.count(),
                'amount': float(
                    lc.aggregate(total=Sum('commission_amount'))['total'] or 0
                ),
            }

        for comm in commissions.order_by('-created_at')[:10].values(
            'commission_amount', 'level', 'status', 'created_at'
        ):
            summary['recent'].append({
                'amount': float(comm['commission_amount']),
                'level':  comm['level'],
                'status': comm['status'],
                'date':   comm['created_at'].strftime('%Y-%m-%d %H:%M'),
            })

        return JsonResponse(summary)

    except Exception as e:
        logger.error(f'Error in get_commission_summary: {e}', exc_info=True)
        return JsonResponse({'error': 'Internal server error'}, status=500)


# ==================== UTILITY FUNCTIONS ====================

def mask_identifier(identifier):
    if not identifier or len(identifier) < 4:
        return identifier
    if len(identifier) >= 10:
        return f"{identifier[:2]}*******{identifier[-2:]}"
    return f"{identifier[:2]}*****{identifier[-2:]}"


def format_currency(amount, currency='UGX'):
    try:
        return f"{currency} {float(amount):,.2f}"
    except Exception:
        return f"{currency} 0.00"