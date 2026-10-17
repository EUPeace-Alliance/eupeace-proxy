from django.contrib.auth.signals import user_logged_in
from django.contrib.auth import logout
from django.dispatch import receiver
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import PermissionDenied
from datetime import timedelta
from .models import GuestInvitation, GuestProfile, IdentityProvider


# 1. Promote user if they have a pending invite
@receiver(user_logged_in)
def process_pending_invite(sender, request, user, **kwargs):
    token = request.session.get('pending_invite_token')
    
    if token:
        try:
            invitation = GuestInvitation.objects.get(token=token, is_used=False)
            if invitation.is_valid():
                GuestProfile.objects.update_or_create(
                    user=user,
                    defaults={
                        'invited_by': invitation.inviter,
                        'valid_until': timezone.now() + timedelta(days=invitation.duration_days)
                    }
                )
                invitation.is_used = True
                invitation.save()
                del request.session['pending_invite_token']
        except GuestInvitation.DoesNotExist:
            pass


# 2. Check if the user is authorized
@receiver(user_logged_in)
def enforce_access_policy(sender, request, user, **kwargs):
    if user.is_superuser or user.is_staff:
        return
    idp_entity_id = getattr(user, '_saml_issuer', None)
    
    if not idp_entity_id:
        session_info = request.session.get('saml2_session_info', {})
        idp_entity_id = session_info.get('issuer')

    if not idp_entity_id:
        logout(request)
        raise PermissionDenied("Invalid federated authentication.")

    # RULE A: Does the user come from an authorized Identity Provider in the DB?
    if (
        IdentityProvider.objects.filter(entity_id=idp_entity_id, is_active=True).exists()
        or idp_entity_id in getattr(settings, 'EUPEACE_PARTNER_IDPS', [])
    ):
        return

    # RULE B: Not from the alliance. Do they have a valid Guest profile?
    has_valid_guest = (
        hasattr(user, 'guest_profile') and 
        user.guest_profile.valid_until > timezone.now()
    )

    if has_valid_guest:
        return

    # RULE C: Unknown user.
    # Destroy Django session and raise 403 error.
    logout(request)
    raise PermissionDenied("You are not authorized.")

