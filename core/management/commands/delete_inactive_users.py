from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

class Command(BaseCommand):
    help = 'Deletes users inactive for over 12 months for GDPR compliance'

    def handle(self, *args, **options):
        User = get_user_model()
        # Calculate the cutoff date (exactly 1 year ago)
        cutoff_date = timezone.now() - timedelta(days=365)
        
        # Filter users (excluding superusers/admins for security)
        inactive_users = User.objects.filter(
            last_login__lt=cutoff_date, 
            is_superuser=False
        )
        
        count = inactive_users.count()
        inactive_users.delete()
        
        self.stdout.write(f"GDPR Compliance: {count} inactive profiles deleted.")