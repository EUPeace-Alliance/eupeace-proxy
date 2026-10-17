# 👨‍💻 Developer Guide & Onboarding

This guide provides technical onboarding instructions, architectural deep-dives, testing procedures, and troubleshooting guidelines for developers working on the **EUPEACE Proxy Identifier**.

---

## 1. Local Environment Setup

The application is containerized using Docker Compose to match the production runtime closely.

### Prerequisites
* **Docker Engine** (v24+) and **Docker Compose** (v2+)
* *(Optional for local IDE linters)* **Python 3.12+** with `venv`

### Step 1: Clone and Configure Environment
```bash
git clone git@github.com:EUPeace-Alliance/eupeace-proxy.git
cd eupeace-proxy
cp .env.example .env
```

Ensure your `.env` contains valid development configurations:
```ini
DEBUG=True
SECRET_KEY=dev-secret-key-replace-in-production
PROXY_DOMAIN=localhost:8000
ALLOWED_HOSTS=localhost,127.0.0.1,proxy.eupeace.eu
DATABASE_URL=postgres://eupeace_user:super_password@pgbouncer:6432/eupeace_db
REDIS_URL=redis://redis:6379/1
DB_USER=eupeace_user
DB_PASSWORD=super_password
DB_NAME=eupeace_db
SAML_ENTITY_ID=https://proxy.eupeace.eu/saml2/metadata/
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

### Step 2: Initialize Required Cryptographic Keys
Create the local `certs/` directory (completely ignored by Git):
```bash
mkdir -p certs
```

1. **OIDC Private Key:**
   ```bash
   openssl genrsa -out certs/oidc_rsa.key 2048
   chmod 600 certs/oidc_rsa.key
   ```
2. **SAML Self-Signed Keypair (for local development):**
   ```bash
   openssl req -new -x509 -days 365 -nodes \
     -out certs/public.cert \
     -keyout certs/private.key \
     -subj "/C=EU/O=EUPeace Alliance/CN=localhost"
   chmod 600 certs/private.key
   ```
3. **IDEM MDX Certificate:**
   Download the public IDEM/GARR MDX signing certificate:
   ```bash
   curl -s -o certs/idem-mdx-service-crt.pem https://mdx.idem.garr.it/idem-mdx-service-crt.pem
   ```

### Step 3: Build & Start Infrastructure
```bash
docker compose up -d --build
```

### Step 4: Run Migrations & Create Superuser
```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

Once running, navigate to `http://localhost:8000/gestione/` to access the Django Administration portal.

---

## 2. Codebase Anatomy & Key Components

The core application code is organized across two directories: `core/` (application logic, models, views, templates) and `hybrid_project/` (project-wide configuration, SAML backend, URL dispatching).

### Core Application (`core/`)

| File | Purpose |
| --- | --- |
| `core/models.py` | Defines data models: `UserProfile`, `GuestProfile`, `GuestInvitation`, `AllianceService`, `IdentityProvider`, and `AuditLog`. Includes login signal handlers logging authentication outcomes. |
| `core/views.py` | Contains the primary HTTP endpoints: `wayf_view` (discovery), `dashboard` (service catalog & invitations), `CustomSAML2LoginView` (MFA injection & guest handling), `CustomAuthorizationView` (OAuth2 gatekeeping), `redeem_invite_view`, `create_invitation_view`, `revoke_invitation_view`, and `custom_logout`. |
| `core/oauth_validators.py` | Subclasses `OAuth2Validator` (`CustomOAuth2Validator`) to map and inject institutional claims (`affiliation`, `home_organization`, `esi_code`) into the OIDC `profile` scope. |
| `core/signals.py` | Handles post-login business logic: binds redeemed guest tokens, enforces IdP whitelisting, and blocks unauthorized sessions. |
| `core/admin.py` | Customizes Django admin for all models; configures read-only immutable auditing views for `AuditLog`. |
| `core/apps.py` | Implements an application startup monkey patch for `djangosaml2` to prevent 500 errors on missing MDQ entities. |
| `core/forms.py` | Contains `GuestInvitationForm` used for email invitation creation. |

### Configuration Layer (`hybrid_project/`)

| File | Purpose |
| --- | --- |
| `hybrid_project/settings.py` | Global settings: database connection, `SAML_CONFIG` (IDEM MDX metadata, signing keys, encryption keypairs, UI info), `OAUTH2_PROVIDER` configuration, Redis session caches, security cookies, and CSRF origins. |
| `hybrid_project/saml_backend.py` | `EupeaceSamlBackend` (subclass of `djangosaml2.backends.Saml2Backend`): handles ePPN fallback, maps SAML attributes, derives `home_organization` from attribute scopes, and passes the IdP entity ID to signals. |
| `hybrid_project/urls.py` | Master URL routing: mounts SAML endpoints (`/saml2/`), OAuth2 endpoints (`/o/`), admin portal (`/gestione/`), and compliance pages (`/info/`, `/privacy/`, `/helpdesk/`). |

---

## 3. Automated Testing Suite

The repository includes a comprehensive test suite in `core/tests.py` covering:
* **OAuth2 Gatekeeping:** Verifies that students, staff, guests, and administrators are appropriately granted or denied access based on `AllianceService.visibility`.
* **Inactive Service Handling:** Verifies that maintenance-mode services return 403 pages.
* **Unlinked OAuth2 Applications:** Confirms default access for unlinked clients.
* **Audit Logging:** Asserts that access denials produce `FAILURE` records in `AuditLog` with matching client IDs.

### Running Tests Inside Docker
```bash
docker compose exec web python manage.py test
```

### Running Tests Locally with SQLite Override
If running tests outside Docker without PgBouncer/PostgreSQL running:
```bash
DATABASE_URL=sqlite:////tmp/test.db python manage.py test
```

---

## 4. Development Workflows & "God Mode"

### Superuser Bypass ("God Mode")
Testing federated authentication without an active academic IdP is cumbersome. A built-in bypass exists for development:
1. Log in to `http://localhost:8000/gestione/` using the superuser created via `createsuperuser`.
2. Visit `http://localhost:8000/dashboard/`.
3. The dashboard detects `user.is_superuser` and assigns the `ADMIN` role.
4. In `CustomAuthorizationView`, superusers bypass all visibility restrictions, allowing manual testing of OAuth2 authorization flows without needing specific institutional affiliations.

### Testing OAuth2 / OIDC Integration Locally
To simulate an OAuth2 client (like Moodle) connecting to the proxy:
1. Go to `http://localhost:8000/gestione/oauth2_provider/application/`.
2. Create an Application:
   * **Client type:** Confidential
   * **Authorization grant type:** Authorization code
   * **Redirect URIs:** `https://oauth.pstmn.io/v1/callback` (or your local client callback)
   * **Algorithm:** RSA with SHA-256
3. Under **Alliance Services**, create an `AllianceService` and link it to the newly created OAuth2 application with desired visibility (`STUDENT` or `STAFF`).
4. Trigger the flow in a browser:
   `http://localhost:8000/o/authorize/?client_id=<CLIENT_ID>&response_type=code&scope=openid%20profile%20email`

### Testing Guest Invitations
With `EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'`, invitation emails are printed to the terminal console (`docker compose logs -f web`). You can copy the generated `/invite/<UUID>/` link directly into your browser to test the redemption workflow.

---

## 5. Troubleshooting & Gotchas

### 1. PgBouncer Transaction Mode (`prepare_threshold`)
Because PgBouncer operates in `transaction` pool mode, PostgreSQL server-side prepared statements can cause errors across shared connections. Django is configured in `settings.py` with:
```python
DATABASES['default']['OPTIONS'] = {
    'prepare_threshold': None,
}
```
Do not remove this setting when connecting via PgBouncer.

### 2. Redis Session Caching & Outage Resilience
User sessions are managed in Redis RAM (`django-redis`). If Redis temporarily restarts, `IGNORE_EXCEPTIONS: True` is configured to avoid hard 500 crashes. If sessions appear to reset unexpectedly, check Redis status:
```bash
docker compose logs -f redis
```

### 3. Entity ID Formats (URLs vs URNs)
Some European IdPs (e.g., French or Czech universities) use URNs rather than HTTPS URLs as their Entity ID (e.g., `urn:mace:cru.fr:federation:unilim.fr`). The `IdentityProvider.entity_id` and `AuditLog.idp_entity_id` fields use `CharField(max_length=500)` rather than `URLField` to support both formats without validation errors.

### 4. Gunicorn Gevent `/nonexistent` Warning
When starting Gunicorn with `--worker-class gevent`, the following warning may appear:
`Control server error: [Errno 13] Permission denied: '/nonexistent'`
This is a known false positive resulting from gevent attempting to resolve a non-existent home directory inside the lightweight container user. It has no functional impact on the server.

### 5. Inspecting Debug Logs
Sensitive views include diagnostic logging statements. To stream runtime logs:
```bash
docker compose logs --tail 100 -f web
```
