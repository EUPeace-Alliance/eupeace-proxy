# EUPEACE Authentication Proxy & Identity Provider 🌍

The **EUPEACE Proxy Identifier** is a centralized Identity and Access Management (IAM) node developed for the **European University for Peace, Justice, and Inclusive Societies (EUPeace) Alliance**.

The infrastructure serves a dual architectural purpose:
1. **Inbound SAML 2.0 Service Provider (SP):** Federates authentication with Identity Providers (IdPs) across the **IDEM GARR** and international **eduGAIN** networks using dynamic MDX metadata.
2. **Outbound OAuth2 / OpenID Connect (OIDC) Identity Provider (IdP):** Acts as a secure authorization gatekeeper for digital alliance services (such as shared Moodle LMS platforms, collaborative tools, and academic portals), issuing OIDC tokens enriched with role-based claims (`affiliation`, `home_organization`, `esi_code`).

---

## 🛠 Tech Stack

* **Backend Framework:** Django 6.x / Python 3.12+
* **Database & Pooling:** PostgreSQL 15 (Alpine) with PgBouncer (transaction pooling)
* **Session Cache & Memory Store:** Redis 7 (Alpine) via `django-redis`
* **Federated Protocols:**
  * SAML 2.0 Service Provider (`djangosaml2`, `pysaml2`)
  * OAuth2 / OpenID Connect Provider (`django-oauth-toolkit`, `jwcrypto`)
* **Web Server & Reverse Proxy:** Gunicorn (gevent workers) & Nginx (Let's Encrypt / Certbot TLS)
* **Frontend:** HTML5, Bootstrap 5.3 (Vanilla CSS & responsive components)
* **Containerization:** Docker & Docker Compose

---

## ✨ Key Features

* **Federated Single Sign-On (SSO):** Interoperable authentication via academic Identity Providers across IDEM and eduGAIN. Integrates with the **IDEM Metadata Query Protocol (MDX)** (`https://mdx.idem.garr.it/edugain/`) with X.509 signature verification.
* **OAuth2 / OIDC Gatekeeping:** Built-in gatekeeping authorization view (`CustomAuthorizationView`) that intercepts OAuth2 client requests (e.g., Moodle) and enforces role-based visibility policies (`ALL`, `STUDENT`, `STAFF`) against user institutional affiliations before issuing tokens.
* **Custom OIDC Claims:** Claims injection (`CustomOAuth2Validator`) returning standard OIDC profile claims along with European academic claims: `affiliation`, `home_organization`, and `esi_code` (European Student Identifier).
* **Dynamic Identity Provider Management:** Authorized IdPs are managed dynamically via the `IdentityProvider` database model. Supports both URLs (`https://...`) and URNs (e.g., `urn:mace:cru.fr:federation:unilim.fr`) and dynamic Multi-Factor Authentication (REFEDS MFA profile) requests.
* **Role-Based Service Dashboard:** Dynamic service catalog offering categorized access to digital alliance services based on institutional affiliation (`STUDENT`, `STAFF`, `ADMIN`, `GUEST`), featuring search, provider filtering (across partner institutions), and pagination.
* **Guest Invitation System:** Token-based guest onboarding allowing administrators and authorized users to send time-limited email invitations to external collaborators, linking their eduGAIN credentials to a temporary guest profile.
* **Security Audit Logging:** Persistent logging via `AuditLog` of all login events (successes and failures) and OAuth2 authorization attempts, capturing user ePPN, IP address, IdP entity ID, client ID, and timestamps.
* **Session Hardening & Bfcache Prevention:** Sessions stored in Redis with cross-domain SameSite/Secure cookies and HTTP `@never_cache` protection headers on sensitive endpoints.
* **IDEM / eduGAIN Compliance:** Bilingual public service information (`/info/`), privacy policy (`/privacy/`), and helpdesk (`/helpdesk/`) endpoints compliant with IDEM SP-FED02 standards and REFEDS security requirements.

---

## 🚀 Prerequisites & Installation

Ensure you have **Docker** (version 24+) and **Docker Compose** (v2+) installed on your server.

### 1. Clone the repository
```bash
git clone git@github.com:EUPeace-Alliance/eupeace-proxy.git
cd eupeace-proxy
```

### 2. Environment Variables Configuration
Copy the template and configure your `.env` file:
```bash
cp .env.example .env
```

| Variable | Description | Example / Default |
| --- | --- | --- |
| `DEBUG` | Django debug mode (must be `False` in production) | `False` |
| `SECRET_KEY` | Cryptographic secret for signing sessions and tokens | `django-insecure-...` |
| `PROXY_DOMAIN` | Primary public FQDN of your proxy instance | `proxy.eupeace.eu` |
| `ALLOWED_HOSTS` | Comma-separated list of authorized hostnames | `proxy.eupeace.eu,localhost` |
| `DATABASE_URL` | PostgreSQL connection string (points to PgBouncer) | `postgres://eupeace_user:pass@pgbouncer:6432/eupeace_db` |
| `DB_NAME` | PostgreSQL database name | `eupeace_db` |
| `DB_USER` | PostgreSQL username | `eupeace_user` |
| `DB_PASSWORD` | PostgreSQL password | `strongpassword` |
| `REDIS_URL` | Redis URL for session storage and caching | `redis://redis:6379/1` |
| `SAML_ENTITY_ID` | Public Entity ID of this Service Provider | `https://proxy.eupeace.eu/saml2/metadata/` |
| `EMAIL_HOST` | Outgoing SMTP host for guest invitations | `smtp.example.org` |
| `EMAIL_PORT` | SMTP port | `587` |
| `EMAIL_USE_TLS` | Enable TLS encryption for email transmission | `True` |
| `EMAIL_USE_SSL` | Enable SSL encryption for email transmission | `False` |
| `DEFAULT_FROM_EMAIL` | Default sender email address | `noreply@eupeace.eu` |

### 3. Cryptographic Certificates & Keys Setup
Create a local `certs/` directory (completely ignored by Git) and place or generate the required cryptographic assets:
```bash
mkdir -p certs
```

* `private.key`: SP private key (RSA 2048/4096-bit) used for signing SAML AuthnRequests/LogoutRequests and decrypting encrypted assertions.
* `public.cert`: SP public certificate registered with the IDEM/eduGAIN federation.
* `idem-mdx-service-crt.pem`: IDEM MDX signing certificate used to verify downloaded federation metadata. Obtain it directly from the IDEM/GARR federation:
  ```bash
  curl -s -o certs/idem-mdx-service-crt.pem https://mdx.idem.garr.it/idem-mdx-service-crt.pem
  ```
* `oidc_rsa.key`: RSA private key used by `django-oauth-toolkit` to sign OpenID Connect JWT tokens:
  ```bash
  openssl genrsa -out certs/oidc_rsa.key 2048
  chmod 600 certs/oidc_rsa.key
  ```

### 4. Start the Infrastructure
```bash
docker compose up -d --build
```

### 5. Initialize Database, Migrations, and Superuser
```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

---

## 🔐 Federation & Protocol Endpoints

Assuming default domain `proxy.eupeace.eu`:

### SAML 2.0 Service Provider Endpoints
* **SP Entity ID:** `https://proxy.eupeace.eu/saml2/metadata/`
* **Assertion Consumer Service (ACS):** `https://proxy.eupeace.eu/saml2/acs/` (HTTP-POST)
* **Single Logout Service (SLS Redirect):** `https://proxy.eupeace.eu/saml2/ls/` (HTTP-Redirect)
* **Single Logout Service (SLS Post):** `https://proxy.eupeace.eu/saml2/ls/post` (HTTP-POST)
* **WAYF / Discovery Endpoint:** `https://proxy.eupeace.eu/`
* **Direct IdP Login Endpoint:** `https://proxy.eupeace.eu/saml2/login/?idp=<ENTITY_ID>`

### OAuth2 / OpenID Connect Endpoints
* **Authorization Endpoint:** `https://proxy.eupeace.eu/o/authorize/`
* **Token Endpoint:** `https://proxy.eupeace.eu/o/token/`
* **User Information Endpoint:** `https://proxy.eupeace.eu/o/userinfo/`
* **OIDC Discovery (.well-known):** `https://proxy.eupeace.eu/o/.well-known/openid-configuration/`
* **JWKS Endpoint:** `https://proxy.eupeace.eu/o/.well-known/jwks.json`

### Public Compliance & Information Pages
* **Service Information:** `https://proxy.eupeace.eu/info/`
* **Privacy Statement:** `https://proxy.eupeace.eu/privacy/`
* **Support & Helpdesk:** `https://proxy.eupeace.eu/helpdesk/`

---

## ✉️ Guest Invitation Workflow

The Guest Management System allows external non-federated partners or guest scholars to register using an eduGAIN or guest account:
1. **Creation:** An administrator fills in the invitation modal in the Dashboard, specifying the guest's email and account validity duration (e.g., 180 days).
2. **Token Generation:** A cryptographic UUID4 token is generated and persisted in `GuestInvitation`.
3. **Email Notification:** An invitation link (`/invite/<UUID>/`) is sent via SMTP.
4. **Redemption & Binding:** The recipient opens the link, stores the token in their session, and completes SAML login via any eduGAIN IdP.
5. **Activation:** The login signal binds the authenticated identity to a `GuestProfile` with expiration matching the invitation duration, and marks the invitation token as used.
