from oauth2_provider.oauth2_validators import OAuth2Validator
from django.conf import settings

class CustomOAuth2Validator(OAuth2Validator):
    def get_additional_claims(self, request):
        claims = super().get_additional_claims(request)
        user = request.user
        
        claims['email'] = user.email
        claims['eppn'] = user.username 
        
        # djangosaml2 saves the assertion details in the session
        session_info = request.session.get('saml2_session_info', {})
        authn_info = session_info.get('authn_info', [])
        
        # Check if the IdP actually responded using the MFA profile
        used_mfa = False
        for info in authn_info:
            authn_class, _, _ = info
            if authn_class == settings.REFEDS_MFA_PROFILE:
                used_mfa = True
                break
                
        # Populate the 'acr' claim (Authentication Context Class Reference)
        if used_mfa:
            claims['acr'] = settings.REFEDS_MFA_PROFILE
        else:
            claims['acr'] = 'urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport' # Standard authentication

        return claims
    def get_additional_claims(self, request):
        claims = super().get_additional_claims(request)
        user = request.user
        
        # Entitlements array (AARC permissions)
        entitlements = []
        
        # Check if it is a Guest with a valid profile
        if hasattr(user, 'guest_profile'):
            if user.guest_profile.valid_until > timezone.now():
                # Standard URN to represent academic affiliation
                entitlements.append("urn:mace:eupeace.eu:entitlement:guest")
                
        claims['eduperson_entitlement'] = entitlements
        return claims