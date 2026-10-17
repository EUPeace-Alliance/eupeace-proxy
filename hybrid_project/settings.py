from saml2 import httpbase
import environ
import os
import saml2
import saml2.saml
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False)
)

environ.Env.read_env(os.path.join(BASE_DIR, '.env'))


SECRET_KEY = env('SECRET_KEY', default='django-insecure-dev-key-change-in-production')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1', 'proxy.eupeace.eu'])
PROXY_DOMAIN = env('PROXY_DOMAIN', default='proxy.eupeace.eu')


DATABASES = {
    'default': env.db('DATABASE_URL', default='sqlite:///db.sqlite3')
}

# Mandatory configuration to make Django work with PgBouncer in transaction mode
if 'postgresql' in DATABASES['default'].get('ENGINE', ''):
    DATABASES['default']['OPTIONS'] = {
        'prepare_threshold': None,
    }


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'djangosaml2',
    'oauth2_provider',
    'core',
]
AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
    'hybrid_project.saml_backend.EupeaceSamlBackend',
)

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'djangosaml2.middleware.SamlSessionMiddleware',
]

ROOT_URLCONF = 'hybrid_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'hybrid_project.wsgi.application'


AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')

# Mapping eduGAIN / SAML attributes to Django User and UserProfile models
SAML_ATTRIBUTE_MAPPING = {
    'mail': ('email', ),
    'givenName': ('first_name', ),
    'sn': ('last_name', ),
    'eduPersonPrincipalName': ('username', ),
    'eduPersonScopedAffiliation': ('profile__affiliation', ),
    'schacPersonalUniqueCode': ('profile__esi', ),
    'schacHomeOrganization': ('profile__home_organization', ),
}

# Folder for SP cryptographic certificates and metadata verification assets
SAML_CERTS_DIR = os.path.join(BASE_DIR, 'certs')
SAML_CSP_HANDLER = ''

SAML_CONFIG = {
    'base_url': f'https://{PROXY_DOMAIN}',
    'entityid': env('SAML_ENTITY_ID', default=f'https://{PROXY_DOMAIN}/saml2/metadata/'),
    
    # 1. ORGANIZATION INFORMATION (Federation Compliance)
    'organization': {
        'name': [
            ('EUPeace European University Alliance', 'en'),
            ('Alleanza Universitaria Europea EUPeace', 'it')
        ],
        'display_name': [
            ('EUPeace Authentication Proxy', 'en'),
            ('Proxy di Autenticazione EUPeace', 'it')
        ],
        'url': [
            ('https://www.eupeace.eu', 'en'),
            ('https://www.eupeace.eu', 'it')
        ],
    },
    
    # 2. CONTACTS (Technical, Support, Security - IDEM & REFEDS requirement)
    'contact_person': [
        {
            'given_name': 'EUPeace IT Team',
            'sur_name': 'Support',
            'email_address': 'mailto:tech@eupeace.eu',
            'contact_type': 'technical',
        },
        {
            'given_name': 'EUPeace User Support',
            'email_address': 'mailto:support@eupeace.eu',
            'contact_type': 'support',
        },
        # Security Incident Response Contact (Required by REFEDS/GARR)
        {
            'given_name': 'Security Incident Response Team',
            'email_address': 'mailto:abuse@eupeace.eu', 
            'contact_type': 'other',
            'ext': {
                'contact_type': 'http://refeds.org/metadata/contactType/security'
            }
        },
    ],
    
    'accepted_time_diff': 120, # Clock skew tolerance of 2 minutes
    
    # Directory mapping SAML OIDs to human-readable names
    'attribute_map_dir': os.path.join(os.path.dirname(saml2.__file__), 'attributemaps'),
    
    # 3. METADATA MANAGEMENT (IDEM & eduGAIN via MDX)
    'metadata': {
        'local': [f for f in [
            os.path.join(SAML_CERTS_DIR, 'local_metadata.xml'),
        ] if os.path.exists(f)],
        'mdq': [
            {
                "url": "https://mdx.idem.garr.it/edugain/",
                "cert": os.path.join(SAML_CERTS_DIR, 'idem-mdx-service-crt.pem') if os.path.exists(os.path.join(SAML_CERTS_DIR, 'idem-mdx-service-crt.pem')) else None,
            },
        ],
    },
    
    'key_file': os.path.join(SAML_CERTS_DIR, 'private.key'),
    'cert_file': os.path.join(SAML_CERTS_DIR, 'public.cert'),
    'encryption_keypairs': [{
        'key_file': os.path.join(SAML_CERTS_DIR, 'private.key'),
        'cert_file': os.path.join(SAML_CERTS_DIR, 'public.cert'),
    }],
    
    'service': {
        'sp': {
            'endpoints': {
                'assertion_consumer_service': [
                    (f'https://{PROXY_DOMAIN}/saml2/acs/', saml2.BINDING_HTTP_POST),
                ],
                'single_logout_service': [
                    (f'https://{PROXY_DOMAIN}/saml2/ls/', saml2.BINDING_HTTP_REDIRECT),
                    (f'https://{PROXY_DOMAIN}/saml2/ls/post', saml2.BINDING_HTTP_POST),
                ],
            },
            
            # 4. UI INFO (Display parameters in discovery services & federation registries)
            'ui_info': {
                'display_name': [
                    ('EUPeace Proxy', 'en'), 
                    ('Proxy di Autenticazione EUPeace', 'it')
                ],
                'description': [
                    ('Centralized access to EUPeace federated services.', 'en'),
                    ('Accesso centralizzato ai servizi federati EUPeace.', 'it')
                ],
                'information_url': [
                    (f'https://{PROXY_DOMAIN}/info/', 'en'),
                    (f'https://{PROXY_DOMAIN}/info/', 'it')
                ],
                'privacy_statement_url': [
                    (f'https://{PROXY_DOMAIN}/privacy/', 'en'),
                    (f'https://{PROXY_DOMAIN}/privacy/', 'it')
                ],
                'logo': {
                    'text': f'https://{PROXY_DOMAIN}/static/logo_eupeace.png',
                    'width': '146',
                    'height': '122',
                },
            },
            
            # 5. REQUESTED ATTRIBUTES (Standard SAML2 AttributeConsumingService)
            'required_attributes': [
                'mail',
                'eduPersonPrincipalName',
            ],
            'optional_attributes': [
                'givenName',
                'sn',
                'eduPersonScopedAffiliation',
                'schacPersonalUniqueCode',
            ],
            
            'name_id_format': [
                saml2.saml.NAMEID_FORMAT_TRANSIENT,
                saml2.saml.NAMEID_FORMAT_PERSISTENT,
            ],
            'allow_unsolicited': True,
            'authn_requests_signed': True,
            'want_assertions_signed': True,
            'want_response_signed': False,
            'logout_requests_signed': True,
            'signing_algorithm': 'http://www.w3.org/2001/04/xmldsig-more#rsa-sha256',
            'digest_algorithm': 'http://www.w3.org/2001/04/xmlenc#sha256',
        },
    },
    'signing_algorithm': 'http://www.w3.org/2001/04/xmldsig-more#rsa-sha256',
    'digest_algorithm': 'http://www.w3.org/2001/04/xmlenc#sha256',
}

# Path to the RSA private key used to sign OpenID Connect JWT tokens
OIDC_PRIVATE_KEY_PATH = os.path.join(BASE_DIR, 'certs', 'oidc_rsa.key')

if os.path.exists(OIDC_PRIVATE_KEY_PATH):
    with open(OIDC_PRIVATE_KEY_PATH, 'r') as f:
        OIDC_RSA_PRIVATE_KEY = f.read()
else:
    # Graceful fallback during initial migrations or testing when key is absent
    OIDC_RSA_PRIVATE_KEY = ""

OAUTH2_PROVIDER_APPLICATION_MODEL = 'oauth2_provider.Application'

OAUTH2_PROVIDER = {
    'OIDC_ENABLED': True,
    'OIDC_RSA_PRIVATE_KEY': OIDC_RSA_PRIVATE_KEY,
    'OIDC_ISS_ENDPOINT': f'https://{PROXY_DOMAIN}',
    'PKCE_REQUIRED': False,  # Relaxed for broad client compatibility (e.g. Moodle LMS)
    'OAUTH2_VALIDATOR_CLASS': 'core.oauth_validators.CustomOAuth2Validator',
    # Declared OIDC scopes to authorize user attributes
    'SCOPES': {
        'openid': 'OpenID Connect scope',
        'profile': 'Profile scope',
        'email': 'Email scope',
        'read': 'Read scope',
        'write': 'Write scope'
    },
}

# Redirect destinations for authentication lifecycle
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'
LOGIN_URL = '/'

REFEDS_MFA_PROFILE = 'https://refeds.org/profile/mfa'

# Authorized partner Identity Providers & testing endpoints (e.g. eduGAIN Access Check)
EUPEACE_PARTNER_IDPS = [
    'https://access-check.edugain.org/simplesaml/saml2/idp/metadata.php',
]

EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', default='localhost')
EMAIL_PORT = env.int('EMAIL_PORT', default=25)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_USE_SSL = env.bool('EMAIL_USE_SSL', default=False)
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default=f'noreply@{PROXY_DOMAIN}')

# Redis Caching & RAM Session Configuration
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': env('REDIS_URL', default='redis://127.0.0.1:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            # Resiliency: ignore temporary cache outages without crashing requests
            'IGNORE_EXCEPTIONS': True, 
        }
    }
}

# Move user sessions from database to Redis RAM
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

# --- USER PROVISIONING SETTINGS ---
SAML_DJANGO_USER_MAIN_ATTRIBUTE = 'username'
SAML_DJANGO_USER_MAIN_ATTRIBUTE_LOOKUP = '__iexact'
SAML_CREATE_UNKNOWN_USER = True  # Automatically provision user in local DB on first federated login

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[f'https://{PROXY_DOMAIN}'])

# --- HARDENED COOKIE CONFIGURATION FOR SAML & OIDC ---
SESSION_COOKIE_DOMAIN = env('SESSION_COOKIE_DOMAIN', default=f'.{PROXY_DOMAIN}')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'None'  # Mandatory for cross-origin SAML HTTP-POST bindings
CSRF_COOKIE_SAMESITE = 'None'
SESSION_SAVE_EVERY_REQUEST = True
