from django.shortcuts import render

# Create your views here.
# services/views.py
import random
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import SupportTicket, SupportMessage, SupportMessageImage


# ── Bot responses ─────────────────────────────────────────────────────────────
BOT_REPLIES = {
    'deposit':    "For deposit issues, please share your transaction ID and amount — our team will investigate within 24 hours.",
    'recharge':   "For recharge issues, share your transaction details and payment method and we'll resolve it quickly.",
    'withdraw':   "Withdrawal requests are processed within 24–48 hours. If yours is delayed, please share your withdrawal number.",
    'withdrawal': "Withdrawal requests are processed within 24–48 hours. If yours is delayed, please share your withdrawal number.",
    'account':    "For account issues, please describe the problem clearly and our team will assist you shortly.",
    'password':   "To reset your transaction password, visit the Settings page. For login password, use the Forgot Password link.",
    'vip':        "VIP upgrades happen automatically once your total investment reaches the required threshold.",
    'invest':     "You can browse and invest in products from the Store page. Each product shows daily earnings and duration.",
    'product':    "All available products are on the Store page. Filter by category to find the right plan for you.",
    'commission': "Commissions are earned when your referrals invest. Track them in the Invitation section.",
    'referral':   "Share your referral link from the Invitation page to earn commissions from friends who invest.",
    'proof':      "Thank you for uploading your proof. Our team will verify it and update your account within 24 hours.",
    'screenshot': "Thank you for the screenshot. Our support team will review it and get back to you shortly.",
    'hello':      "Hello! Welcome to Agnicoe Eagle Support. How can we help you today?",
    'hi':         "Hi there! How can I assist you today?",
    'help':       "I'm here to help! Please describe your issue and I'll do my best to assist you.",
}

FALLBACK_REPLIES = [
    "Thank you for your message. Our support team has been notified and will reply shortly.",
    "I've received your message. A customer service agent will respond as soon as possible.",
    "Got it! Our team is reviewing your request. Please allow up to 24 hours for a response.",
    "Thank you for reaching out. If this is urgent, please describe your issue in detail so we can prioritise.",
]

IMAGE_AUTO_REPLY = "Thank you for uploading your proof/screenshot. Our team has received it and will verify within 24 hours."


def get_bot_reply(message: str, has_images: bool) -> str:
    if has_images and not message:
        return IMAGE_AUTO_REPLY
    msg_lower = message.lower()
    for keyword, reply in BOT_REPLIES.items():
        if keyword in msg_lower:
            return reply
    if has_images:
        return IMAGE_AUTO_REPLY
    return random.choice(FALLBACK_REPLIES)


# ── Views ─────────────────────────────────────────────────────────────────────

@login_required
def services(request):
    ticket, _ = SupportTicket.objects.get_or_create(
        user=request.user,
        status__in=['open', 'pending'],
        defaults={'status': 'open'}
    )
    ticket.messages.filter(
        sender_type__in=['admin', 'bot'], is_read=False
    ).update(is_read=True)

    messages = ticket.messages.prefetch_related('images').all()
    return render(request, 'services.html', {
        'ticket':   ticket,
        'messages': messages,
    })


@login_required
@require_POST
def send_message(request):
    ticket, _ = SupportTicket.objects.get_or_create(
        user=request.user,
        status__in=['open', 'pending'],
        defaults={'status': 'open'}
    )

    text   = request.POST.get('message', '').strip()
    images = request.FILES.getlist('images')  # multiple images

    if not text and not images:
        return JsonResponse({'success': False, 'error': 'Empty message'}, status=400)

    # Validate image types
    allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    for img in images:
        if img.content_type not in allowed_types:
            return JsonResponse({'success': False, 'error': f'Invalid file type: {img.name}'}, status=400)
        if img.size > 10 * 1024 * 1024:  # 10MB limit per image
            return JsonResponse({'success': False, 'error': f'Image too large (max 10MB): {img.name}'}, status=400)

    # Save message
    user_msg = SupportMessage.objects.create(
        ticket=ticket, sender_type='user',
        user=request.user, message=text,
    )

    # Save all images
    saved_image_urls = []
    for img in images:
        msg_img = SupportMessageImage.objects.create(message=user_msg, image=img)
        saved_image_urls.append(msg_img.image.url)

    ticket.status = 'pending'
    ticket.save()

    # Bot reply — suppressed if admin replied recently
    recent = ticket.messages.order_by('-created_at')[:5]
    admin_replied_recently = any(m.sender_type == 'admin' for m in recent)

    bot_msg = None
    if not admin_replied_recently:
        bot_reply_text = get_bot_reply(text, bool(images))
        bot_msg = SupportMessage.objects.create(
            ticket=ticket, sender_type='bot', message=bot_reply_text,
        )

    return JsonResponse({
        'success': True,
        'user_message': {
            'id':          user_msg.id,
            'message':     user_msg.message,
            'images':      saved_image_urls,
            'sender_type': 'user',
            'created_at':  user_msg.created_at.strftime('%H:%M'),
        },
        'bot_reply': {
            'id':          bot_msg.id,
            'message':     bot_msg.message,
            'images':      [],
            'sender_type': 'bot',
            'created_at':  bot_msg.created_at.strftime('%H:%M'),
        } if bot_msg else None,
    })


@login_required
def poll_messages(request):
    since_id = int(request.GET.get('since_id', 0))
    ticket   = SupportTicket.objects.filter(
                 user=request.user, status__in=['open', 'pending']
               ).first()

    if not ticket:
        return JsonResponse({'success': True, 'messages': []})

    new_messages = ticket.messages.filter(
        id__gt=since_id, sender_type__in=['admin', 'bot']
    ).prefetch_related('images').order_by('created_at')

    new_messages.filter(is_read=False).update(is_read=True)

    return JsonResponse({
        'success': True,
        'messages': [
            {
                'id':          m.id,
                'message':     m.message,
                'images':      [i.image.url for i in m.images.all()],
                'sender_type': m.sender_type,
                'created_at':  m.created_at.strftime('%H:%M'),
            }
            for m in new_messages
        ],
    })