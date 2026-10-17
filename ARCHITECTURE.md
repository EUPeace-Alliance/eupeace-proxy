# 🏗 Architecture & Design Specifications

The **EUPEACE Proxy Identifier** is a hybrid Identity and Access Management (IAM) node designed to bridge federated university identities with internal and external digital alliance services.

The platform simultaneously operates in two fundamental roles:
1. **Inbound SAML 2.0 Service Provider (SP):** Accepts authentication assertions from federated Identity Providers (IdPs) belonging to the **IDEM GARR** and **eduGAIN** confederations.
2. **Outbound OAuth2 / OpenID Connect (OIDC) Identity Provider (IdP):** Issues digitally signed OIDC tokens to alliance services (e.g., Moodle LMS instances, collaborative platforms) while strictly enforcing affiliation-based gatekeeping policies.

---

## 1. High-Level System Architecture

```mermaid
graph TD
    %% Actors
    Admin[Admin / Staff]
    Student[Student]
    Guest[External Guest]

    %% Relying Parties / Consumers
    Moodle[Alliance Moodle LMS]
    Portal[Digital Alliance Portals]

    %% External Identity & Federation Services
    WAYF[SeamlessAccess Discovery Service]
    IdP[eduGAIN / IDEM Identity Providers]
    MDX[IDEM MDX Service<br/>mdx.idem.garr.it]
    SMTP[Alliance SMTP Relay]

    %% Internal Infrastructure
    subgraph EUPEACE Infrastructure
        Nginx[Nginx Reverse Proxy / SSL]
        
        subgraph Application Server
            Gunicorn[Gunicorn / Gevent Workers]
            Django[Django Core Engine]
            SAML_SP[djangosaml2 / pysaml2 SP]
            OIDC_IDP[django-oauth-toolkit OIDC IdP]
            Gatekeeper[CustomAuthorizationView<br/>Gatekeeping Engine]
        end

        Redis[(Redis 7 Cache & Sessions)]
        PgBouncer[PgBouncer Pooler<br/>Transaction Mode]
        DB[(PostgreSQL 15)]
    end

    %% Inbound SAML Flows
    Student & Admin & Guest -->|1. HTTPS| Nginx
    Nginx --> Gunicorn
    Gunicorn --> Django
    Django --> SAML_SP
    SAML_SP -->|Fetch Signed Metadata| MDX
    SAML_SP -->|Redirect to Discovery| WAYF
    WAYF -->|Select IdP| IdP
    SAML_SP <-->|SAML AuthnRequest / Assertion| IdP

    %% Outbound OIDC Flows
    Moodle & Portal -->|OAuth2 / OIDC Auth Request| Nginx
    Django --> Gatekeeper
    Gatekeeper --> OIDC_IDP
    OIDC_IDP -->|Issue JWT Token with Custom Claims| Moodle & Portal

    %% Persistence & Cache
    Django <-->|Session Store / Caching| Redis
    Django <-->|ORM Queries| PgBouncer
    PgBouncer <--> DB

    %% Notifications
    Django -->|Send Invite via Port 587 TLS| SMTP
    SMTP -->|Dispatch Email| Guest
```

---

## 2. Sequence Diagrams

### A. Inbound Federated Authentication Flow (SAML 2.0 Single Sign-On)
The proxy delegates user authentication to their home university's Identity Provider, retrieving attributes and populating the local session:

```mermaid
sequenceDiagram
    autonumber
    participant User as End User
    participant Proxy as EUPEACE Proxy (SP)
    participant WAYF as SeamlessAccess (Discovery)
    participant IdP as Home University IdP
    participant DB as PostgreSQL / Redis

    User->>Proxy: Accesses Homepage (/)
    Proxy->>WAYF: Redirect to Central Discovery with SP Entity ID
    WAYF-->>User: Renders University Search Dialog
    User->>WAYF: Selects Home Institution
    WAYF->>Proxy: Returns with chosen IdP Entity ID
    Proxy->>Proxy: Inspects IdP in IdentityProvider model (Checks MFA requirement)
    Proxy->>IdP: Sends SAML AuthnRequest (+ REFEDS MFA context if required)
    IdP-->>User: Prompts for institutional credentials (+ 2FA if requested)
    User->>IdP: Authenticates successfully
    IdP->>Proxy: POST SAML Assertion to /saml2/acs/
    Proxy->>Proxy: Verifies cryptographic signatures using IDEM MDX metadata
    Proxy->>Proxy: EupeaceSamlBackend maps attributes & derives home_organization
    Proxy->>DB: Updates or creates User and UserProfile
    Proxy->>DB: Records SUCCESS entry in AuditLog
    Proxy-->>User: Redirects to /dashboard/ or saved OAuth2 authorization URL
```

---

### B. Outbound OAuth2 / OpenID Connect Gatekeeping Flow
When external alliance platforms (like Moodle) request user authorization, the proxy acts as an OIDC Identity Provider with strict role-based gatekeeping:

```mermaid
sequenceDiagram
    autonumber
    participant User as Authenticated User
    participant Client as Alliance Client (e.g., Moodle)
    participant Gatekeeper as CustomAuthorizationView (/o/authorize/)
    participant Validator as CustomOAuth2Validator
    participant Audit as AuditLog

    Client->>User: Initiates Login via EUPEACE
    User->>Gatekeeper: Redirects to /o/authorize/?client_id=...&response_type=code
    alt User Not Authenticated
        Gatekeeper-->>User: Preserves target URL in session & redirects to WAYF / SAML
    end
    Gatekeeper->>Gatekeeper: Matches client_id to linked AllianceService
    
    alt Service Inactive
        Gatekeeper->>Audit: Records FAILURE in AuditLog (Service Disabled)
        Gatekeeper-->>User: Renders 403 access_denied.html
    else Visibility Policy Enforcement
        Gatekeeper->>Gatekeeper: Evaluates service.visibility (ALL / STUDENT / STAFF)
        alt Affiliation Mismatch (e.g. Student accessing Staff-only Moodle)
            Gatekeeper->>Audit: Records FAILURE in AuditLog (Affiliation Mismatch)
            Gatekeeper-->>User: Renders 403 access_denied.html
        else Authorized Access (or Superuser Bypass)
            Gatekeeper-->>Client: Returns 302 Redirect with Authorization Code
            Client->>Gatekeeper: Exchanges Code at /o/token/
            Validator->>Validator: Injects claims: affiliation, home_organization, esi_code
            Gatekeeper-->>Client: Issues ID Token (JWT) & Access Token
            Client-->>User: Grants access to the alliance platform
        end
    end
```

---

### C. Guest Invitation & Redemption Lifecycle
Enables external experts, researchers, and partners to be invited with time-limited access:

```mermaid
sequenceDiagram
    autonumber
    participant Admin as Proxy Administrator
    participant Proxy as EUPEACE Proxy
    participant SMTP as Alliance SMTP Relay
    participant Guest as External Guest
    participant IdP as Guest's eduGAIN IdP
    participant DB as PostgreSQL

    Admin->>Proxy: Submits invitation modal (Email + Duration in days)
    Proxy->>DB: Generates UUID4 token in GuestInvitation (is_used=False)
    Proxy->>SMTP: Dispatches invitation email with /invite/<token>/ link
    SMTP-->>Guest: Delivers invitation message
    Guest->>Proxy: Visits /invite/<token>/ (redeem_invite_view)
    Proxy->>Proxy: Validates token expiration & stores token in session
    Proxy-->>Guest: Displays guest_welcome.html
    Guest->>Proxy: Clicks "Find your University"
    Proxy->>IdP: Executes standard SAML SSO flow
    IdP-->>Proxy: Returns valid SAML Assertion
    Proxy->>DB: Signal creates/updates GuestProfile (valid_until = now + duration)
    Proxy->>DB: Marks GuestInvitation as is_used=True
    Proxy-->>Guest: Redirects to /dashboard/ with GUEST role privileges
```

---

## 3. Data Architecture & Relational Schema

The data model is implemented in `core/models.py` and consists of six primary entities:

```mermaid
erDiagram
    User ||--o| UserProfile : "extends (1:1)"
    User ||--o| GuestProfile : "holds (1:1)"
    User ||--o{ GuestInvitation : "invites (1:N)"
    User ||--o{ Application : "owns (1:N)"
    Application ||--o| AllianceService : "links (1:1)"
    
    UserProfile {
        int id PK
        int user_id FK
        string esi
        string affiliation
        string home_organization
    }

    GuestProfile {
        int id PK
        int user_id FK
        int invited_by_id FK
        datetime valid_until
    }

    GuestInvitation {
        uuid token PK
        int inviter_id FK
        string guest_email
        int duration_days
        datetime created_at
        datetime expires_at
        bool is_used
    }

    AllianceService {
        int id PK
        string name
        text description
        string url
        string logo_url
        string visibility "ALL | STUDENT | STAFF"
        bool is_active
        string provider "UNICAL | MARBURG | GIESSEN | LIMOGES | ZCU | SARAJEVO | CUKUROVA | COMILLAS | MOSTAR"
        int oauth_application_id FK
    }

    IdentityProvider {
        int id PK
        string name
        string short_code
        string entity_id "Supports URLs and URNs"
        bool supports_mfa
        bool is_active
        string logo_url
    }

    AuditLog {
        int id PK
        datetime timestamp
        string eppn
        string ip_address
        string idp_entity_id
        string service_client_id
        string status "SUCCESS | FAILURE"
    }
```

### Model Specifications

1. **`UserProfile`:**
   * One-to-one extension of Django's built-in `User` model.
   * Maps essential SAML attributes: European Student Identifier (`esi`), scoped affiliation (`affiliation`), and institutional domain (`home_organization`).
   * Provides the `formatted_esi` property, parsing SCHAC personal unique codes into user-friendly HTML tags.

2. **`GuestProfile`:**
   * One-to-one extension for users who authenticated through an invitation token.
   * Tracks the inviter reference (`invited_by`) and role expiration timestamp (`valid_until`).

3. **`GuestInvitation`:**
   * Manages pending and fulfilled invitation tokens.
   * Includes utility methods such as `is_valid()` to verify token freshness before redemption.

4. **`AllianceService`:**
   * Defines the catalog of alliance services presented on the dashboard.
   * Links to `oauth2_provider.Application` via a nullable `OneToOneField`. When linked, any OAuth2 authorization request for this client triggers gatekeeping enforcement.
   * Categorized by providing university (partner universities of the EUPeace alliance) and role visibility (`ALL`, `STUDENT`, `STAFF`).

5. **`IdentityProvider`:**
   * Maintains the active directory of federated Identity Providers.
   * `entity_id` is stored as `CharField(max_length=500)` to fully accommodate both standard URLs and URN-formatted identifiers (e.g., `urn:mace:cru.fr:federation:unilim.fr`).
   * Controls dynamic injection of the REFEDS MFA profile during SAML authentication requests.

6. **`AuditLog`:**
   * Immutable security audit log tracking all authentication events (`SUCCESS` / `FAILURE`), client IP addresses, user ePPNs, IdP entity IDs, and target client IDs.
   * Protected in Django admin against manual tampering or alteration (`has_add_permission=False`, `has_change_permission=False`).

---

## 4. Middleware, Session & Infrastructure Hardening

* **Session Storage:** Powered by Redis (`django_redis.cache.RedisCache`). User sessions reside in RAM to ensure high throughput and rapid SSO redirects.
* **PgBouncer Compatibility:** Set to `POOL_MODE=transaction` with `prepare_threshold: None` in database settings to support high concurrent connection volumes without resource exhaustion.
* **SAML RelayState Preservation:** To prevent IdPs from truncating OAuth2 authorization URLs (which often exceed the 80-byte SAML RelayState specification), the proxy captures the `next` parameter in the Redis session (`oauth2_next_url`) and restores it upon successful authentication.
* **Bfcache & Cache Prevention:** Sensitive authentication views and user dashboards are decorated with `@never_cache` to prohibit browser caching, preventing information leakage via browser back/forward buttons on shared workstations.
