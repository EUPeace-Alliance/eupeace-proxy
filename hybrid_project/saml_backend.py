from djangosaml2.backends import Saml2Backend

class EupeaceSamlBackend(Saml2Backend):
    def authenticate(self, request, session_info=None, attribute_mapping=None, create_unknown_user=True, **kwargs):
        if not session_info or 'ava' not in session_info:
            return None

        ava = session_info['ava']
        
        # 1. Fallback to ensure the primary identity attribute exists
        # If eduPersonPrincipalName is missing, fall back to email to prevent djangosaml2 provisioning failures
        if 'eduPersonPrincipalName' not in ava and 'mail' in ava:
            ava['eduPersonPrincipalName'] = ava['mail']

        # 2. Delegate to the base class: apply SAML_ATTRIBUTE_MAPPING and provision/update user
        user = super().authenticate(
            request, 
            session_info=session_info, 
            attribute_mapping=attribute_mapping, 
            create_unknown_user=create_unknown_user, 
            **kwargs
        )
        
        # 3. Ensure the password is unusable if the user was just provisioned via SAML
        if user and not user.has_usable_password():
            user.set_unusable_password()
            user.save()
            
        # 4. Safely attach the IdP issuer to the user instance for login signal processing
        if user and session_info:
            user._saml_issuer = session_info.get('issuer')
            
        return user

    def _update_user(self, user, attributes, attribute_mapping, force_save=False):
        # Perform standard attribute mapping via parent method
        user = super()._update_user(user, attributes, attribute_mapping, force_save)
        
        from core.models import UserProfile

        # Ensure the user has a primary key before updating related profile
        if not user.pk:
            user.save()
            
        profile, created = UserProfile.objects.get_or_create(user=user)
        
        # European Student Identifier (ESI) - checks both readable name and raw OID
        esi_list = attributes.get('schacPersonalUniqueCode') or attributes.get('urn:oid:1.3.6.1.4.1.25178.1.2.14') or []
        if esi_list:
            profile.esi = esi_list[0]
            
        # Scoped Institutional Affiliations
        affiliation_list = attributes.get('eduPersonScopedAffiliation') or attributes.get('urn:oid:1.3.6.1.4.1.5923.1.1.1.9') or []
        if affiliation_list:
            profile.affiliation = ", ".join(affiliation_list)
            
        # Home Organization (derived from schacHomeOrganization or scope of ePPN / affiliation)
        org_list = attributes.get('schacHomeOrganization') or attributes.get('urn:oid:1.3.6.1.4.1.25178.1.2.9') or []
        if org_list:
            profile.home_organization = org_list[0]
        else:
            eppn_list = attributes.get('eduPersonPrincipalName') or attributes.get('urn:oid:1.3.6.1.4.1.5923.1.1.1.6') or []
            if eppn_list and '@' in eppn_list[0]:
                profile.home_organization = eppn_list[0].split('@')[-1]
            elif affiliation_list and '@' in affiliation_list[0]:
                profile.home_organization = affiliation_list[0].split('@')[-1]
            
        profile.save()
        return user