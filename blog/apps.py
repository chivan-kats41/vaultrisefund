"""
Django App Configuration for Blog System
File: blog/apps.py
"""

from django.apps import AppConfig


class BlogConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'blog'
    verbose_name = 'Blog Management System'
    
    def ready(self):
        """
        Import signal handlers when Django starts.
        This ensures all signals are connected and working.
        """
        import blog.signals  # noqa
        print("✓ Blog signals registered successfully")

### **2. Smart Features:**
'''
✨ **Anti-Spam Protection:**
- Detects users posting >5 times per hour
- Can be extended to auto-block spammers

✨ **Smart Rewards:**
- Base: 5,000 UGX
- +1,000 UGX per image (max 3)
- +1,000 UGX for 200+ chars
- +2,000 UGX for 500+ chars
- Max: 50,000 UGX

✨ **Auto-Moderation:**
- 3 reports = automatic rejection
- Admins notified immediately

✨ **Engagement Milestones:**
- Strategic notifications at key thresholds
- Encourages continued engagement

## 📊 **Complete Workflow:**
```
USER POSTS:
1. Submit → Status: Pending
2. Signal: Notify admins + user
3. Auto-generate slug

ADMIN APPROVES:
4. Set reward amount
5. Click "Approve & pay rewards"
6. Signal: Create reward record
7. Signal: Notify user

REWARD PAYMENT:
8. Mark reward as paid
9. Signal: Credit balance
10. Signal: Create transaction
11. Signal: Notify user
12. User sees money in account! 💰

ENGAGEMENT:
- User comments → Notify post author
- User likes → Count milestone notifications
- Views tracked → Notify on milestones
'''