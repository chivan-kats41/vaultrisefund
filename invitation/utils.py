"""
Utility Functions for Invitation/Referral System
File: invitation/utils.py

Provides helper functions for:
- Referral tree building and visualization
- Commission calculations and analytics
- Batch processing operations
- Statistics and reporting
- Data validation and integrity checks

Usage:
    from invitation.utils import get_referral_tree, calculate_user_commissions
    
    tree = get_referral_tree(user)
    stats = calculate_user_commissions(user)
"""

from django.db.models import Sum, Count, Q, Avg, F
from django.utils import timezone
from django.contrib.auth import get_user_model
from decimal import Decimal
from datetime import timedelta, datetime
from collections import defaultdict
import json
import csv
from io import StringIO

from .models import (
    ReferralRelationship,
    Commission,
    CommissionRate,
    InvitationClick,
    InvitationReward,
    UserReward
)
from users.models import UserProfile, Order, Transaction, Notification

User = get_user_model()


# ==================== REFERRAL TREE FUNCTIONS ====================

def get_upline_chain(user, max_levels=3):
    """
    Get the complete upline chain for a user.
    
    Args:
        user: User instance
        max_levels: Maximum number of levels to traverse (default 3)
    
    Returns:
        list: List of (user, level) tuples representing upline chain
        
    Example:
        >>> upline = get_upline_chain(user_b)
        >>> print(upline)
        [(user_a, 1), (user_x, 2), (user_y, 3)]
    """
    upline = []
    current_user = user
    
    for level in range(1, max_levels + 1):
        try:
            profile = current_user.profile
            if not profile.referred_by:
                break
            
            parent_profile = profile.referred_by
            if not parent_profile or not hasattr(parent_profile, 'user'):
                break
            
            parent_user = parent_profile.user
            upline.append((parent_user, level))
            current_user = parent_user
        
        except (UserProfile.DoesNotExist, AttributeError):
            break
    
    return upline


def get_downline_chain(user, level=1, max_depth=3):
    """
    Get the downline chain for a user at a specific level.
    
    Args:
        user: User instance
        level: Starting level (default 1)
        max_depth: Maximum depth to traverse (default 3)
    
    Returns:
        list: List of users in the downline
        
    Example:
        >>> downline = get_downline_chain(user_a, level=1)
        >>> print([u.username for u in downline])
        ['user_b', 'user_c', 'user_d']
    """
    if level > max_depth:
        return []
    
    relationships = ReferralRelationship.objects.filter(
        referrer=user,
        level=level
    ).select_related('referee')
    
    downline = [rel.referee for rel in relationships]
    
    # Recursively get deeper levels
    if level < max_depth:
        for referee in downline:
            deeper = get_downline_chain(referee, level + 1, max_depth)
            downline.extend(deeper)
    
    return downline


def get_referral_tree(user, max_levels=3):
    """
    Build a complete referral tree structure for a user.
    
    Args:
        user: User instance (root of the tree)
        max_levels: Maximum depth of the tree (default 3)
    
    Returns:
        dict: Tree structure with nested children
        
    Example:
        >>> tree = get_referral_tree(user_a)
        >>> print(json.dumps(tree, indent=2))
        {
            "user": "user_a",
            "level": 0,
            "children": [
                {
                    "user": "user_b",
                    "level": 1,
                    "is_active": True,
                    "total_purchases": 5,
                    "commission_earned": 50000,
                    "children": [...]
                }
            ],
            "stats": {
                "total_downline": 25,
                "active_downline": 18,
                "total_commission": 250000
            }
        }
    """
    def build_node(current_user, current_level):
        if current_level > max_levels:
            return None
        
        # Get direct referrals
        relationships = ReferralRelationship.objects.filter(
            referrer=current_user,
            level=1
        ).select_related('referee', 'referee__profile')
        
        node = {
            'user': current_user.username,
            'user_id': current_user.id,
            'level': current_level,
            'children': []
        }
        
        # Add profile info if at root
        if current_level == 0:
            profile = current_user.profile
            node['vip_level'] = profile.vip_level
            node['total_referrals'] = profile.total_referrals
            node['referral_earnings'] = float(profile.referral_earnings)
        
        # Build children
        for rel in relationships:
            child_node = {
                'user': rel.referee.username,
                'user_id': rel.referee.id,
                'level': current_level + 1,
                'is_active': rel.is_active,
                'total_purchases': rel.total_purchases,
                'total_purchase_amount': float(rel.total_purchase_amount),
                'commission_earned': float(rel.total_commission_earned),
                'joined_date': rel.created_at.strftime('%Y-%m-%d'),
                'children': []
            }
            
            # Recursively build deeper levels
            if current_level + 1 < max_levels:
                deeper_node = build_node(rel.referee, current_level + 1)
                if deeper_node and deeper_node['children']:
                    child_node['children'] = deeper_node['children']
            
            node['children'].append(child_node)
        
        return node
    
    # Build the tree
    tree = build_node(user, 0)
    
    # Calculate statistics
    tree['stats'] = calculate_tree_statistics(user)
    
    return tree


def calculate_tree_statistics(user):
    """
    Calculate comprehensive statistics for a user's referral tree.
    
    Args:
        user: User instance
    
    Returns:
        dict: Statistics including counts, amounts, and rates
    """
    relationships = ReferralRelationship.objects.filter(referrer=user)
    
    stats = {
        'total_downline': relationships.count(),
        'active_downline': relationships.filter(is_active=True).count(),
        'by_level': {}
    }
    
    # Statistics by level
    for level in [1, 2, 3]:
        level_rels = relationships.filter(level=level)
        level_stats = level_rels.aggregate(
            count=Count('id'),
            active=Count('id', filter=Q(is_active=True)),
            total_purchases=Sum('total_purchases'),
            total_amount=Sum('total_purchase_amount'),
            total_commission=Sum('total_commission_earned')
        )
        
        stats['by_level'][level] = {
            'total': level_stats['count'] or 0,
            'active': level_stats['active'] or 0,
            'total_purchases': level_stats['total_purchases'] or 0,
            'total_amount': float(level_stats['total_amount'] or 0),
            'total_commission': float(level_stats['total_commission'] or 0)
        }
    
    # Overall totals
    totals = relationships.aggregate(
        total_purchases=Sum('total_purchases'),
        total_amount=Sum('total_purchase_amount'),
        total_commission=Sum('total_commission_earned')
    )
    
    stats['total_purchases'] = totals['total_purchases'] or 0
    stats['total_amount'] = float(totals['total_amount'] or 0)
    stats['total_commission'] = float(totals['total_commission'] or 0)
    
    # Active rate
    if stats['total_downline'] > 0:
        stats['active_rate'] = (stats['active_downline'] / stats['total_downline']) * 100
    else:
        stats['active_rate'] = 0
    
    return stats


def get_referral_path(from_user, to_user):
    """
    Find the referral path between two users.
    
    Args:
        from_user: Starting user
        to_user: Target user
    
    Returns:
        list: Path of users from from_user to to_user, or empty if no path
        
    Example:
        >>> path = get_referral_path(user_a, user_d)
        >>> print([u.username for u in path])
        ['user_a', 'user_b', 'user_c', 'user_d']
    """
    # Check if direct relationship exists
    relationship = ReferralRelationship.objects.filter(
        referrer=from_user,
        referee=to_user
    ).first()
    
    if relationship:
        return [from_user, to_user]
    
    # BFS to find path
    from collections import deque
    
    queue = deque([(from_user, [from_user])])
    visited = {from_user.id}
    
    while queue:
        current_user, path = queue.popleft()
        
        # Get direct referrals
        direct_refs = ReferralRelationship.objects.filter(
            referrer=current_user,
            level=1
        ).select_related('referee')
        
        for rel in direct_refs:
            referee = rel.referee
            
            if referee.id == to_user.id:
                return path + [referee]
            
            if referee.id not in visited:
                visited.add(referee.id)
                queue.append((referee, path + [referee]))
    
    return []  # No path found


def build_tree_html(user, max_levels=3):
    """
    Build HTML representation of referral tree for display.
    
    Args:
        user: User instance
        max_levels: Maximum depth (default 3)
    
    Returns:
        str: HTML string of the tree
    """
    def build_html_node(current_user, current_level, prefix=""):
        if current_level > max_levels:
            return ""
        
        html = ""
        
        relationships = ReferralRelationship.objects.filter(
            referrer=current_user,
            level=1
        ).select_related('referee', 'referee__profile')
        
        for idx, rel in enumerate(relationships):
            is_last = (idx == relationships.count() - 1)
            connector = "└─" if is_last else "├─"
            
            status_icon = "✓" if rel.is_active else "○"
            status_color = "green" if rel.is_active else "gray"
            
            html += f'{prefix}{connector} <span style="color: {status_color}">{status_icon}</span> '
            html += f'<strong>{rel.referee.username}</strong> '
            html += f'<small>(VIP {rel.referee.profile.vip_level}, '
            html += f'{rel.total_purchases} purchases, '
            html += f'UGX {float(rel.total_commission_earned):,.2f})</small><br>'
            
            if current_level + 1 < max_levels:
                new_prefix = prefix + ("   " if is_last else "│  ")
                html += build_html_node(rel.referee, current_level + 1, new_prefix)
        
        return html
    
    html = f'<div style="font-family: monospace; line-height: 1.8;">'
    html += f'<strong style="font-size: 16px;">📊 {user.username} (Root)</strong><br>'
    html += build_html_node(user, 0, "")
    html += '</div>'
    
    return html


# ==================== COMMISSION CALCULATION FUNCTIONS ====================

def calculate_commission_for_order(order):
    """
    Calculate what commissions should be for a given order.
    Does not create records, just calculates.
    
    Args:
        order: Order instance
    
    Returns:
        list: List of dicts with commission details
        
    Example:
        >>> commissions = calculate_commission_for_order(order)
        >>> for comm in commissions:
        ...     print(f"{comm['referrer']}: {comm['amount']}")
        user_a: 12000.00
        user_x: 8000.00
        user_y: 16000.00
    """
    buyer = order.user
    order_amount = order.total_amount
    
    commissions = []
    
    # Get all upline relationships
    relationships = ReferralRelationship.objects.filter(
        referee=buyer
    ).select_related('referrer', 'referrer__profile')
    
    for relationship in relationships:
        referrer = relationship.referrer
        level = relationship.level
        
        # Get commission rate
        rate = CommissionRate.get_rate(
            level=level,
            vip_level=referrer.profile.vip_level
        )
        
        if rate > 0:
            amount = (order_amount * rate) / Decimal('100.00')
            
            commissions.append({
                'referrer': referrer,
                'referrer_username': referrer.username,
                'level': level,
                'rate': float(rate),
                'amount': float(amount),
                'relationship': relationship
            })
    
    return commissions


def calculate_user_commissions(user, status='all'):
    """
    Calculate total commissions earned by a user.
    
    Args:
        user: User instance
        status: 'all', 'paid', 'pending', or 'cancelled'
    
    Returns:
        dict: Commission summary with breakdown by level and status
    """
    commissions = Commission.objects.filter(referrer=user)
    
    if status != 'all':
        commissions = commissions.filter(status=status)
    
    summary = {
        'total_count': commissions.count(),
        'total_amount': Decimal('0.00'),
        'by_status': {},
        'by_level': {},
        'recent_commissions': []
    }
    
    # By status
    for status_choice in ['paid', 'pending', 'cancelled', 'failed']:
        status_comms = commissions.filter(status=status_choice).aggregate(
            count=Count('id'),
            total=Sum('commission_amount')
        )
        summary['by_status'][status_choice] = {
            'count': status_comms['count'] or 0,
            'total': float(status_comms['total'] or 0)
        }
    
    # By level
    for level in [1, 2, 3]:
        level_comms = commissions.filter(level=level).aggregate(
            count=Count('id'),
            total=Sum('commission_amount')
        )
        summary['by_level'][level] = {
            'count': level_comms['count'] or 0,
            'total': float(level_comms['total'] or 0)
        }
    
    # Total amount
    total = commissions.aggregate(total=Sum('commission_amount'))
    summary['total_amount'] = float(total['total'] or 0)
    
    # Recent commissions
    recent = commissions.order_by('-created_at')[:10].values(
        'id', 'referee__username', 'level', 'commission_amount',
        'status', 'created_at', 'order__order_number'
    )
    summary['recent_commissions'] = list(recent)
    
    return summary


def recalculate_all_commissions(user):
    """
    Recalculate all commission amounts for a user.
    Useful when rates change or data needs verification.
    
    Args:
        user: User instance
    
    Returns:
        dict: Summary of recalculation
    """
    commissions = Commission.objects.filter(referrer=user)
    
    summary = {
        'total_processed': 0,
        'total_changed': 0,
        'old_total': Decimal('0.00'),
        'new_total': Decimal('0.00'),
        'changes': []
    }
    
    for commission in commissions:
        old_amount = commission.commission_amount
        
        # Recalculate
        new_amount = (commission.order_amount * commission.commission_rate) / Decimal('100.00')
        
        if old_amount != new_amount:
            commission.commission_amount = new_amount
            commission.save(update_fields=['commission_amount'])
            
            summary['total_changed'] += 1
            summary['changes'].append({
                'commission_id': commission.id,
                'order': commission.order.order_number,
                'old_amount': float(old_amount),
                'new_amount': float(new_amount),
                'difference': float(new_amount - old_amount)
            })
        
        summary['old_total'] += old_amount
        summary['new_total'] += new_amount
        summary['total_processed'] += 1
    
    return summary


def get_commission_forecast(user, months=3):
    """
    Forecast potential commissions based on historical data.
    
    Args:
        user: User instance
        months: Number of months to forecast (default 3)
    
    Returns:
        dict: Forecast data with projections
    """
    # Get historical data (last 3 months)
    three_months_ago = timezone.now() - timedelta(days=90)
    
    historical = Commission.objects.filter(
        referrer=user,
        created_at__gte=three_months_ago,
        status='paid'
    ).aggregate(
        total=Sum('commission_amount'),
        count=Count('id'),
        avg_per_commission=Avg('commission_amount')
    )
    
    # Calculate monthly average
    monthly_avg = float(historical['total'] or 0) / 3
    
    # Project future based on growth rate
    active_relationships = ReferralRelationship.objects.filter(
        referrer=user,
        is_active=True
    ).count()
    
    forecast = {
        'historical_monthly_avg': monthly_avg,
        'active_relationships': active_relationships,
        'projections': []
    }
    
    for month in range(1, months + 1):
        # Simple projection with 10% growth rate
        projected = monthly_avg * (1.1 ** month)
        forecast['projections'].append({
            'month': month,
            'projected_amount': round(projected, 2),
            'confidence': 'medium' if month <= 2 else 'low'
        })
    
    return forecast


# ==================== ANALYTICS FUNCTIONS ====================

def get_conversion_analytics(user):
    """
    Get detailed conversion analytics for a user's referral links.
    
    Args:
        user: User instance
    
    Returns:
        dict: Conversion analytics including rates and trends
    """
    clicks = InvitationClick.objects.filter(referrer=user)
    
    analytics = {
        'total_clicks': clicks.count(),
        'total_conversions': clicks.filter(converted=True).count(),
        'conversion_rate': 0,
        'by_device': {},
        'by_date': {},
        'average_time_to_convert': 0
    }
    
    if analytics['total_clicks'] > 0:
        analytics['conversion_rate'] = (
            analytics['total_conversions'] / analytics['total_clicks']
        ) * 100
    
    # By device
    device_stats = clicks.values('device_type').annotate(
        total=Count('id'),
        converted=Count('id', filter=Q(converted=True))
    )
    
    for stat in device_stats:
        device = stat['device_type']
        total = stat['total']
        converted = stat['converted']
        
        analytics['by_device'][device] = {
            'clicks': total,
            'conversions': converted,
            'rate': (converted / total * 100) if total > 0 else 0
        }
    
    # Average time to convert
    converted_clicks = clicks.filter(converted=True).exclude(
        converted_at__isnull=True
    )
    
    if converted_clicks.exists():
        total_time = 0
        count = 0
        
        for click in converted_clicks:
            time_diff = (click.converted_at - click.clicked_at).total_seconds() / 60
            total_time += time_diff
            count += 1
        
        analytics['average_time_to_convert'] = total_time / count if count > 0 else 0
    
    return analytics


def get_performance_metrics(user, days=30):
    """
    Get performance metrics for a user over a period.
    
    Args:
        user: User instance
        days: Number of days to analyze (default 30)
    
    Returns:
        dict: Performance metrics including growth and trends
    """
    start_date = timezone.now() - timedelta(days=days)
    
    # New relationships
    new_relationships = ReferralRelationship.objects.filter(
        referrer=user,
        created_at__gte=start_date
    )
    
    # New commissions
    new_commissions = Commission.objects.filter(
        referrer=user,
        created_at__gte=start_date,
        status='paid'
    )
    
    # Previous period for comparison
    prev_start = start_date - timedelta(days=days)
    prev_relationships = ReferralRelationship.objects.filter(
        referrer=user,
        created_at__gte=prev_start,
        created_at__lt=start_date
    )
    
    prev_commissions = Commission.objects.filter(
        referrer=user,
        created_at__gte=prev_start,
        created_at__lt=start_date,
        status='paid'
    )
    
    metrics = {
        'period_days': days,
        'new_referrals': new_relationships.count(),
        'new_active_referrals': new_relationships.filter(is_active=True).count(),
        'new_commissions_count': new_commissions.count(),
        'new_commissions_amount': float(
            new_commissions.aggregate(total=Sum('commission_amount'))['total'] or 0
        ),
        'growth': {}
    }
    
    # Calculate growth rates
    prev_ref_count = prev_relationships.count()
    if prev_ref_count > 0:
        growth_rate = (
            (metrics['new_referrals'] - prev_ref_count) / prev_ref_count
        ) * 100
        metrics['growth']['referrals'] = round(growth_rate, 2)
    else:
        metrics['growth']['referrals'] = 100 if metrics['new_referrals'] > 0 else 0
    
    prev_comm_amount = float(
        prev_commissions.aggregate(total=Sum('commission_amount'))['total'] or 0
    )
    if prev_comm_amount > 0:
        growth_rate = (
            (metrics['new_commissions_amount'] - prev_comm_amount) / prev_comm_amount
        ) * 100
        metrics['growth']['commissions'] = round(growth_rate, 2)
    else:
        metrics['growth']['commissions'] = (
            100 if metrics['new_commissions_amount'] > 0 else 0
        )
    
    return metrics


def get_top_referrers(limit=10, level=None):
    """
    Get top referrers by commission earned or referral count.
    
    Args:
        limit: Number of top referrers to return (default 10)
        level: Filter by specific level (1, 2, or 3), or None for all
    
    Returns:
        list: List of dicts with referrer info and stats
    """
    relationships = ReferralRelationship.objects.all()
    
    if level:
        relationships = relationships.filter(level=level)
    
    # Group by referrer and calculate stats
    top_refs = relationships.values(
        'referrer__id',
        'referrer__username',
        'referrer__profile__vip_level'
    ).annotate(
        total_referrals=Count('id'),
        active_referrals=Count('id', filter=Q(is_active=True)),
        total_commission=Sum('total_commission_earned'),
        total_purchases=Sum('total_purchase_amount')
    ).order_by('-total_commission')[:limit]
    
    return list(top_refs)


def get_leaderboard(period='all_time', limit=20):
    """
    Get referral leaderboard for gamification.
    
    Args:
        period: 'all_time', 'monthly', 'weekly' (default 'all_time')
        limit: Number of users to return (default 20)
    
    Returns:
        list: Ranked list of top performers
    """
    if period == 'monthly':
        start_date = timezone.now() - timedelta(days=30)
        relationships = ReferralRelationship.objects.filter(created_at__gte=start_date)
    elif period == 'weekly':
        start_date = timezone.now() - timedelta(days=7)
        relationships = ReferralRelationship.objects.filter(created_at__gte=start_date)
    else:
        relationships = ReferralRelationship.objects.all()
    
    leaderboard = relationships.values(
        'referrer__id',
        'referrer__username',
        'referrer__profile__vip_level'
    ).annotate(
        total_referrals=Count('id'),
        active_referrals=Count('id', filter=Q(is_active=True)),
        total_commission=Sum('total_commission_earned'),
        score=F('total_commission') + (F('active_referrals') * 1000)
    ).order_by('-score')[:limit]
    
    # Add rank
    for idx, item in enumerate(leaderboard):
        item['rank'] = idx + 1
        item['total_commission'] = float(item['total_commission'] or 0)
        item['score'] = float(item['score'] or 0)
    
    return list(leaderboard)


# ==================== BATCH OPERATIONS ====================

def process_pending_commissions(user=None):
    """
    Process all pending commissions for a user or all users.
    
    Args:
        user: User instance (optional, if None processes all)
    
    Returns:
        dict: Summary of processing results
    """
    pending = Commission.objects.filter(status='pending')
    
    if user:
        pending = pending.filter(referrer=user)
    
    summary = {
        'total_pending': pending.count(),
        'processed': 0,
        'failed': 0,
        'total_amount': Decimal('0.00'),
        'errors': []
    }
    
    for commission in pending:
        try:
            referrer_profile = commission.referrer.profile
            
            # Credit balance
            referrer_profile.commission_balance += commission.commission_amount
            referrer_profile.referral_earnings += commission.commission_amount
            referrer_profile.save(update_fields=['commission_balance', 'referral_earnings'])
            
            # Create transaction
            transaction = Transaction.objects.create(
                user=commission.referrer,
                transaction_number=f"BATCH_COM{commission.id}",
                transaction_type='promotion_commission',
                amount=commission.commission_amount,
                balance_type='commission_balance',
                balance_before=referrer_profile.commission_balance - commission.commission_amount,
                balance_after=referrer_profile.commission_balance,
                description=f"Batch-processed commission (Level {commission.level})",
                reference_id=str(commission.id),
                status='completed'
            )
            
            # Mark as paid
            commission.mark_as_paid(transaction=transaction)
            
            summary['processed'] += 1
            summary['total_amount'] += commission.commission_amount
        
        except Exception as e:
            summary['failed'] += 1
            summary['errors'].append({
                'commission_id': commission.id,
                'error': str(e)
            })
    
    return summary


def sync_relationship_statistics():
    """
    Synchronize all relationship statistics with actual data.
    Useful for data integrity checks and corrections.
    
    Returns:
        dict: Summary of synchronization
    """
    relationships = ReferralRelationship.objects.all()
    
    summary = {
        'total_processed': 0,
        'updated': 0,
        'errors': []
    }
    
    for relationship in relationships:
        try:
            # Recalculate from actual data
            commissions = Commission.objects.filter(
                relationship=relationship,
                status='paid'
            ).aggregate(
                total=Sum('commission_amount'),
                count=Count('id')
            )
            
            orders = Order.objects.filter(
                user=relationship.referee,
                status__in=['normal', 'finish']
            ).aggregate(
                count=Count('id'),
                total_amount=Sum('total_amount')
            )
            
            # Update relationship
            old_commission = relationship.total_commission_earned
            new_commission = commissions['total'] or Decimal('0.00')
            
            old_purchases = relationship.total_purchases
            new_purchases = orders['count'] or 0
            
            if (old_commission != new_commission or 
                old_purchases != new_purchases):
                
                relationship.total_commission_earned = new_commission
                relationship.total_purchases = new_purchases
                relationship.total_purchase_amount = orders['total_amount'] or Decimal('0.00')
                relationship.save(update_fields=[
                    'total_commission_earned',
                    'total_purchases',
                    'total_purchase_amount'
                ])
                
                summary['updated'] += 1
            
            summary['total_processed'] += 1
        
        except Exception as e:
            summary['errors'].append({
                'relationship_id': relationship.id,
                'error': str(e)
            })
    
    return summary


def cleanup_orphan_relationships():
    """
    Find and optionally clean up orphaned relationships.
    
    Returns:
        dict: Report of orphaned relationships
    """
    orphans = {
        'missing_referrer_profile': [],
        'missing_referee_profile': [],
        'circular_references': [],
        'invalid_levels': []
    }
    
    relationships = ReferralRelationship.objects.select_related(
        'referrer', 'referee'
    ).all()
    
    for rel in relationships:
        # Check for missing profiles
        try:
            referrer_profile = rel.referrer.profile
        except UserProfile.DoesNotExist:
            orphans['missing_referrer_profile'].append(rel.id)
        
        try:
            referee_profile = rel.referee.profile
        except UserProfile.DoesNotExist:
            orphans['missing_referee_profile'].append(rel.id)
        
        # Check for circular reference
        if rel.referrer.id == rel.referee.id:
            orphans['circular_references'].append(rel.id)
        
        # Check for invalid levels
        if rel.level not in [1, 2, 3]:
            orphans['invalid_levels'].append(rel.id)
    
    return orphans


# ==================== REWARD FUNCTIONS ====================

def check_reward_eligibility(user):
    """
    Check if a user is eligible for any rewards.
    
    Args:
        user: User instance
    
    Returns:
        list: List of eligible rewards that haven't been claimed
    """
    # Get user's statistics
    stats = calculate_tree_statistics(user)
    
    # Get all active rewards
    rewards = InvitationReward.objects.filter(is_active=True)
    
    # Get already claimed rewards
    claimed_reward_ids = UserReward.objects.filter(
        user=user
    ).values_list('reward_id', flat=True)
    
    eligible_rewards = []
    
    for reward in rewards:
        # Skip if already claimed
        if reward.id in claimed_reward_ids:
            continue
        
        # Check requirements
        level_stats = stats['by_level'].get(reward.required_level, {})
        total_refs = level_stats.get('total', 0)
        active_refs = level_stats.get('active', 0)
        
        if (total_refs >= reward.required_referrals and
            active_refs >= reward.required_active_referrals):
            
            eligible_rewards.append({
                'reward': reward,
                'reward_id': reward.id,
                'name': reward.name,
                'type': reward.reward_type,
                'description': reward.description,
                'icon': reward.icon,
                'can_claim': True
            })
    
    return eligible_rewards


def auto_claim_rewards(user):
    """
    Automatically claim and process eligible rewards for a user.
    
    Args:
        user: User instance
    
    Returns:
        dict: Summary of claimed rewards
    """
    eligible = check_reward_eligibility(user)
    
    summary = {
        'total_eligible': len(eligible),
        'claimed': 0,
        'processed': 0,
        'rewards': []
    }
    
    for reward_info in eligible:
        reward = reward_info['reward']
        
        try:
            # Create claim record
            user_reward = UserReward.objects.create(
                user=user,
                reward=reward,
                processed=False
            )
            summary['claimed'] += 1
            
            # Process immediately
            profile = user.profile
            
            if reward.reward_type == 'bonus_balance':
                profile.commission_balance += reward.bonus_amount
                profile.save(update_fields=['commission_balance'])
                
                transaction = Transaction.objects.create(
                    user=user,
                    transaction_number=f"REWARD{user_reward.id}",
                    transaction_type='referral_bonus',
                    amount=reward.bonus_amount,
                    balance_type='commission_balance',
                    balance_before=profile.commission_balance - reward.bonus_amount,
                    balance_after=profile.commission_balance,
                    description=f"Milestone reward: {reward.name}",
                    status='completed'
                )
                
                user_reward.transaction = transaction
                user_reward.processed = True
                user_reward.processed_at = timezone.now()
                user_reward.save()
                
                summary['processed'] += 1
            
            elif reward.reward_type == 'vip_upgrade':
                if reward.vip_upgrade_to:
                    profile.vip_level = reward.vip_upgrade_to
                    profile.save(update_fields=['vip_level'])
                    
                    user_reward.processed = True
                    user_reward.processed_at = timezone.now()
                    user_reward.save()
                    
                    summary['processed'] += 1
            
            # Send notification
            Notification.objects.create(
                user=user,
                title=f"Reward Unlocked! {reward.icon if reward.icon else '🎁'}",
                message=f"Congratulations! You've earned: {reward.name}",
                notification_type='referral',
                is_important=True
            )
            
            summary['rewards'].append({
                'name': reward.name,
                'type': reward.reward_type,
                'processed': user_reward.processed
            })
        
        except Exception as e:
            continue
    
    return summary


def get_reward_progress(user):
    """
    Get user's progress towards all rewards.
    
    Args:
        user: User instance
    
    Returns:
        list: List of all rewards with progress information
    """
    stats = calculate_tree_statistics(user)
    rewards = InvitationReward.objects.filter(is_active=True).order_by('required_referrals')
    claimed_ids = UserReward.objects.filter(user=user).values_list('reward_id', flat=True)
    
    progress_list = []
    
    for reward in rewards:
        level_stats = stats['by_level'].get(reward.required_level, {})
        current_refs = level_stats.get('total', 0)
        current_active = level_stats.get('active', 0)
        
        is_claimed = reward.id in claimed_ids
        
        refs_progress = min(100, (current_refs / reward.required_referrals * 100)) if reward.required_referrals > 0 else 100
        active_progress = min(100, (current_active / reward.required_active_referrals * 100)) if reward.required_active_referrals > 0 else 100
        
        overall_progress = min(refs_progress, active_progress)
        
        progress_list.append({
            'reward': reward,
            'name': reward.name,
            'icon': reward.icon,
            'required_referrals': reward.required_referrals,
            'current_referrals': current_refs,
            'required_active': reward.required_active_referrals,
            'current_active': current_active,
            'progress_percentage': round(overall_progress, 1),
            'is_eligible': (current_refs >= reward.required_referrals and 
                          current_active >= reward.required_active_referrals),
            'is_claimed': is_claimed,
            'status': 'claimed' if is_claimed else ('eligible' if overall_progress >= 100 else 'in_progress')
        })
    
    return progress_list


# ==================== EXPORT FUNCTIONS ====================

def export_referral_data(user, format='dict'):
    """
    Export complete referral data for a user.
    
    Args:
        user: User instance
        format: 'dict', 'json', or 'csv'
    
    Returns:
        Exported data in requested format
    """
    tree = get_referral_tree(user)
    stats = calculate_user_commissions(user)
    analytics = get_conversion_analytics(user)
    metrics = get_performance_metrics(user)
    
    data = {
        'user': {
            'id': user.id,
            'username': user.username,
            'vip_level': user.profile.vip_level,
            'referral_code': user.profile.referral_code,
            'total_referrals': user.profile.total_referrals,
            'referral_earnings': float(user.profile.referral_earnings),
            'commission_balance': float(user.profile.commission_balance)
        },
        'tree': tree,
        'commissions': stats,
        'analytics': analytics,
        'performance': metrics
    }
    
    if format == 'json':
        return json.dumps(data, indent=2, default=str)
    elif format == 'csv':
        # Flatten for CSV
        output = StringIO()
        writer = csv.writer(output)
        
        # Write basic info
        writer.writerow(['User', user.username])
        writer.writerow(['Total Referrals', data['user']['total_referrals']])
        writer.writerow(['Total Earnings', data['user']['referral_earnings']])
        writer.writerow([])
        
        # Write relationships
        writer.writerow(['Level', 'Total', 'Active', 'Commission'])
        for level, stats in data['tree']['stats']['by_level'].items():
            writer.writerow([
                level,
                stats['total'],
                stats['active'],
                stats['total_commission']
            ])
        
        return output.getvalue()
    
    return data


def export_commission_report(start_date=None, end_date=None, status='paid'):
    """
    Export commission report for all users.
    
    Args:
        start_date: Start date (optional)
        end_date: End date (optional)
        status: Commission status filter (default 'paid')
    
    Returns:
        str: CSV formatted report
    """
    commissions = Commission.objects.filter(status=status)
    
    if start_date:
        commissions = commissions.filter(created_at__gte=start_date)
    if end_date:
        commissions = commissions.filter(created_at__lte=end_date)
    
    commissions = commissions.select_related(
        'referrer', 'referee', 'order'
    ).order_by('-created_at')
    
    output = StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        'Date', 'Referrer', 'Referee', 'Level', 'Order Number',
        'Order Amount', 'Commission Rate', 'Commission Amount', 'Status'
    ])
    
    # Data
    for comm in commissions:
        writer.writerow([
            comm.created_at.strftime('%Y-%m-%d %H:%M'),
            comm.referrer.username,
            comm.referee.username,
            comm.level,
            comm.order.order_number,
            float(comm.order_amount),
            float(comm.commission_rate),
            float(comm.commission_amount),
            comm.status
        ])
    
    return output.getvalue()


def export_relationships_csv(user=None):
    """
    Export referral relationships to CSV.
    
    Args:
        user: User instance (optional, exports all if None)
    
    Returns:
        str: CSV formatted data
    """
    relationships = ReferralRelationship.objects.select_related(
        'referrer', 'referee', 'referrer__profile', 'referee__profile'
    )
    
    if user:
        relationships = relationships.filter(referrer=user)
    
    output = StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        'Referrer', 'Referrer VIP', 'Referee', 'Referee VIP', 'Level',
        'Status', 'Total Purchases', 'Total Amount', 'Commission Earned',
        'Created Date', 'First Purchase', 'Last Purchase'
    ])
    
    # Data
    for rel in relationships:
        writer.writerow([
            rel.referrer.username,
            rel.referrer.profile.vip_level,
            rel.referee.username,
            rel.referee.profile.vip_level,
            rel.level,
            'Active' if rel.is_active else 'Inactive',
            rel.total_purchases,
            float(rel.total_purchase_amount),
            float(rel.total_commission_earned),
            rel.created_at.strftime('%Y-%m-%d'),
            rel.first_purchase_date.strftime('%Y-%m-%d') if rel.first_purchase_date else 'N/A',
            rel.last_purchase_date.strftime('%Y-%m-%d') if rel.last_purchase_date else 'N/A'
        ])
    
    return output.getvalue()


# ==================== VALIDATION FUNCTIONS ====================

def validate_referral_integrity():
    """
    Validate the integrity of the referral system.
    Check for circular references, orphaned records, and data inconsistencies.
    
    Returns:
        dict: Validation report with errors and warnings
    """
    report = {
        'valid': True,
        'errors': [],
        'warnings': [],
        'statistics': {}
    }
    
    # Check 1: Circular references
    relationships = ReferralRelationship.objects.all()
    for rel in relationships:
        if rel.referrer.id == rel.referee.id:
            report['errors'].append({
                'type': 'circular_reference',
                'relationship_id': rel.id,
                'message': f'User {rel.referrer.username} refers themselves'
            })
            report['valid'] = False
    
    # Check 2: Orphaned profiles
    profiles_without_users = UserProfile.objects.filter(user__isnull=True)
    if profiles_without_users.exists():
        report['warnings'].append({
            'type': 'orphaned_profiles',
            'count': profiles_without_users.count(),
            'message': f'{profiles_without_users.count()} profiles without users'
        })
    
    # Check 3: Invalid level chains
    for rel in relationships.filter(level__gt=1):
        # Verify parent chain exists
        upline = get_upline_chain(rel.referee, max_levels=rel.level)
        if len(upline) < rel.level:
            report['errors'].append({
                'type': 'invalid_level_chain',
                'relationship_id': rel.id,
                'message': f'Level {rel.level} relationship without complete upline chain'
            })
            report['valid'] = False
    
    # Check 4: Commission calculation accuracy
    commissions = Commission.objects.select_related('order')[:100]  # Sample
    for comm in commissions:
        expected = (comm.order_amount * comm.commission_rate) / Decimal('100.00')
        if abs(comm.commission_amount - expected) > Decimal('0.01'):
            report['warnings'].append({
                'type': 'commission_mismatch',
                'commission_id': comm.id,
                'expected': float(expected),
                'actual': float(comm.commission_amount),
                'message': f'Commission amount mismatch for commission {comm.id}'
            })
    
    # Check 5: Balance consistency
    profiles = UserProfile.objects.select_related('user')
    for profile in profiles:
        # Check if commission_balance matches sum of paid commissions
        paid_total = Commission.objects.filter(
            referrer=profile.user,
            status='paid'
        ).aggregate(total=Sum('commission_amount'))['total'] or Decimal('0.00')
        
        withdrawn = profile.total_withdrawn or Decimal('0.00')
        expected_balance = paid_total - withdrawn
        
        # Allow small difference due to other operations
        if abs(profile.commission_balance - expected_balance) > Decimal('1.00'):
            report['warnings'].append({
                'type': 'balance_mismatch',
                'user': profile.user.username,
                'expected': float(expected_balance),
                'actual': float(profile.commission_balance),
                'difference': float(abs(profile.commission_balance - expected_balance))
            })
    
    # Statistics
    report['statistics'] = {
        'total_relationships': relationships.count(),
        'total_commissions': Commission.objects.count(),
        'total_clicks': InvitationClick.objects.count(),
        'errors_found': len(report['errors']),
        'warnings_found': len(report['warnings'])
    }
    
    return report


def fix_relationship_data(dry_run=True):
    """
    Attempt to fix common data issues.
    
    Args:
        dry_run: If True, don't make changes, just report what would be fixed
    
    Returns:
        dict: Report of fixes applied or that would be applied
    """
    fixes = {
        'dry_run': dry_run,
        'circular_refs_removed': 0,
        'statistics_updated': 0,
        'commissions_recalculated': 0,
        'details': []
    }
    
    # Fix 1: Remove circular references
    circular_refs = ReferralRelationship.objects.filter(
        referrer=F('referee')
    )
    
    if circular_refs.exists():
        count = circular_refs.count()
        if not dry_run:
            circular_refs.delete()
        fixes['circular_refs_removed'] = count
        fixes['details'].append(f'Removed {count} circular references')
    
    # Fix 2: Sync statistics
    relationships = ReferralRelationship.objects.all()
    for rel in relationships[:100]:  # Limit for safety
        try:
            # Get actual commission total
            actual_commission = Commission.objects.filter(
                relationship=rel,
                status='paid'
            ).aggregate(total=Sum('commission_amount'))['total'] or Decimal('0.00')
            
            if rel.total_commission_earned != actual_commission:
                if not dry_run:
                    rel.total_commission_earned = actual_commission
                    rel.save(update_fields=['total_commission_earned'])
                fixes['statistics_updated'] += 1
        except Exception as e:
            fixes['details'].append(f'Error updating relationship {rel.id}: {str(e)}')
    
    # Fix 3: Recalculate commission amounts
    commissions = Commission.objects.all()[:100]  # Limit for safety
    for comm in commissions:
        expected = (comm.order_amount * comm.commission_rate) / Decimal('100.00')
        if abs(comm.commission_amount - expected) > Decimal('0.01'):
            if not dry_run:
                comm.commission_amount = expected
                comm.save(update_fields=['commission_amount'])
            fixes['commissions_recalculated'] += 1
    
    return fixes


# ==================== REPORTING FUNCTIONS ====================

def generate_monthly_report(year, month):
    """
    Generate comprehensive monthly report for the referral system.
    
    Args:
        year: Year (e.g., 2024)
        month: Month (1-12)
    
    Returns:
        dict: Comprehensive monthly report
    """
    from datetime import date
    from calendar import monthrange
    
    start_date = datetime(year, month, 1)
    _, last_day = monthrange(year, month)
    end_date = datetime(year, month, last_day, 23, 59, 59)
    
    # New relationships
    new_relationships = ReferralRelationship.objects.filter(
        created_at__gte=start_date,
        created_at__lte=end_date
    )
    
    # Commissions paid
    commissions_paid = Commission.objects.filter(
        created_at__gte=start_date,
        created_at__lte=end_date,
        status='paid'
    )
    
    # Clicks and conversions
    clicks = InvitationClick.objects.filter(
        clicked_at__gte=start_date,
        clicked_at__lte=end_date
    )
    
    report = {
        'period': {
            'year': year,
            'month': month,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d')
        },
        'relationships': {
            'new_total': new_relationships.count(),
            'new_active': new_relationships.filter(is_active=True).count(),
            'by_level': {}
        },
        'commissions': {
            'total_count': commissions_paid.count(),
            'total_amount': float(
                commissions_paid.aggregate(total=Sum('commission_amount'))['total'] or 0
            ),
            'by_level': {}
        },
        'marketing': {
            'total_clicks': clicks.count(),
            'conversions': clicks.filter(converted=True).count(),
            'conversion_rate': 0
        },
        'top_performers': []
    }
    
    # By level breakdowns
    for level in [1, 2, 3]:
        level_rels = new_relationships.filter(level=level)
        report['relationships']['by_level'][level] = {
            'total': level_rels.count(),
            'active': level_rels.filter(is_active=True).count()
        }
        
        level_comms = commissions_paid.filter(level=level)
        report['commissions']['by_level'][level] = {
            'count': level_comms.count(),
            'total': float(
                level_comms.aggregate(total=Sum('commission_amount'))['total'] or 0
            )
        }
    
    # Conversion rate
    if report['marketing']['total_clicks'] > 0:
        report['marketing']['conversion_rate'] = (
            report['marketing']['conversions'] / report['marketing']['total_clicks']
        ) * 100
    
    # Top performers
    top_refs = new_relationships.values(
        'referrer__username'
    ).annotate(
        count=Count('id'),
        commission=Sum('total_commission_earned')
    ).order_by('-count')[:10]
    
    report['top_performers'] = list(top_refs)
    
    return report


def get_system_health():
    """
    Get overall health metrics of the referral system.
    
    Returns:
        dict: System health indicators
    """
    total_users = User.objects.count()
    total_relationships = ReferralRelationship.objects.count()
    active_relationships = ReferralRelationship.objects.filter(is_active=True).count()
    
    # Pending commissions
    pending_commissions = Commission.objects.filter(status='pending')
    pending_amount = float(
        pending_commissions.aggregate(total=Sum('commission_amount'))['total'] or 0
    )
    
    # Recent activity (last 7 days)
    week_ago = timezone.now() - timedelta(days=7)
    recent_relationships = ReferralRelationship.objects.filter(
        created_at__gte=week_ago
    ).count()
    recent_commissions = Commission.objects.filter(
        created_at__gte=week_ago,
        status='paid'
    ).count()
    
    # Calculate health score (0-100)
    activation_rate = (active_relationships / total_relationships * 100) if total_relationships > 0 else 0
    growth_rate = (recent_relationships / total_relationships * 100) if total_relationships > 0 else 0
    
    health_score = min(100, (activation_rate * 0.5) + (growth_rate * 0.3) + 20)
    
    health = {
        'health_score': round(health_score, 1),
        'status': 'healthy' if health_score >= 70 else ('warning' if health_score >= 40 else 'critical'),
        'metrics': {
            'total_users': total_users,
            'total_relationships': total_relationships,
            'active_relationships': active_relationships,
            'activation_rate': round(activation_rate, 2),
            'pending_commissions_count': pending_commissions.count(),
            'pending_commissions_amount': pending_amount,
            'recent_activity': {
                'new_relationships_7d': recent_relationships,
                'commissions_paid_7d': recent_commissions
            }
        },
        'recommendations': []
    }
    
    # Add recommendations
    if activation_rate < 50:
        health['recommendations'].append('Low activation rate - consider incentives for first purchases')
    if pending_commissions.count() > 100:
        health['recommendations'].append('High pending commissions - process payments soon')
    if recent_relationships < 10:
        health['recommendations'].append('Low recent growth - increase marketing efforts')
    
    return health


# ==================== UTILITY HELPERS ====================

def mask_phone_number(phone):
    """
    Mask phone number for privacy.
    
    Args:
        phone: Phone number string
    
    Returns:
        str: Masked phone number
    """
    if not phone or len(phone) < 4:
        return phone
    
    if len(phone) >= 10:
        return f"{phone[:2]}*******{phone[-2:]}"
    else:
        return f"{phone[:2]}*****{phone[-2:]}"


def format_currency(amount, currency='UGX'):
    """
    Format amount as currency string.
    
    Args:
        amount: Decimal or float amount
        currency: Currency code (default 'UGX')
    
    Returns:
        str: Formatted currency string
    """
    try:
        return f"{currency} {float(amount):,.2f}"
    except:
        return f"{currency} 0.00"


def calculate_roi(investment, returns):
    """
    Calculate ROI percentage.
    
    Args:
        investment: Initial investment amount
        returns: Return amount
    
    Returns:
        float: ROI percentage
    """
    if investment == 0:
        return 0
    return ((returns - investment) / investment) * 100


# ==================== END OF UTILS ====================

"""
AVAILABLE UTILITY FUNCTIONS:

TREE FUNCTIONS:
- get_upline_chain(user, max_levels=3)
- get_downline_chain(user, level=1, max_depth=3)
- get_referral_tree(user, max_levels=3)
- calculate_tree_statistics(user)
- get_referral_path(from_user, to_user)
- build_tree_html(user, max_levels=3)

COMMISSION FUNCTIONS:
- calculate_commission_for_order(order)
- calculate_user_commissions(user, status='all')
- recalculate_all_commissions(user)
- get_commission_forecast(user, months=3)

ANALYTICS FUNCTIONS:
- get_conversion_analytics(user)
- get_performance_metrics(user, days=30)
- get_top_referrers(limit=10, level=None)
- get_leaderboard(period='all_time', limit=20)

BATCH OPERATIONS:
- process_pending_commissions(user=None)
- sync_relationship_statistics()
- cleanup_orphan_relationships()

REWARD FUNCTIONS:
- check_reward_eligibility(user)
- auto_claim_rewards(user)
- get_reward_progress(user)

EXPORT FUNCTIONS:
- export_referral_data(user, format='dict')
- export_commission_report(start_date, end_date, status='paid')
- export_relationships_csv(user=None)

VALIDATION FUNCTIONS:
- validate_referral_integrity()
- fix_relationship_data(dry_run=True)

REPORTING FUNCTIONS:
- generate_monthly_report(year, month)
- get_system_health()

UTILITY HELPERS:
- mask_phone_number(phone)
- format_currency(amount, currency='UGX')
- calculate_roi(investment, returns)
"""