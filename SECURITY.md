# 🔐 Security Architecture & Policies

The **EUPEACE Proxy Identifier** is an exposed node bridging international identity federations (**IDEM GARR**, **eduGAIN**) and alliance service providers. Security across SAML 2.0 transactions, OAuth2 / OIDC token issuance, session storage, and audit accountability is central to its operational design.

---

## 1. Cryptographic Signatures & SAML Encryption

The proxy establishes cryptographic trust through dedicated RSA keypairs (`private.key` and `public.cert`) stored in the secure `/certs/` directory.

### SAML Security Directives (`SAML_CONFIG`)
Located in `hybrid_project/settings.py`, the security directives dictate:
```python
'service': {
    'sp': {
        # AuthnRequests & LogoutRequests are digitally signed by our SP
        'authn_requests_signed': True,
        'logout_requests_signed': True,

        # Mandates that Identity Providers cryptographically sign Assertions
        'want_assertions_signed': True,

        # Responses are not required to be signed at response-level 
        # (assertion signing is enforced instead for broad IdP compatibility)
        'want_response_signed': False,

        # Modern cryptographic algorithms (SHA-256)
        'signing_algorithm': 'http://www.w3.org/2001/04/xmldsig-more#rsa-sha256',
        'digest_algorithm': 'http://www.w3.org/2001/04/xmlenc#sha256',
    }
}
```

### SAML Assertion Decryption (`encryption_keypairs`)
To support federated IdPs that encrypt SAML assertions, the SP declares decryption keypairs:
```python
'encryption_keypairs': [{
    'key_file': os.path.join(SAML_CERTS_DIR, 'private.key'),
    'cert_file': os.path.join(SAML_CERTS_DIR, 'public.cert'),
}],
```
This enables seamless decryption of assertions containing sensitive academic attributes.

---

## 2. Multi-Factor Authentication (REFEDS Profile)

To safeguard elevated services, the proxy natively supports the **REFEDS MFA Profile** (`https://refeds.org/profile/mfa`):

* **Dynamic DB Configuration:** The `IdentityProvider` database model contains a `supports_mfa` boolean attribute.
* **Context Injection:** When an IdP is marked with `supports_mfa=True`, `CustomSAML2LoginView` injects the REFEDS MFA `AuthnContextClassRef` into the outgoing `AuthnRequest`:
```python
kwargs['requested_authn_context'] = {
    'authn_context_class_ref': [getattr(settings, 'REFEDS_MFA_PROFILE', 'https://refeds.org/profile/mfa')],
    'comparison': 'exact'
}
```
* **Fallback Behavior:** If an IdP does not support REFEDS MFA, standard username/password authentication is requested without generating authentication context mismatches.

---

## 3. Dynamic Metadata Verification (IDEM MDX & Partner IdPs)

To prevent Man-in-the-Middle (MitM) attacks and IdP spoofing, metadata is retrieved via the **Metadata Query Protocol (MDX)**:
* **MDX Endpoint:** `https://mdx.idem.garr.it/edugain/`
* **X.509 Signature Validation:** The metadata response signature is cryptographically validated using the trusted IDEM signing certificate (`certs/idem-mdx-service-crt.pem`).
* **Partner IdP Whitelist:** Partner endpoints and diagnostic services (e.g., eduGAIN Access Check) are declared in `EUPEACE_PARTNER_IDPS` in `settings.py`.
* **Access Filtering:** `CustomSAML2LoginView` verifies whether the requesting IdP is an active database entity, an authorized partner IdP, or if the user possesses a valid pending guest invitation token. Unauthorized IdPs are rejected with HTTP 403.

---

## 4. OAuth2 / OpenID Connect Gatekeeping & Token Security

The proxy serves as an OAuth2 / OIDC Authorization Server for alliance applications (e.g., Moodle):

### Token Signing
* OIDC JSON Web Tokens (JWTs) are signed using a dedicated RSA key (`certs/oidc_rsa.key`).
* Client applications verify token authenticity using the public JWKS endpoint at `/o/.well-known/jwks.json`.

### Affiliation-Based Gatekeeping (`CustomAuthorizationView`)
When an application requests authorization (`/o/authorize/`), the custom view enforces gatekeeping policies:
1. **Service Status:** Checks if the associated `AllianceService` is active. Inactive services return HTTP 403 (`access_denied.html`).
2. **Role Verification:** Compares the user's institutional affiliation against `AllianceService.visibility`:
   * `STUDENT`: Requires `'student'` in the user's affiliation attribute.
   * `STAFF`: Requires `'staff'`, `'faculty'`, `'employee'`, `'teacher'`, or `'docent'`.
   * `ALL`: Grants access to all authenticated members and guests.
3. **Superuser Override:** Administrators can access any service for diagnostic purposes.
4. **Denial Audit:** Denied attempts render a user-friendly 403 page and generate a persistent `FAILURE` record in `AuditLog`.

### Claim Scoping & Minimization (`CustomOAuth2Validator`)
Custom OIDC claims (`affiliation`, `home_organization`, `esi_code`) are explicitly restricted to the `profile` scope. If the client does not request the `profile` scope, academic claims are omitted from the ID token.

---

## 5. Security Audit Logging & Accountability

Every authentication attempt and authorization gatekeeping decision is logged in the `AuditLog` table:

```python
class AuditLog(models.Model):
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    eppn = models.CharField(max_length=255, verbose_name="User ePPN", db_index=True, blank=True, null=True)
    ip_address = models.GenericIPAddressField(verbose_name="IP Address", blank=True, null=True)
    idp_entity_id = models.CharField(verbose_name="IdP Entity ID", blank=True, null=True, max_length=500)
    service_client_id = models.CharField(max_length=255, verbose_name="Client ID", blank=True, null=True)
    status = models.CharField(max_length=20, choices=[('SUCCESS', 'Success'), ('FAILURE', 'Failure')])
```

* **Automated Signals:** Connected to `user_logged_in` and `user_login_failed`.
* **Gatekeeper Rejections:** Inactive service access and affiliation mismatches are recorded with the corresponding OAuth2 `client_id`.
* **Admin Immutability:** In `core/admin.py`, `has_add_permission` and `has_change_permission` are set to `False` to prevent audit tampering.

---

## 6. Session Hardening, Cookies & Bfcache Mitigation

```python
# Cookie Security
SESSION_COOKIE_DOMAIN = '.proxy.eupeace.eu'
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'None' # Required for SAML HTTP-POST cross-site binding
CSRF_COOKIE_SAMESITE = 'None'
SESSION_SAVE_EVERY_REQUEST = True
```

* **Session Storage:** Offloaded from the relational database into Redis RAM (`SESSION_ENGINE = 'django.contrib.sessions.backends.cache'`).
* **Bfcache (Back-Forward Cache) Protection:** Sensitive views (`dashboard`, `wayf_view`, `custom_logout`, `create_invitation_view`, `revoke_invitation_view`) are decorated with `@never_cache` to inject:
  ```http
  Cache-Control: max-age=0, no-cache, no-store, must-revalidate, private
  Pragma: no-cache
  ```
  This ensures that hitting the browser back button on shared terminals does not display cached authenticated views after logout.

---

## 7. Attribute Sanitization & GDPR Compliance

In accordance with the **GÉANT Data Protection Code of Conduct (CoCo)** and GDPR:
* **Whitelist Mapping:** Only attributes explicitly listed in `SAML_ATTRIBUTE_MAPPING` are persisted. Unmapped attributes are discarded in memory upon assertion processing.
* **Home Organization Derivation:** If an IdP omits `schacHomeOrganization`, the custom backend (`EupeaceSamlBackend`) extracts the organizational domain from the scope of `eduPersonPrincipalName` (e.g. `user@example.org` -> `example.org`) or `eduPersonScopedAffiliation`.
* **Single-Use Guest Tokens:** Guest invitation tokens are cryptographically randomized UUID4 strings, valid for a single redemption, and time-bounded by an expiration timestamp.

---

## 8. Incident Reporting & Security Contacts

Security incidents, vulnerability disclosures, or metadata compliance concerns should be directed to the security contacts declared in the official SAML metadata:

* **Security Incident Response Team:** [abuse@eupeace.eu](mailto:abuse@eupeace.eu)
* **Technical Operations:** [tech@eupeace.eu](mailto:tech@eupeace.eu)
* **Alliance IT Support:** [support@eupeace.eu](mailto:support@eupeace.eu)