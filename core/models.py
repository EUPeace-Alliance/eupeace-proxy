import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_login_failed
from urllib.parse import urlparse, parse_qs

def default_expiration():
    # Registration link expiration
    return timezone.now() + timedelta(days=7)

class GuestInvitation(models.Model):
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    
    inviter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_invites')
    guest_email = models.EmailField()
    
    # Account validity duration (e.g., 6 months = 180 days)
    duration_days = models.IntegerField(default=180)
    
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=default_expiration)
    is_used = models.BooleanField(default=False)

    def is_valid(self):
        return not self.is_used and self.expires_at > timezone.now()

class GuestProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='guest_profile')
    invited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    # Expiration of the Guest role (access rights, not the invitation)
    valid_until = models.DateTimeField()

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    esi = models.CharField(max_length=255, blank=True, null=True)
    affiliation = models.CharField(max_length=255, blank=True, null=True)
    home_organization = models.CharField(max_length=255, blank=True, null=True)
    
    @property
    def formatted_esi(self):
        if self.esi and self.esi.startswith('urn:schac:personalUniqueCode:'):
            parts = self.esi.split(':')
            if len(parts) >= 7:
                domain = parts[4]
                role = parts[5].capitalize()
                user_id = parts[6]
                return f"{user_id} <span class='text-muted small'>({role}, {domain})</span>"
        return f"<code class='bg-light text-dark px-2 py-1 rounded border'>{self.esi}</code>"

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

class AllianceService(models.Model):
    VISIBILITY_CHOICES = [
        ('ALL', 'All (Students, Staff and Guest)'),
        ('STUDENT', 'Students Only'),
        ('STAFF', 'Staff and Faculty Only'),
    ]
    
    PROVIDER_CHOICES = [
        ('UNICAL', 'Università della Calabria'),
        ('MARBURG', 'Philipps-Universität Marburg'),
        ('GIESSEN', 'Justus-Liebig-Universität Giessen'),
        ('LIMOGES', 'Université de Limoges'),
        ('ZCU', 'University of West Bohemia'),
        ('SARAJEVO', 'University of Sarajevo'),
        ('CUKUROVA', 'Çukurova University'),
        ('COMILLAS', 'Universidad Pontificia Comillas'),
        ('MOSTAR', 'University of Mostar'),
    ]

    name = models.CharField(max_length=150, verbose_name="Service name")
    description = models.TextField(blank=True, verbose_name="Brief Description")
    url = models.URLField(verbose_name="Service URL")
    # We use a logo URL to avoid complex media volume configurations on Docker at this stage
    logo_url = models.URLField(blank=True, null=True, verbose_name="Logo URL (e.g., link to the image hosted on the service's website)")
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default='ALL')
    is_active = models.BooleanField(default=True, verbose_name="Service Active")
    
    provider = models.CharField(
        max_length=50, 
        choices=PROVIDER_CHOICES, 
        default='UNICAL',
        verbose_name="Providing University"
    )

    oauth_application = models.OneToOneField(
        'oauth2_provider.Application',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alliance_service',
        verbose_name="Linked OAuth2 Application",
        help_text="Optional link to an OAuth2 application (e.g. Moodle). If linked, OAuth2 authorization requests will enforce the visibility policy."
    )

    def __str__(self):
        return self.name



class UserFavoriteService(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorite_services')
    service = models.ForeignKey(AllianceService, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "User Favorite Service"
        verbose_name_plural = "User Favorite Services"
        unique_together = ('user', 'service')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.service.name}"



class IdentityProvider(models.Model):
    name = models.CharField(max_length=150, verbose_name="Identity Provider Name")
    short_code = models.CharField(max_length=50, unique=True, help_text="Es. UNICAL, MARBURG")
    entity_id = models.CharField(
        max_length=500, 
        unique=True, 
        verbose_name="Entity ID (URI/URL of the IdP metadata)",
        help_text="Can be a URL (e.g. https://...) or a URN (e.g. urn:mace:cru.fr:federation:unilim.fr)"
    )
    supports_mfa = models.BooleanField(default=False, verbose_name="Support MFA (REFEDS)")
    is_active = models.BooleanField(default=True, verbose_name="Active")
    logo_url = models.URLField(blank=True, null=True, verbose_name="Logo URL (Optional)")

    class Meta:
        verbose_name = "Identity Provider"
        verbose_name_plural = "Identity Providers"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({'MFA' if self.supports_mfa else 'No MFA'})"


class AuditLog(models.Model):
    STATUS_CHOICES = [
        ('SUCCESS', 'Success'),
        ('FAILURE', 'Failure'),
    ]

    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    eppn = models.CharField(max_length=255, verbose_name="User ePPN", db_index=True, blank=True, null=True)
    ip_address = models.GenericIPAddressField(verbose_name="IP Address", blank=True, null=True)
    idp_entity_id = models.CharField(verbose_name="IdP Entity ID", blank=True, null=True, max_length=500)
    service_client_id = models.CharField(max_length=255, verbose_name="Client ID", blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SUCCESS')
    
    class Meta:
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.timestamp}] {self.eppn} - {self.status} (IP: {self.ip_address})"

def extract_client_id_from_request(request):
    if not request:
        return None
    
    client_id = request.GET.get('client_id')
    if client_id:
        return client_id
    
    next_url = request.GET.get('next')
    if next_url:
        parsed_url = urlparse(next_url)
        qs = parse_qs(parsed_url.query)
        if 'client_id' in qs:
            return qs['client_id'][0]
    return None

def get_client_ip(request):
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    eppn = getattr(user, 'username', 'UNKNOWN')
    ip = get_client_ip(request)
    idp = getattr(user, '_saml_issuer', None)
    client_id = extract_client_id_from_request(request)
    
    AuditLog.objects.create(
        eppn=eppn,
        ip_address=ip,
        idp_entity_id=idp,
        service_client_id=client_id,
        status='SUCCESS'
    )

@receiver(user_login_failed)
def log_user_login_failed(sender, credentials, request, **kwargs):
    eppn = 'UNKNOWN'
    idp = None
    
    # If login occurred via SAML, credentials contain session_info
    session_info = credentials.get('session_info')
    if session_info and 'ava' in session_info:
        ava = session_info['ava']
        eppn = ava.get('eduPersonPrincipalName', [None])[0] or ava.get('mail', [None])[0] or 'UNKNOWN'
        idp = session_info.get('issuer')
    else:
        # For admin or local fallback
        eppn = credentials.get('username', 'UNKNOWN')
        
    ip = get_client_ip(request)
    client_id = extract_client_id_from_request(request)
    
    AuditLog.objects.create(
        eppn=eppn,
        ip_address=ip,
        idp_entity_id=idp,
        service_client_id=client_id,
        status='FAILURE'
    )
