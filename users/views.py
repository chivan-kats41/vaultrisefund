"""
Complete Views for Users App
File: users/views.py
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum, Q
from django.utils import timezone
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings
from decimal import Decimal
from datetime import timedelta
import json
import uuid
import re
import traceback

from .models import (
    UserProfile, VIPLevel, Wallet, Order,
    Settlement, Transaction, Recharge, Withdrawal,
    Notification, PasswordResetCode
)
from store.models import InvestmentProduct

User = get_user_model()


# ==================== HELPER FUNCTIONS ====================

def get_or_create_profile(user):
    if not user.is_authenticated:
        return None
    if not user.pk:
        return None
    try:
        return UserProfile.objects.get(user=user)
    except UserProfile.DoesNotExist:
        try:
            profile = UserProfile.objects.create(user=user)
            profile.generate_referral_code()
            return profile
        except Exception as e:
            print(f"Error creating profile: {e}")
            return None
    except Exception as e:
        print(f"Error getting profile: {e}")
        return None


def validate_phone_number(wallet_type, phone_number):
    phone = phone_number.replace(' ', '').replace('-', '')
    if wallet_type == 'MTN':
        if phone.startswith('256'):
            return bool(re.match(r'^256(77|78|76|79)\d{7}$', phone))
        elif phone.startswith('0'):
            return bool(re.match(r'^0(77|78|76|79)\d{7}$', phone))
    elif wallet_type == 'Airtel':
        if phone.startswith('256'):
            return bool(re.match(r'^256(70|72|74|75)\d{7}$', phone))
        elif phone.startswith('0'):
            return bool(re.match(r'^0(70|72|74|75)\d{7}$', phone))
    return False


def generate_merchant_account(payment_method):
    merchants = {
        'MTN':    {'account': '0762899641', 'name': 'OKAPIS WILLINGTON'},
        'Airtel': {'account': '0746066574', 'name': 'OKAPIS WILLINGTON'},
    }
    return merchants.get(payment_method, merchants['MTN'])


def notify_admins_withdrawal(withdrawal, user):
    admin_users = User.objects.filter(is_superadmin=True)
    subject = f'[Agnicoe Eagle] New Withdrawal Request — {withdrawal.withdrawal_number}'
    body = (
        f'A new withdrawal request has been submitted.\n\n'
        f'User:        {user.username} ({user.email})\n'
        f'Amount:      UGX {withdrawal.amount:,.2f}\n'
        f'Fee (10%%):   UGX {withdrawal.withdrawal_fee:,.2f}\n'
        f'Net Payout:  UGX {withdrawal.net_amount:,.2f}\n'
        f'Wallet:      {withdrawal.destination_wallet_type} — '
        f'{withdrawal.destination_account} ({withdrawal.destination_name})\n'
        f'Reference:   {withdrawal.withdrawal_number}\n\n'
        f'Log in to the admin panel to approve or reject this request.'
    )
    admin_emails = []
    for admin in admin_users:
        Notification.objects.create(
            user=admin,
            title='New Withdrawal Request',
            message=(
                f'User {user.username} has requested a withdrawal of '
                f'UGX {withdrawal.amount:,.2f}. '
                f'Net payout: UGX {withdrawal.net_amount:,.2f}. '
                f'Ref: {withdrawal.withdrawal_number}'
            ),
            notification_type='system',
            is_important=True,
        )
        if admin.email:
            admin_emails.append(admin.email)
    if admin_emails:
        try:
            send_mail(
                subject=subject, message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=admin_emails, fail_silently=True,
            )
        except Exception as e:
            print(f"Admin withdrawal email error: {e}")


# ==================== PAGE VIEWS ====================

def account(request):
    profile = get_or_create_profile(request.user)
    if not profile:
        messages.error(request, 'Error loading profile. Please contact support.')
        return redirect('login')
    try:
        vip_level = VIPLevel.objects.get(level=profile.vip_level)
        next_vip  = VIPLevel.objects.get(level=profile.vip_level + 1)
    except VIPLevel.DoesNotExist:
        vip_level = None
        next_vip  = None

    vip_progress_percentage = 0
    if next_vip:
        current_threshold = vip_level.required_investment if vip_level else Decimal('0')
        progress = profile.total_investment - current_threshold
        required = next_vip.required_investment - current_threshold
        if required > 0:
            vip_progress_percentage = float(progress / required * 100)

    recent_orders = Order.objects.filter(user=request.user).select_related('product')[:5]

    context = {
        # ✅ user.nickname (Accounts.nickname) is now the single source of
        # truth for display name, set at registration. Falls back to
        # username only if somehow still blank on an old account.
        'nickname':           request.user.nickname or request.user.username,
        'username':           request.user.username,
        'recharge_balance':   profile.recharge_balance,
        'withdrawal_balance': profile.withdrawal_balance + profile.recharge_balance + profile.commission_balance,
        'commission_balance': profile.commission_balance,
        'total_orders':       profile.total_orders,
        'vip_progress':       float(vip_progress_percentage),
        'vip_required':       float(next_vip.required_investment) if next_vip else None,
        'user':               request.user,
        'profile':            profile,
        'vip_level_obj':      vip_level,
        'next_vip':           next_vip,
        'total_balance':      profile.recharge_balance + profile.withdrawal_balance + profile.commission_balance,
        'recent_orders':      recent_orders,
    }
    return render(request, 'account page/my.html', context)


def rewards(request):
    profile = get_or_create_profile(request.user)
    if not profile:
        messages.error(request, 'Error loading profile.')
        return redirect('login')
    reward_transactions = Transaction.objects.filter(
        user=request.user, transaction_type='promotion_commission'
    ).order_by('-created_at')
    context = {
        'profile':             profile,
        'user':                request.user,
        'reward_transactions': reward_transactions,
        'total_rewards':       reward_transactions.aggregate(total=Sum('amount'))['total'] or Decimal('0'),
    }
    return render(request, 'account page/rewards.html', context)


def vip(request):
    vip_levels = VIPLevel.objects.filter(is_active=True).order_by('level')
    profile    = get_or_create_profile(request.user)
    if not profile:
        messages.error(request, 'Error loading profile.')
        return redirect('login')
    context = {
        'vip_levels':        vip_levels,
        'current_vip_level': profile.vip_level,
        'total_investment':  profile.total_investment,
    }
    return render(request, 'account page/viplevel.html', context)


def about(request):
    return render(request, 'account page/about.html')


def mail(request):
    notifications = Notification.objects.filter(
        Q(user=request.user) | Q(is_broadcast=True)
    ).order_by('-created_at')
    unread_count  = notifications.filter(is_read=False).count()
    notifications = notifications[:20]
    return render(request, 'account page/mail.html', {
        'notifications': notifications, 'unread_count': unread_count,
    })


def info(request):
    profile = get_or_create_profile(request.user)
    if not profile:
        messages.error(request, 'Error loading profile.')
        return redirect('login')
    return render(request, 'account page/info.html', {
        'profile':    profile,
        'user':       request.user,
        'avatar_url': profile.avatar.url if profile.avatar else None,
    })


def orders(request):
    all_orders    = Order.objects.filter(user=request.user).select_related('product').order_by('-created_at')

    # Bring every active order's progress, settlements, and income up to
    # date with today's date before rendering (self-healing, no cron needed).
    for order in all_orders:
        if order.status == 'normal':
            order.sync_progress()

    status_filter = request.GET.get('status', 'all')
    if status_filter != 'all':
        all_orders = all_orders.filter(status=status_filter)
    return render(request, 'account page/my_orders.html', {
        'orders':          all_orders,
        'active_orders':   all_orders.filter(status='normal').count(),
        'finished_orders': all_orders.filter(status='finish').count(),
        'status_filter':   status_filter,
    })


def bankCardInfo(request):
    try:
        wallet     = Wallet.objects.get(user=request.user)
        has_wallet = True
    except Wallet.DoesNotExist:
        wallet     = None
        has_wallet = False
    return render(request, 'account page/bankCardInfo.html', {
        'wallet': wallet, 'has_wallet': has_wallet,
    })


def AddCard(request):
    try:
        wallet     = Wallet.objects.get(user=request.user)
        has_wallet = True
    except Wallet.DoesNotExist:
        wallet     = None
        has_wallet = False
    return render(request, 'account page/AddCard.html', {
        'wallet': wallet, 'has_wallet': has_wallet,
    })


def recharge(request):
    profile = get_or_create_profile(request.user)
    if not profile:
        messages.error(request, 'Error loading profile.')
        return redirect('login')
    recharge_history = Recharge.objects.filter(user=request.user).order_by('-created_at')[:10]
    return render(request, 'account page/recharge.html', {
        'profile':          profile,
        'balance':          profile.recharge_balance,
        'recharge_history': recharge_history,
    })


def balance(request):
    transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')
    filter_type  = request.GET.get('type', 'all')
    if filter_type == 'recharge':
        transactions = transactions.filter(transaction_type__in=['recharge', 'buy_product'])
    elif filter_type == 'withdrawal':
        transactions = transactions.filter(
            transaction_type__in=['withdrawal', 'promotion_commission', 'system_deduction']
        )
    return render(request, 'account page/balance.html', {
        'transactions': transactions[:50], 'filter_type': filter_type,
    })


def help(request):
    return render(request, 'account page/help.html')


def withdraw(request):
    profile = get_or_create_profile(request.user)
    if not profile:
        messages.error(request, 'Error loading profile.')
        return redirect('login')
    try:
        wallet     = Wallet.objects.get(user=request.user)
        has_wallet = True
    except Wallet.DoesNotExist:
        wallet     = None
        has_wallet = False
    withdrawal_history = Withdrawal.objects.filter(user=request.user).order_by('-created_at')[:10]
    return render(request, 'account page/withdrawal.html', {
        'profile':            profile,
        'balance':            profile.withdrawal_balance,
        'wallet':             wallet,
        'has_wallet':         has_wallet,
        'withdrawal_history': withdrawal_history,
    })


# ==================== API ENDPOINTS ====================

@require_http_methods(["GET"])
def api_wallet_get(request):
    try:
        wallet = Wallet.objects.get(user=request.user)
        return JsonResponse({
            'success':        True,
            'wallet_type':    wallet.wallet_type,
            'wallet_account': wallet.wallet_account,
            'owner_name':     wallet.owner_name,
            'usdt_wallet':    wallet.usdt_wallet or '',
            'is_verified':    wallet.is_verified,
            'is_active':      wallet.is_active,
        })
    except Wallet.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'No wallet found'}, status=404)


@require_POST
def api_wallet_add(request):
    try:
        data = json.loads(request.body)
        if Wallet.objects.filter(user=request.user).exists():
            return JsonResponse({'success': False, 'message': 'Wallet already exists. Use update endpoint.'}, status=400)

        wallet_type          = data.get('wallet_type')
        owner_name           = data.get('owner_name', '').strip()
        wallet_account       = data.get('wallet_account', '').strip()
        usdt_wallet          = data.get('usdt_wallet', '').strip()
        transaction_password = data.get('transaction_password')

        if not wallet_type or wallet_type not in ['MTN', 'Airtel']:
            return JsonResponse({'success': False, 'message': 'Invalid wallet type'}, status=400)
        if not owner_name or len(owner_name) < 6:
            return JsonResponse({'success': False, 'message': 'Owner name must be at least 6 characters'}, status=400)
        if not wallet_account:
            return JsonResponse({'success': False, 'message': 'Wallet account is required'}, status=400)
        if not validate_phone_number(wallet_type, wallet_account):
            return JsonResponse({'success': False, 'message': f'Invalid {wallet_type} phone number'}, status=400)
        if not transaction_password:
            return JsonResponse({'success': False, 'message': 'Transaction password is required'}, status=400)

        profile = get_or_create_profile(request.user)
        if not profile:
            return JsonResponse({'success': False, 'message': 'Error loading profile'}, status=500)

        if not profile.transaction_password_set:
            profile.transaction_password     = make_password(transaction_password)
            profile.transaction_password_set = True
            profile.save()
        else:
            if not check_password(transaction_password, profile.transaction_password):
                return JsonResponse({'success': False, 'message': 'Incorrect transaction password'}, status=400)

        wallet = Wallet.objects.create(
            user=request.user, wallet_type=wallet_type,
            wallet_account=wallet_account, owner_name=owner_name.upper(),
            usdt_wallet=usdt_wallet, is_verified=False, is_active=True
        )
        return JsonResponse({
            'success': True, 'message': 'Wallet added successfully',
            'wallet': {
                'wallet_type':    wallet.wallet_type,
                'wallet_account': wallet.wallet_account,
                'owner_name':     wallet.owner_name,
            },
        })
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@require_POST
def api_wallet_update(request):
    try:
        data = json.loads(request.body)
        try:
            wallet = Wallet.objects.get(user=request.user)
        except Wallet.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'No wallet found. Use add endpoint.'}, status=404)

        wallet_type          = data.get('wallet_type')
        owner_name           = data.get('owner_name', '').strip()
        wallet_account       = data.get('wallet_account', '').strip()
        usdt_wallet          = data.get('usdt_wallet', '').strip()
        transaction_password = data.get('transaction_password')

        if not wallet_type or wallet_type not in ['MTN', 'Airtel']:
            return JsonResponse({'success': False, 'message': 'Invalid wallet type'}, status=400)
        if not owner_name or len(owner_name) < 3:
            return JsonResponse({'success': False, 'message': 'Owner name must be at least 3 characters'}, status=400)
        if not wallet_account:
            return JsonResponse({'success': False, 'message': 'Wallet account is required'}, status=400)
        if not validate_phone_number(wallet_type, wallet_account):
            return JsonResponse({'success': False, 'message': f'Invalid {wallet_type} phone number'}, status=400)
        if not transaction_password:
            return JsonResponse({'success': False, 'message': 'Transaction password is required'}, status=400)

        profile = get_or_create_profile(request.user)
        if not profile:
            return JsonResponse({'success': False, 'message': 'Error loading profile'}, status=500)
        if not check_password(transaction_password, profile.transaction_password):
            return JsonResponse({'success': False, 'message': 'Incorrect transaction password'}, status=400)

        wallet.wallet_type    = wallet_type
        wallet.wallet_account = wallet_account
        wallet.owner_name     = owner_name.upper()
        wallet.usdt_wallet    = usdt_wallet
        wallet.save()
        return JsonResponse({
            'success': True, 'message': 'Wallet updated successfully',
            'wallet': {
                'wallet_type':    wallet.wallet_type,
                'wallet_account': wallet.wallet_account,
                'owner_name':     wallet.owner_name,
            },
        })
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@require_POST
def api_withdrawal_apply(request):
    try:
        data    = json.loads(request.body)
        profile = get_or_create_profile(request.user)
        if not profile:
            return JsonResponse({'success': False, 'message': 'Error loading profile'}, status=500)

        try:
            wallet = Wallet.objects.get(user=request.user)
        except Wallet.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Please add your bank card first'}, status=400)

        amount = data.get('amount')
        if not amount:
            return JsonResponse({'success': False, 'message': 'Please enter withdrawal amount'}, status=400)
        try:
            amount = Decimal(str(amount))
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid amount'}, status=400)

        if amount < Decimal('10000'):
            return JsonResponse({'success': False, 'message': 'Minimum withdrawal amount is UGX 10,000'}, status=400)
        if amount > Decimal('5000000'):
            return JsonResponse({'success': False, 'message': 'Maximum withdrawal amount is UGX 5,000,000'}, status=400)

        password = data.get('password')
        if not password:
            return JsonResponse({'success': False, 'message': 'Please enter transaction password'}, status=400)
        if not profile.transaction_password_set:
            return JsonResponse({'success': False, 'message': 'Transaction password not set. Please set it in settings.'}, status=400)
        if not check_password(password, profile.transaction_password):
            return JsonResponse({'success': False, 'message': 'Incorrect transaction password'}, status=400)

        if profile.withdrawal_balance < amount:
            return JsonResponse({
                'success': False,
                'message': f'Insufficient balance. Available: UGX {profile.withdrawal_balance:,.2f}'
            }, status=400)

        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if Withdrawal.objects.filter(
            user=request.user, created_at__gte=today_start,
            status__in=['pending', 'processing', 'completed']
        ).count() >= 1:
            return JsonResponse({'success': False, 'message': 'You can only request one withdrawal per day'}, status=400)

        current_hour = timezone.now().hour
        if not (10 <= current_hour < 19):
            return JsonResponse({'success': False, 'message': 'Withdrawals are only allowed between 10:00 and 19:00'}, status=400)

        withdrawal_fee_rate = Decimal('10.00')
        withdrawal_fee      = (amount * withdrawal_fee_rate) / Decimal('100')
        net_amount          = amount - withdrawal_fee
        withdrawal_number   = f"WDR{timezone.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}"

        balance_before              = profile.withdrawal_balance
        profile.withdrawal_balance -= amount
        profile.total_withdrawn    += amount
        profile.save()

        withdrawal = Withdrawal.objects.create(
            user=request.user, wallet=wallet,
            withdrawal_number=withdrawal_number,
            amount=amount, withdrawal_fee_rate=withdrawal_fee_rate,
            withdrawal_fee=withdrawal_fee, net_amount=net_amount,
            destination_wallet_type=wallet.wallet_type,
            destination_account=wallet.wallet_account,
            destination_name=wallet.owner_name, status='pending',
        )

        transaction_number = f"TXN{timezone.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}"
        Transaction.objects.create(
            user=request.user, transaction_number=transaction_number,
            transaction_type='withdrawal', amount=-amount,
            balance_type='withdrawal_balance',
            balance_before=balance_before, balance_after=profile.withdrawal_balance,
            description=f'Withdrawal request — {withdrawal_number}',
            reference_id=withdrawal_number, status='pending',
        )

        Notification.objects.create(
            user=request.user, title='Withdrawal Request Submitted',
            message=(
                f'Your withdrawal of UGX {amount:,.2f} has been submitted. '
                f'Fee: UGX {withdrawal_fee:,.2f}. '
                f'You will receive UGX {net_amount:,.2f} upon approval. '
                f'Ref: {withdrawal_number}. Processing within 24 hours.'
            ),
            notification_type='system', is_important=True,
        )

        notify_admins_withdrawal(withdrawal, request.user)

        return JsonResponse({
            'success': True, 'message': 'Withdrawal request submitted successfully',
            'withdrawal': {
                'withdrawal_number': withdrawal.withdrawal_number,
                'amount':            float(amount),
                'fee':               float(withdrawal_fee),
                'net_amount':        float(net_amount),
                'status':            'pending',
            },
        })
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@require_POST
def api_recharge_initiate(request):
    try:
        data                 = json.loads(request.body)
        amount               = data.get('amount')
        payment_method       = (data.get('payment_method', '') or '').strip().upper()
        user_payment_account = data.get('user_payment_account', '').strip()

        if not amount:
            return JsonResponse({'success': False, 'message': 'Please enter recharge amount'}, status=400)
        try:
            amount = Decimal(str(amount))
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid amount'}, status=400)
        if amount < Decimal('10000'):
            return JsonResponse({'success': False, 'message': 'Minimum recharge amount is UGX 10,000'}, status=400)
        if not payment_method or payment_method not in ['MTN', 'AIRTEL', 'USDT']:
            return JsonResponse({'success': False, 'message': f'Invalid payment method: {payment_method}'}, status=400)
        if not user_payment_account:
            return JsonResponse({'success': False, 'message': 'Please enter your payment account'}, status=400)
        if payment_method in ['MTN', 'AIRTEL']:
            wallet_type = 'Airtel' if payment_method == 'AIRTEL' else payment_method
            if not validate_phone_number(wallet_type, user_payment_account):
                return JsonResponse({'success': False, 'message': f'Invalid {payment_method} phone number'}, status=400)

        merchant_key    = 'Airtel' if payment_method == 'AIRTEL' else payment_method
        merchant        = generate_merchant_account(merchant_key)
        recharge_number = f"RCH{timezone.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}"

        recharge = Recharge.objects.create(
            user=request.user, recharge_number=recharge_number, amount=amount,
            payment_method=payment_method, user_payment_account=user_payment_account,
            merchant_account=merchant['account'], merchant_name=merchant['name'],
            status='pending', expires_at=timezone.now() + timedelta(minutes=15)
        )
        return JsonResponse({
            'success': True, 'message': 'Recharge initiated successfully',
            'recharge': {
                'recharge_number':  recharge.recharge_number,
                'amount':           float(amount),
                'payment_method':   payment_method,
                'merchant_account': merchant['account'],
                'merchant_name':    merchant['name'],
                'expires_at':       recharge.expires_at.isoformat(),
                'status':           'pending',
            },
        })
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@require_http_methods(["GET"])
def api_user_balance(request):
    profile = get_or_create_profile(request.user)
    if not profile:
        return JsonResponse({'success': False, 'message': 'Error loading profile'}, status=500)
    return JsonResponse({
        'success':            True,
        'recharge_balance':   float(profile.recharge_balance),
        'withdrawal_balance': float(profile.withdrawal_balance),
        'commission_balance': float(profile.commission_balance),
        'total_balance':      float(
            profile.recharge_balance + profile.withdrawal_balance + profile.commission_balance
        ),
        'vip_level':    profile.vip_level,
        'total_orders': profile.total_orders,
    })


@require_http_methods(["GET"])
def api_transactions(request):
    filter_type  = request.GET.get('filter', 'all')
    page         = int(request.GET.get('page', 1))
    per_page     = 20
    transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')
    if filter_type == 'recharge':
        transactions = transactions.filter(transaction_type__in=['recharge', 'buy_product'])
    elif filter_type == 'withdrawal':
        transactions = transactions.filter(
            transaction_type__in=['withdrawal', 'promotion_commission', 'system_deduction']
        )
    start = (page - 1) * per_page
    end   = start + per_page
    return JsonResponse({
        'success': True,
        'transactions': [
            {
                'id':                 t.id,
                'transaction_number': t.transaction_number,
                'type':               t.transaction_type,
                'amount':             float(t.amount),
                'balance_type':       t.balance_type,
                'description':        t.description or '',
                'status':             t.status,
                'created_at':         t.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            }
            for t in transactions[start:end]
        ],
        'has_more': transactions.count() > end,
        'total':    transactions.count(),
    })


@require_POST
def api_update_profile(request):
    try:
        profile = get_or_create_profile(request.user)
        if not profile:
            return JsonResponse({'success': False, 'message': 'Error loading profile'}, status=500)
        nickname = request.POST.get('nickname', '').strip()
        if nickname:
            if len(nickname) < 3:
                return JsonResponse({'success': False, 'message': 'Nickname must be at least 3 characters'}, status=400)
            # ✅ user.nickname is the source of truth for display; keep
            # profile.nickname in sync too for any legacy reads.
            request.user.nickname = nickname
            request.user.save(update_fields=['nickname'])
            profile.nickname = nickname
        if 'avatar' in request.FILES:
            profile.avatar = request.FILES['avatar']
        profile.save()
        return JsonResponse({
            'success': True, 'message': 'Profile updated successfully',
            'profile': {
                'nickname':   request.user.nickname or request.user.username,
                'avatar_url': profile.avatar.url if profile.avatar else None,
            },
        })
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@require_POST
def api_change_password(request):
    try:
        data             = json.loads(request.body)
        password_type    = data.get('type')
        current_password = data.get('current_password')
        new_password     = data.get('new_password')

        if not all([password_type, current_password, new_password]):
            return JsonResponse({'success': False, 'message': 'All fields are required'}, status=400)
        if len(new_password) < 6:
            return JsonResponse({'success': False, 'message': 'Password must be at least 6 characters'}, status=400)

        if password_type == 'login':
            if not request.user.check_password(current_password):
                return JsonResponse({'success': False, 'message': 'Current password is incorrect'}, status=400)
            request.user.set_password(new_password)
            request.user.save()
            message = 'Login password changed successfully'
        elif password_type == 'transaction':
            profile = get_or_create_profile(request.user)
            if not profile:
                return JsonResponse({'success': False, 'message': 'Error loading profile'}, status=500)
            if profile.transaction_password_set:
                if not check_password(current_password, profile.transaction_password):
                    return JsonResponse({'success': False, 'message': 'Current transaction password is incorrect'}, status=400)
            profile.transaction_password     = make_password(new_password)
            profile.transaction_password_set = True
            profile.save()
            message = 'Transaction password changed successfully'
        else:
            return JsonResponse({'success': False, 'message': 'Invalid password type'}, status=400)

        return JsonResponse({'success': True, 'message': message})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@require_http_methods(["GET"])
def api_order_detail(request, order_id):
    try:
        order = Order.objects.select_related('product').get(id=order_id, user=request.user)

        # Bring this order's days_completed / income / settlement statuses
        # up to date with today before returning it.
        if order.status == 'normal':
            order.sync_progress()

        settlements = Settlement.objects.filter(order=order).order_by('-settlement_date')
        return JsonResponse({
            'success': True,
            'order': {
                'id':                     order.id,
                'order_number':           order.order_number,
                'product_name':           order.product.name,
                'total_amount':           float(order.total_amount),
                'daily_income':           float(order.daily_income),
                'duration_days':          order.duration_days,
                'days_completed':         order.days_completed,
                'days_remaining':         order.days_remaining,
                'total_income_generated': float(order.total_income_generated),
                'estimated_total_income': float(order.estimated_total_income),
                'status':                 order.status,
                'purchase_date':          order.purchase_date.strftime('%Y-%m-%d %H:%M:%S'),
            },
            'settlements': [
                {
                    'id':              s.id,
                    'settlement_date': s.settlement_date.strftime('%Y-%m-%d'),
                    'amount':          float(s.amount),
                    'day_number':      s.day_number,
                    'is_paid':         s.is_paid,
                }
                for s in settlements
            ],
        })
    except Order.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Order not found'}, status=404)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@require_http_methods(["GET"])
def api_notifications(request):
    unread_only   = request.GET.get('unread_only', 'false') == 'true'
    notifications = Notification.objects.filter(
        Q(user=request.user) | Q(is_broadcast=True)
    ).order_by('-created_at')
    if unread_only:
        notifications = notifications.filter(is_read=False)
    notifications = notifications[:50]
    return JsonResponse({
        'success': True,
        'notifications': [
            {
                'id':           n.id,
                'title':        n.title,
                'message':      n.message,
                'type':         n.notification_type,
                'is_read':      n.is_read,
                'is_important': n.is_important,
                'created_at':   n.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'image_url':    n.image.url if n.image else None,
                'link_url':     n.link_url,
            }
            for n in notifications
        ],
        'unread_count': Notification.objects.filter(
            Q(user=request.user) | Q(is_broadcast=True), is_read=False
        ).count(),
    })


@require_POST
def api_notification_mark_read(request, notification_id):
    try:
        notification = Notification.objects.get(
            Q(id=notification_id),
            Q(user=request.user) | Q(is_broadcast=True)
        )
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save()
        return JsonResponse({'success': True, 'message': 'Notification marked as read'})
    except Notification.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Notification not found'}, status=404)


@require_http_methods(["GET"])
def api_products_list(request):
    profile = get_or_create_profile(request.user)
    if not profile:
        return JsonResponse({'success': False, 'message': 'Error loading profile'}, status=500)
    products = InvestmentProduct.objects.filter(
        is_active=True, vip_required__lte=profile.vip_level
    ).select_related('category').order_by('vip_required', 'price')
    return JsonResponse({'success': True, 'products': [p.as_dict() for p in products]})


@require_POST
def api_product_purchase(request):
    try:
        data       = json.loads(request.body)
        product_id = data.get('product_id')
        quantity   = data.get('quantity', 1)

        if not product_id:
            return JsonResponse({'success': False, 'message': 'Product ID is required'}, status=400)
        try:
            quantity = int(quantity)
            if quantity < 1:
                raise ValueError()
        except ValueError:
            return JsonResponse({'success': False, 'message': 'Invalid quantity'}, status=400)

        try:
            product = InvestmentProduct.objects.get(id=product_id, is_active=True)
        except InvestmentProduct.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Product not found or not available'}, status=404)

        profile = get_or_create_profile(request.user)
        if not profile:
            return JsonResponse({'success': False, 'message': 'Error loading profile'}, status=500)

        if profile.vip_level < product.vip_required:
            return JsonResponse({'success': False, 'message': f'VIP Level {product.vip_required} required'}, status=400)
        if quantity > product.max_shares:
            return JsonResponse({'success': False, 'message': f'Maximum {product.max_shares} shares allowed'}, status=400)

        total_amount = product.price * quantity

        # ✅ Check combined recharge + withdrawal balance
        total_available = profile.recharge_balance + profile.withdrawal_balance
        if total_available < total_amount:
            return JsonResponse({
                'success': False,
                'message': (
                    f'Insufficient balance. '
                    f'Required: UGX {total_amount:,.2f}, '
                    f'Available: UGX {total_available:,.2f}'
                )
            }, status=400)

        start_date   = timezone.now().date()
        end_date     = start_date + timedelta(days=product.duration_days)
        order_number = f"ORD{timezone.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}"
        daily_income = product.daily_earning * quantity

        order = Order.objects.create(
            user=request.user, product=product, order_number=order_number,
            quantity=quantity, total_amount=total_amount, daily_income=daily_income,
            estimated_total_income=product.total_return * quantity,
            duration_days=product.duration_days, days_remaining=product.duration_days,
            start_date=start_date, end_date=end_date,
            next_settlement_date=start_date + timedelta(days=1), status='normal'
        )

        # ✅ Deduct recharge_balance first, then withdrawal_balance
        balance_before_recharge    = profile.recharge_balance
        balance_before_withdrawal  = profile.withdrawal_balance

        if profile.recharge_balance >= total_amount:
            profile.recharge_balance -= total_amount
            balance_type = 'recharge_balance'
        else:
            remainder = total_amount - profile.recharge_balance
            profile.recharge_balance   = Decimal('0.00')
            profile.withdrawal_balance -= remainder
            balance_type = 'recharge_balance+withdrawal_balance'

        profile.total_investment += total_amount
        profile.total_orders     += 1
        profile.save()

        # ✅ total_investment just changed — recheck which VIP tier that
        # qualifies for and persist it. Without this, vip_level never moves
        # off 0 no matter how much a user invests.
        leveled_up, old_level, new_level = profile.update_vip_level()
        if leveled_up:
            Notification.objects.create(
                user=request.user,
                title='VIP Level Upgraded! 🎉',
                message=(
                    f'Congratulations! Your total investment has upgraded you '
                    f'from VIP {old_level} to VIP {new_level}.'
                ),
                notification_type='vip_upgrade',
                is_important=True,
            )

        transaction_number = f"TXN{timezone.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}"
        Transaction.objects.create(
            user=request.user, transaction_number=transaction_number,
            transaction_type='buy_product', amount=-total_amount,
            balance_type=balance_type,
            balance_before=balance_before_recharge + balance_before_withdrawal,
            balance_after=profile.recharge_balance + profile.withdrawal_balance,
            description=f'Purchased {product.name} x{quantity}',
            reference_id=order.order_number, status='completed'
        )

        for day in range(1, product.duration_days + 1):
            Settlement.objects.create(
                order=order, user=request.user,
                settlement_date=start_date + timedelta(days=day),
                amount=daily_income, day_number=day, is_paid=False
            )

        return JsonResponse({
            'success': True,
            'message': 'Product purchased successfully',
            'order': {
                'order_number':  order.order_number,
                'product_name':  product.name,
                'total_amount':  float(total_amount),
                'daily_income':  float(daily_income),
                'duration_days': product.duration_days,
            },
            'vip_upgraded': leveled_up,
            'new_vip_level': new_level,
        })
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@require_http_methods(["GET"])
def api_vip_info(request):
    profile = get_or_create_profile(request.user)
    if not profile:
        return JsonResponse({'success': False, 'message': 'Error loading profile'}, status=500)

    try:
        current_vip = VIPLevel.objects.get(level=profile.vip_level)
    except VIPLevel.DoesNotExist:
        current_vip = None
    try:
        next_vip = VIPLevel.objects.get(level=profile.vip_level + 1)
    except VIPLevel.DoesNotExist:
        next_vip = None

    vip_progress_percentage = 0
    if next_vip:
        current_threshold = current_vip.required_investment if current_vip else Decimal('0')
        progress = profile.total_investment - current_threshold
        required = next_vip.required_investment - current_threshold
        if required > 0:
            vip_progress_percentage = float(progress / required * 100)

    return JsonResponse({
        'success':       True,
        'current_level': profile.vip_level,
        'current_vip': {
            'level':               current_vip.level,
            'name':                current_vip.name,
            'required_investment': float(current_vip.required_investment),
            'commission_rate':     float(current_vip.commission_rate),
            'withdrawal_fee_rate': float(current_vip.withdrawal_fee_rate),
        } if current_vip else None,
        'next_vip': {
            'level':               next_vip.level,
            'name':                next_vip.name,
            'required_investment': float(next_vip.required_investment),
        } if next_vip else None,
        'total_investment':    float(profile.total_investment),
        'progress_percentage': vip_progress_percentage,
    })


# ==================== WEBHOOK ====================

@csrf_exempt
@require_POST
def webhook_payment_callback(request):
    try:
        data            = json.loads(request.body)
        transaction_id  = data.get('transaction_id')
        status          = data.get('status')
        recharge_number = data.get('reference')

        if not all([transaction_id, status, recharge_number]):
            return JsonResponse({'error': 'Missing required fields'}, status=400)

        try:
            recharge = Recharge.objects.get(recharge_number=recharge_number)
        except Recharge.DoesNotExist:
            return JsonResponse({'error': 'Recharge not found'}, status=404)

        if status == 'success' and recharge.status == 'pending':
            recharge.external_transaction_id = transaction_id
            recharge.status                  = 'completed'
            recharge.completed_at            = timezone.now()
            recharge.save()

            profile = recharge.user.profile
            profile.recharge_balance += recharge.amount
            profile.total_recharged  += recharge.amount
            profile.save()

            transaction_number = f"TXN{timezone.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}"
            Transaction.objects.create(
                user=recharge.user, transaction_number=transaction_number,
                transaction_type='recharge', amount=recharge.amount,
                balance_type='recharge_balance',
                balance_before=profile.recharge_balance - recharge.amount,
                balance_after=profile.recharge_balance,
                description=f'Recharge via {recharge.payment_method}',
                reference_id=recharge.recharge_number, status='completed'
            )
            Notification.objects.create(
                user=recharge.user, title='Recharge Confirmed',
                message=f'Your recharge of UGX {recharge.amount:,.2f} has been confirmed.',
                notification_type='recharge_confirmed'
            )
        elif status == 'failed':
            recharge.status = 'failed'
            recharge.save()

        return JsonResponse({'success': True, 'message': 'Webhook processed'})
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({'error': str(e)}, status=500)


# ==================== UTILITY ====================

def get_user_dashboard_context(user):
    profile = get_or_create_profile(user)
    if not profile:
        return {}
    try:
        vip_level = VIPLevel.objects.get(level=profile.vip_level)
    except VIPLevel.DoesNotExist:
        vip_level = None
    try:
        next_vip = VIPLevel.objects.get(level=profile.vip_level + 1)
    except VIPLevel.DoesNotExist:
        next_vip = None
    return {
        'profile':              profile,
        'vip_level':            vip_level,
        'next_vip':             next_vip,
        'active_orders':        Order.objects.filter(user=user, status='normal'),
        'finished_orders':      Order.objects.filter(user=user, status='finish'),
        'recent_transactions':  Transaction.objects.filter(user=user).order_by('-created_at')[:5],
        'unread_notifications': Notification.objects.filter(
            Q(user=user) | Q(is_broadcast=True), is_read=False
        ).count(),
    }


# ==================== PASSWORD RESET ====================

def password_reset_request(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        if not email:
            messages.error(request, 'Please enter your email address.')
            return render(request, 'password_reset_request.html')
        try:
            user = User.objects.get(email__iexact=email)
            PasswordResetCode.objects.filter(user=user, is_used=False).update(is_used=True)
            code = PasswordResetCode.generate_code()
            PasswordResetCode.objects.create(user=user, code=code)
            send_mail(
                subject='Your Agnicoe Eagle Password Reset Code',
                message=(
                    f'Hello {user.username},\n\n'
                    f'Your password reset verification code is:\n\n'
                    f'    {code}\n\n'
                    f'This code expires in 15 minutes. Do not share it with anyone.\n\n'
                    f'If you did not request this, please ignore this email.\n\n'
                    f'— Agnicoe Eagle Support'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email], fail_silently=False,
            )
        except User.DoesNotExist:
            pass
        request.session['reset_email'] = email
        messages.success(request, 'If that email is registered, a 6-digit code has been sent.')
        return redirect('password_reset_verify')
    return render(request, 'password_reset_request.html')


def password_reset_verify(request):
    email = request.session.get('reset_email')
    if not email:
        return redirect('password_reset_request')
    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        if not code or len(code) != 6 or not code.isdigit():
            messages.error(request, 'Please enter the 6-digit code from your email.')
            return render(request, 'password_reset_verify.html', {'email': email})
        try:
            user       = User.objects.get(email__iexact=email)
            reset_code = PasswordResetCode.objects.filter(
                user=user, code=code, is_used=False
            ).latest('created_at')
            if not reset_code.is_valid():
                messages.error(request, 'This code has expired. Please request a new one.')
                return render(request, 'password_reset_verify.html', {'email': email})
            request.session['reset_code_id'] = reset_code.id
            return redirect('password_reset_confirm')
        except (User.DoesNotExist, PasswordResetCode.DoesNotExist):
            messages.error(request, 'Invalid code. Please try again.')
            return render(request, 'password_reset_verify.html', {'email': email})
    return render(request, 'password_reset_verify.html', {'email': email})


def password_reset_confirm(request):
    email         = request.session.get('reset_email')
    reset_code_id = request.session.get('reset_code_id')
    if not email or not reset_code_id:
        return redirect('password_reset_request')
    if request.method == 'POST':
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        if len(password1) < 6:
            messages.error(request, 'Password must be at least 6 characters.')
            return render(request, 'password_reset_confirm.html')
        if password1 != password2:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'password_reset_confirm.html')
        try:
            reset_code = PasswordResetCode.objects.get(id=reset_code_id, is_used=False)
            if not reset_code.is_valid():
                messages.error(request, 'Session expired. Please start again.')
                return redirect('password_reset_request')
            user = reset_code.user
            user.set_password(password1)
            user.save()
            reset_code.is_used = True
            reset_code.save()
            del request.session['reset_email']
            del request.session['reset_code_id']
            messages.success(request, 'Password reset successful! You can now log in.')
            return redirect('login')
        except PasswordResetCode.DoesNotExist:
            messages.error(request, 'Invalid session. Please start again.')
            return redirect('password_reset_request')
    return render(request, 'password_reset_confirm.html')


def password_reset_resend(request):
    email = request.session.get('reset_email')
    if not email:
        return redirect('password_reset_request')
    try:
        user = User.objects.get(email__iexact=email)
        PasswordResetCode.objects.filter(user=user, is_used=False).update(is_used=True)
        code = PasswordResetCode.generate_code()
        PasswordResetCode.objects.create(user=user, code=code)
        send_mail(
            subject='Your Agnicoe Eagle Password Reset Code (Resent)',
            message=(
                f'Hello {user.username},\n\n'
                f'Your new password reset code is:\n\n'
                f'    {code}\n\n'
                f'This code expires in 15 minutes.\n\n'
                f'— Agnicoe Eagle Support'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email], fail_silently=False,
        )
    except User.DoesNotExist:
        pass
    messages.success(request, 'A new code has been sent to your email.')
    return redirect('password_reset_verify')