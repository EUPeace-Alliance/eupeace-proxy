from oauth2_provider.oauth2_validators import OAuth2Validator

class CustomOAuth2Validator(OAuth2Validator):
    # We must declare to which OIDC scope our custom attributes belong.
    # If they are not mapped here, django-oauth-toolkit will discard them during token generation!
    oidc_claim_scope = OAuth2Validator.oidc_claim_scope.copy()
    oidc_claim_scope.update({
        "affiliation": "profile",
        "home_organization": "profile",
        "esi_code": "profile",
    })

    def get_additional_claims(self, request):
        user = request.user
        
        claims = {
            "given_name": user.first_name or "",
            "family_name": user.last_name or "",
            "name": f"{user.first_name} {user.last_name}".strip(),
            "email": user.email or "",
            "preferred_username": user.username or "",
            "email_verified": True,
        }
        
        # Extract profile data and pass it to the external application.
        if hasattr(user, 'profile'):
            claims["affiliation"] = user.profile.affiliation or ""
            claims["home_organization"] = user.profile.home_organization or ""
            claims["esi_code"] = user.profile.esi or ""
            
        return claims