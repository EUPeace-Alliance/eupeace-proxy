from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout, login
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from urllib.parse import quote
from hybrid_project.saml_backend import EupeaceSamlBackend
from djangosaml2.views import LoginView
from oauth2_provider.views import AuthorizationView
from .models import GuestInvitation, AllianceService, IdentityProvider, AuditLog, get_client_ip, UserFavoriteService
from .forms import GuestInvitationForm
from django.http import HttpResponse, JsonResponse
from django.db.models import Q
from django.core.paginator import Paginator

@never_cache
def custom_logout(request):
    """
    Hybrid logout management:
    - If the user has a SAML session, use global Single Logout.
    - If the user is a local user (e.g., superuser), use standard Django logout.
    """
    if '_saml2_subject_id' in request.session:
        return redirect('saml2_logout')
    
    logout(request)
    return redirect('/') 


@never_cache
def wayf_view(request):
    """Discovery page view (WAYF)"""
    next_url = request.GET.get('next')

    # Save the 'next' parameter in the session (e.g., OAuth2 / PKCE) to prevent 
    # the Identity Provider from truncating the querystring if it exceeds the 80-byte RelayState limit.
    if next_url:
        request.session['oauth2_next_url'] = next_url

    if request.user.is_authenticated:
        saved_next = request.session.pop('oauth2_next_url', None)
        target = saved_next or next_url or 'dashboard'
        return redirect(target)
        
    selected_idp = request.GET.get('idp') or request.GET.get('entityID')
    if selected_idp:
        return redirect(f'/saml2/login/?idp={selected_idp}')

    return_url = request.build_absolute_uri('/')
    sp_entity_id = settings.SAML_CONFIG['entityid']
    
    central_ds_url = (
        f"https://service.seamlessaccess.org/ds/"
        f"?entityID={quote(sp_entity_id)}"
        f"&return={quote(return_url)}"
    )

    from .models import IdentityProvider
    active_idps = IdentityProvider.objects.filter(is_active=True)

    return render(request, 'login.html', {
        'central_ds_url': central_ds_url,
        'active_idps': active_idps 
    })


class CustomSAML2LoginView(LoginView):
    """Custom SAML view to request MFA only from IdPs that support it, while allowing invited guests from any eduGAIN IdP"""
    def get_authn_request_kwargs(self, request, config, idp_entityid):
        kwargs = super().get_authn_request_kwargs(request, config, idp_entityid)

        # Check if the user has a valid pending guest invitation
        pending_token = request.session.get('pending_invite_token')
        is_valid_guest = False
        if pending_token:
            try:
                invite = GuestInvitation.objects.get(token=pending_token)
                is_valid_guest = invite.is_valid()
            except (GuestInvitation.DoesNotExist, ValueError):
                pass

        try:
            idp = IdentityProvider.objects.get(entity_id=idp_entityid, is_active=True)
            # If the IdP supports MFA according to the database, inject the REFEDS context
            if idp.supports_mfa:
                kwargs['requested_authn_context'] = {
                    'authn_context_class_ref': [getattr(settings, 'REFEDS_MFA_PROFILE', 'https://refeds.org/profile/mfa')],
                    'comparison': 'exact'
                }
        except IdentityProvider.DoesNotExist:
            is_partner_or_check = idp_entityid in getattr(settings, 'EUPEACE_PARTNER_IDPS', [])
            if not is_valid_guest and not is_partner_or_check:
                raise PermissionDenied("The selected Identity Provider is not authorized or has been deactivated.")

        return kwargs
        


def custom_permission_denied_view(request, exception=None):
    return render(request, '403.html', status=403)


def redeem_invite_view(request, token):
    invitation = get_object_or_404(GuestInvitation, token=token)
    
    if not invitation.is_valid():
        return render(request, '403.html', {'message': 'This invitation has expired or has already been used.'})
    if request.user.is_authenticated:
        from .models import GuestProfile
        from datetime import timedelta

        GuestProfile.objects.update_or_create(
            user=request.user,
            defaults={
                'invited_by': invitation.inviter,
                'valid_until': timezone.now() + timedelta(days=invitation.duration_days)
            }
        )

        invitation.is_used = True
        invitation.save()
        
        messages.success(request, f"Invitation redeemed successfully for {request.user.email}!")
        return redirect('dashboard')
        
    # Save token in session: it will be read by the Signal after SAML login
    request.session['pending_invite_token'] = str(token)
    
    return_url = request.build_absolute_uri('/')
    sp_entity_id = settings.SAML_CONFIG['entityid']
    
    central_ds_url = (
        f"https://service.seamlessaccess.org/ds/"
        f"?entityID={quote(sp_entity_id)}"
        f"&return={quote(return_url)}"
    )
    
    context = {
        'guest_email': invitation.guest_email,
        'duration': invitation.duration_days,
        'central_ds_url': central_ds_url
    }
    
    return render(request, 'guest_welcome.html', context)

@login_required
@never_cache
def create_invitation_view(request):
    
    if hasattr(request.user, 'guest_profile'):
        messages.error(request, 'Guests are not authorized to create invitations.')
        return redirect('dashboard')

    if request.method == 'POST':
        form = GuestInvitationForm(request.POST)
        if form.is_valid():
            invitation = form.save(commit=False)
            invitation.inviter = request.user
            invitation.save()

            invite_url = request.build_absolute_uri(
                reverse('redeem_invite', args=[invitation.token])
            )

            subject = "EUPEACE: You have been invited as a Guest"
            
            inviter_name = f"{request.user.first_name} {request.user.last_name}".strip()
            inviter_display = f"{inviter_name} ({request.user.email})" if inviter_name else request.user.email

            message = (
                f"Dear User,\n\n"
                f"You have been invited by {inviter_display} to access the EUPEACE alliance services securely.\n\n"
                f"To register your identity via eduGAIN, please click the following link:\n"
                f"{invite_url}\n\n"
                f"Note: This link is strictly personal and will expire in {invitation.duration_days} days.\n\n"
                f"The EUPEACE support team."
            )
            
            from_email_header = getattr(settings, 'DEFAULT_FROM_EMAIL', 'EUPeace Proxy Identifier <noreply@eupeace.eu>')
            
            try:
                send_mail(
                    subject,
                    message,
                    from_email_header, 
                    [invitation.guest_email],
                    fail_silently=False,
                )
                messages.success(request, f"The invitation for {invitation.guest_email} has been generated and sent successfully.")
            except Exception as e:
                messages.error(request, "The invitation has been saved, but there was an error sending the email (Firewall/SMTP timeout).")
        else:
            messages.error(request, "The submitted email address was invalid. Please try again.")

        return redirect('dashboard')

    return redirect('dashboard')


@login_required
@never_cache
@require_POST
def revoke_invitation_view(request, token):
    invitation = get_object_or_404(GuestInvitation, token=token, inviter=request.user)
    
    if not invitation.is_used:
        guest_email = invitation.guest_email
        invitation.delete()
        messages.success(request, f"The invitation for {guest_email} has been revoked and deleted.")
    else:
        messages.error(request, "Unable to revoke this invitation because it has already been used.")
        
    return redirect('dashboard')


@login_required
@never_cache
@require_POST
def toggle_favorite_service(request, service_id):
    """
    Toggle a service in the user's favorites.
    Supports asynchronous requests (JSON response) and fallback to redirect.
    """
    service = get_object_or_404(AllianceService, id=service_id, is_active=True)
    fav = UserFavoriteService.objects.filter(user=request.user, service=service).first()
    if fav:
        fav.delete()
        is_favorite = False
    else:
        UserFavoriteService.objects.create(user=request.user, service=service)
        is_favorite = True

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('accept', ''):
        return JsonResponse({
            'status': 'ok',
            'service_id': service.id,
            'is_favorite': is_favorite,
        })

    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))


@login_required
@never_cache
def dashboard(request):
    """
    Dashboard view that manages both services and invitations,
    including search, provider filtering, favorites filtering, and pagination.
    """
    # Resume any pending OAuth2 flow
    oauth2_next = request.session.pop('oauth2_next_url', None)
    if oauth2_next:
        return redirect(oauth2_next)

    user = request.user
    
    sent_invitations = GuestInvitation.objects.filter(inviter=user).order_by('-created_at')

    services_base = AllianceService.objects.filter(is_active=True)
    
    if user.is_superuser:
        user_role = 'ADMIN'
    else:
        user_role = 'GUEST'
        if hasattr(user, 'profile') and user.profile.affiliation:
            affil = user.profile.affiliation.lower()
            if 'student' in affil:
                user_role = 'STUDENT'
            elif 'staff' in affil or 'faculty' in affil or 'member' in affil:
                user_role = 'STAFF'

        if user_role == 'STUDENT':
            services_base = services_base.filter(visibility__in=['ALL', 'STUDENT'])
        elif user_role == 'STAFF':
            services_base = services_base.filter(visibility__in=['ALL', 'STAFF'])
        else:
            services_base = services_base.filter(visibility='ALL')

    search_query = request.GET.get('q', '')
    provider_filter = request.GET.get('provider', '')
    favorites_only = request.GET.get('favorites', '') == '1'

    # Retrieve all favorite service IDs for the current user in a single indexed query
    user_favorite_ids = set(
        UserFavoriteService.objects.filter(user=user).values_list('service_id', flat=True)
    )

    if favorites_only:
        services_base = services_base.filter(id__in=user_favorite_ids)

    if search_query:
        services_base = services_base.filter(
            Q(name__icontains=search_query) | Q(description__icontains=search_query)
        )
    
    if provider_filter:
        services_base = services_base.filter(provider=provider_filter)

    paginator = Paginator(services_base.order_by('name'), 9)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    provider_colors = {
        'UNICAL': 'danger',    
        'MARBURG': 'primary',  
        'GIESSEN': 'success',  
        'LIMOGES': 'info',     
        'ZCU': 'warning',
        'SARAJEVO': 'secondary',
        'CUKUROVA': 'dark',
        'COMILLAS': 'primary',
        'MOSTAR': 'info',
    }

    context = {
        'page_obj': page_obj, 
        'user_role': user_role,
        'sent_invitations': sent_invitations,
        'providers': AllianceService.PROVIDER_CHOICES,
        'current_q': search_query,
        'current_provider': provider_filter,
        'favorites_only': favorites_only,
        'user_favorite_ids': user_favorite_ids,
        'total_favorites_count': len(user_favorite_ids),
        'provider_colors': provider_colors,
    }
    return render(request, 'dashboard.html', context)


class CustomAuthorizationView(AuthorizationView):
    """
    Custom OAuth2 Authorization View enforcing Gatekeeping / Access Control
    based on the user's institutional affiliation and the service's visibility policy.
    """
    def dispatch(self, request, *args, **kwargs):
        # 1. If not authenticated, allow standard OAuth2 flow to redirect to login (WAYF/SAML)
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)

        # 2. Extract client_id from query parameters (GET) or form data (POST)
        client_id = request.GET.get('client_id') or request.POST.get('client_id')
        if not client_id:
            # Let standard oauth2_provider handle missing client_id
            return super().dispatch(request, *args, **kwargs)

        # 3. Check if this OAuth2 application is linked to an AllianceService
        service = AllianceService.objects.filter(oauth_application__client_id=client_id).first()
        if not service:
            # No gatekeeping policy defined for this application: allow by default
            return super().dispatch(request, *args, **kwargs)

        # 4. Superusers bypass all restrictions
        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)

        # 5. Check if service is active
        if not service.is_active:
            self._log_access_denied(request, client_id)
            return render(request, 'access_denied.html', {
                'service': service,
                'reason': 'This service is currently disabled or undergoing maintenance.',
                'required_role': 'Active Service'
            }, status=403)

        # 6. Check Visibility policy against user affiliation
        visibility = service.visibility
        if visibility == 'ALL':
            return super().dispatch(request, *args, **kwargs)

        user_profile = getattr(request.user, 'profile', None)
        user_affiliation = (getattr(user_profile, 'affiliation', '') or '').lower()
        
        is_authorized = False
        required_role_display = "Authorized Users"

        if visibility == 'STUDENT':
            required_role_display = "Students only"
            if 'student' in user_affiliation:
                is_authorized = True
        elif visibility == 'STAFF':
            required_role_display = "Faculty & Staff only"
            staff_keywords = ['staff', 'faculty', 'employee', 'teacher', 'docent']
            if any(k in user_affiliation for k in staff_keywords):
                is_authorized = True

        if not is_authorized:
            self._log_access_denied(request, client_id)
            return render(request, 'access_denied.html', {
                'service': service,
                'reason': f"This service is restricted to {required_role_display}. Your institutional affiliation does not grant access.",
                'required_role': required_role_display,
                'user_affiliation': getattr(user_profile, 'affiliation', 'N/A') or 'None',
                'home_organization': getattr(user_profile, 'home_organization', 'N/A') or 'N/A',
            }, status=403)

        return super().dispatch(request, *args, **kwargs)

    def _log_access_denied(self, request, client_id):
        AuditLog.objects.create(
            eppn=getattr(request.user, 'username', 'UNKNOWN'),
            ip_address=get_client_ip(request),
            idp_entity_id=getattr(request.user, '_saml_issuer', None),
            service_client_id=client_id,
            status='FAILURE'
        )

