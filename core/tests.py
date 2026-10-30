from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.urls import reverse
from oauth2_provider.models import Application
from core.models import UserProfile, AllianceService, AuditLog, UserFavoriteService


@override_settings(
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    },
    SESSION_ENGINE='django.contrib.sessions.backends.db',
)
class OAuth2GatekeepingTestCase(TestCase):
    def setUp(self):
        self.client = Client()

        # Users
        self.admin_user = User.objects.create_superuser(
            username='admin_user', email='admin@example.org', password='password123'
        )
        self.student_user = User.objects.create_user(
            username='student_user', email='student@example.org', password='password123'
        )
        self.staff_user = User.objects.create_user(
            username='staff_user', email='staff@example.org', password='password123'
        )
        self.guest_user = User.objects.create_user(
            username='guest_user', email='guest@external.org', password='password123'
        )

        # Setup authorized Identity Provider
        from core.models import IdentityProvider, GuestProfile
        from django.utils import timezone
        from datetime import timedelta

        self.idp = IdentityProvider.objects.create(
            name='Partner University IdP',
            short_code='PARTNER',
            entity_id='https://idp.example.org/idp/shibboleth',
            is_active=True
        )

        # Profiles
        self.student_user.profile.affiliation = 'member@example.org, student@example.org'
        self.student_user.profile.home_organization = 'example.org'
        self.student_user.profile.save()
        self.student_user._saml_issuer = self.idp.entity_id

        self.staff_user.profile.affiliation = 'member@example.org, staff@example.org'
        self.staff_user.profile.home_organization = 'example.org'
        self.staff_user.profile.save()
        self.staff_user._saml_issuer = self.idp.entity_id

        self.guest_user.profile.affiliation = ''
        self.guest_user.profile.home_organization = 'external.org'
        self.guest_user.profile.save()
        GuestProfile.objects.create(
            user=self.guest_user,
            invited_by=self.admin_user,
            valid_until=timezone.now() + timedelta(days=30)
        )
        self.guest_user._saml_issuer = 'https://external-idp.org'

        # OAuth2 Applications
        self.app_staff = Application.objects.create(
            name='Staff Moodle',
            client_id='client-staff-123',
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris='https://staff-moodle.eupeace.eu/oauth2/callback',
            user=self.admin_user,
            skip_authorization=True,
        )
        self.app_student = Application.objects.create(
            name='Student Moodle',
            client_id='client-student-123',
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris='https://student-moodle.eupeace.eu/oauth2/callback',
            user=self.admin_user,
            skip_authorization=True,
        )
        self.app_public = Application.objects.create(
            name='Public Portal',
            client_id='client-public-123',
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris='https://portal.eupeace.eu/oauth2/callback',
            user=self.admin_user,
            skip_authorization=True,
        )
        self.app_unlinked = Application.objects.create(
            name='Unlinked App',
            client_id='client-unlinked-123',
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris='https://other.eupeace.eu/oauth2/callback',
            user=self.admin_user,
            skip_authorization=True,
        )
        self.app_inactive = Application.objects.create(
            name='Inactive Service App',
            client_id='client-inactive-123',
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris='https://inactive.eupeace.eu/oauth2/callback',
            user=self.admin_user,
            skip_authorization=True,
        )

        # Alliance Services
        self.service_staff = AllianceService.objects.create(
            name='Staff Moodle Service',
            url='https://staff-moodle.eupeace.eu',
            visibility='STAFF',
            oauth_application=self.app_staff,
            is_active=True,
        )
        self.service_student = AllianceService.objects.create(
            name='Student Moodle Service',
            url='https://student-moodle.eupeace.eu',
            visibility='STUDENT',
            oauth_application=self.app_student,
            is_active=True,
        )
        self.service_public = AllianceService.objects.create(
            name='Public Service',
            url='https://portal.eupeace.eu',
            visibility='ALL',
            oauth_application=self.app_public,
            is_active=True,
        )
        self.service_inactive = AllianceService.objects.create(
            name='Maintenance Service',
            url='https://inactive.eupeace.eu',
            visibility='ALL',
            oauth_application=self.app_inactive,
            is_active=False,
        )

    def test_unauthenticated_user_redirects_to_login(self):
        url = f"{reverse('oauth2_provider:authorize')}?response_type=code&client_id={self.app_staff.client_id}&redirect_uri={self.app_staff.redirect_uris}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith('/?next='))

    def test_student_denied_from_staff_service(self):
        self.client.force_login(self.student_user)
        url = f"{reverse('oauth2_provider:authorize')}?response_type=code&client_id={self.app_staff.client_id}&redirect_uri={self.app_staff.redirect_uris}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, 'access_denied.html')
        self.assertContains(response, 'Access Restricted', status_code=403)
        self.assertContains(response, 'Faculty &amp; Staff only', status_code=403)

        # Verify audit log
        log_entry = AuditLog.objects.filter(
            eppn=self.student_user.username,
            service_client_id=self.app_staff.client_id,
            status='FAILURE'
        ).first()
        self.assertIsNotNone(log_entry)

    def test_staff_allowed_to_staff_service(self):
        self.client.force_login(self.staff_user)
        url = f"{reverse('oauth2_provider:authorize')}?response_type=code&client_id={self.app_staff.client_id}&redirect_uri={self.app_staff.redirect_uris}"
        response = self.client.get(url)
        # Should redirect to redirect_uri with auth code (skip_authorization=True)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(self.app_staff.redirect_uris))
        self.assertIn('code=', response.url)

    def test_staff_denied_from_student_service(self):
        self.client.force_login(self.staff_user)
        url = f"{reverse('oauth2_provider:authorize')}?response_type=code&client_id={self.app_student.client_id}&redirect_uri={self.app_student.redirect_uris}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, 'access_denied.html')
        self.assertContains(response, 'Students only', status_code=403)

    def test_student_allowed_to_student_service(self):
        self.client.force_login(self.student_user)
        url = f"{reverse('oauth2_provider:authorize')}?response_type=code&client_id={self.app_student.client_id}&redirect_uri={self.app_student.redirect_uris}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(self.app_student.redirect_uris))
        self.assertIn('code=', response.url)

    def test_guest_denied_from_staff_service(self):
        self.client.force_login(self.guest_user)
        url = f"{reverse('oauth2_provider:authorize')}?response_type=code&client_id={self.app_staff.client_id}&redirect_uri={self.app_staff.redirect_uris}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_all_users_allowed_to_public_service(self):
        for user in [self.student_user, self.staff_user, self.guest_user]:
            self.client.force_login(user)
            url = f"{reverse('oauth2_provider:authorize')}?response_type=code&client_id={self.app_public.client_id}&redirect_uri={self.app_public.redirect_uris}"
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith(self.app_public.redirect_uris))

    def test_unlinked_app_allowed_by_default(self):
        self.client.force_login(self.student_user)
        url = f"{reverse('oauth2_provider:authorize')}?response_type=code&client_id={self.app_unlinked.client_id}&redirect_uri={self.app_unlinked.redirect_uris}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(self.app_unlinked.redirect_uris))

    def test_inactive_service_denied_for_regular_users(self):
        self.client.force_login(self.student_user)
        url = f"{reverse('oauth2_provider:authorize')}?response_type=code&client_id={self.app_inactive.client_id}&redirect_uri={self.app_inactive.redirect_uris}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'currently disabled', status_code=403)

    def test_superuser_bypasses_all_restrictions(self):
        self.client.force_login(self.admin_user)
        # Access staff service
        url1 = f"{reverse('oauth2_provider:authorize')}?response_type=code&client_id={self.app_staff.client_id}&redirect_uri={self.app_staff.redirect_uris}"
        resp1 = self.client.get(url1)
        self.assertEqual(resp1.status_code, 302)

        # Access student service
        url2 = f"{reverse('oauth2_provider:authorize')}?response_type=code&client_id={self.app_student.client_id}&redirect_uri={self.app_student.redirect_uris}"
        resp2 = self.client.get(url2)
        self.assertEqual(resp2.status_code, 302)

        # Access inactive service
        url3 = f"{reverse('oauth2_provider:authorize')}?response_type=code&client_id={self.app_inactive.client_id}&redirect_uri={self.app_inactive.redirect_uris}"
        resp3 = self.client.get(url3)
        self.assertEqual(resp3.status_code, 302)


@override_settings(
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    },
    SESSION_ENGINE='django.contrib.sessions.backends.db',
)
class UserFavoriteServiceTestCase(TestCase):
    def setUp(self):
        from core.models import IdentityProvider
        self.client = Client()
        self.idp = IdentityProvider.objects.create(
            name='Università della Calabria',
            short_code='UNICAL',
            entity_id='https://idp.unical.it/idp/shibboleth',
            is_active=True
        )
        self.user = User.objects.create_user(
            username='fav_test_user', email='fav@example.org', password='password123'
        )
        self.user._saml_issuer = self.idp.entity_id
        self.service1 = AllianceService.objects.create(
            name='Service 1', description='Desc 1', url='https://s1.org', provider='UNICAL', is_active=True
        )
        self.service2 = AllianceService.objects.create(
            name='Service 2', description='Desc 2', url='https://s2.org', provider='MARBURG', is_active=True
        )

    def test_toggle_favorite_service_ajax(self):
        self.client.force_login(self.user)
        url = reverse('toggle_favorite_service', kwargs={'service_id': self.service1.id})

        # 1. Add favorite via AJAX
        response = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertTrue(data['is_favorite'])
        self.assertEqual(data['service_id'], self.service1.id)
        self.assertTrue(UserFavoriteService.objects.filter(user=self.user, service=self.service1).exists())

        # 2. Toggle again to remove favorite
        response2 = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response2.status_code, 200)
        data2 = response2.json()
        self.assertEqual(data2['status'], 'ok')
        self.assertFalse(data2['is_favorite'])
        self.assertFalse(UserFavoriteService.objects.filter(user=self.user, service=self.service1).exists())

    def test_dashboard_favorites_filter(self):
        self.client.force_login(self.user)
        UserFavoriteService.objects.create(user=self.user, service=self.service1)

        # Dashboard without filter: shows both services
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['page_obj']), 2)
        self.assertIn(self.service1.id, resp.context['user_favorite_ids'])
        self.assertEqual(resp.context['total_favorites_count'], 1)

        # Dashboard with favorites=1: only shows service1
        resp_fav = self.client.get(reverse('dashboard') + '?favorites=1')
        self.assertEqual(resp_fav.status_code, 200)
        self.assertEqual(len(resp_fav.context['page_obj']), 1)
        self.assertEqual(resp_fav.context['page_obj'][0].id, self.service1.id)


@override_settings(
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    },
    SESSION_ENGINE='django.contrib.sessions.backends.db',
)
class SecurityHardeningTestCase(TestCase):
    """
    Regression tests verifying cryptographic dependency baselines, Brotli decoder
    protection (CVE-2026-111497 / PYSEC-2026-4322 / PYSEC-2026-4323), and IDEM GARR /
    eduGAIN SAML 2.0 SP metadata structural integrity.
    """

    def test_brotli_decoder_not_vulnerable(self):
        import importlib.metadata
        from packaging.version import Version
        import requests
        import urllib3.response

        vulnerable_found = []
        for pkg_name, min_safe in [('Brotli', '1.2.1'), ('brotlicffi', '1.2.1.0')]:
            try:
                installed_ver = importlib.metadata.version(pkg_name)
                if Version(installed_ver) < Version(min_safe):
                    vulnerable_found.append(f"{pkg_name}=={installed_ver} (< {min_safe})")
            except importlib.metadata.PackageNotFoundError:
                pass

        self.assertEqual(
            vulnerable_found,
            [],
            f"Vulnerable Brotli package(s) detected (PYSEC-2026-4322/4323): {vulnerable_found}",
        )

        # When Brotli is omitted (default posture), urllib3/requests must not advertise 'br'
        if urllib3.response.brotli is None:
            session = requests.Session()
            prepared = session.prepare_request(requests.Request('GET', 'https://mdx.idem.garr.it/edugain/'))
            accept_enc = prepared.headers.get('Accept-Encoding', '')
            self.assertNotIn('br', [enc.strip() for enc in accept_enc.split(',')])

    def test_cryptography_and_pysaml2_security_baseline(self):
        import importlib.metadata
        from packaging.version import Version

        crypto_ver = Version(importlib.metadata.version('cryptography'))
        pysaml2_ver = Version(importlib.metadata.version('pysaml2'))

        # Mitigates CVE-2026-69249 & CVE-2026-26007
        self.assertGreaterEqual(crypto_ver, Version('49.0.0'))
        self.assertGreaterEqual(pysaml2_ver, Version('7.5.5'))

    def test_saml_metadata_generation_integrity(self):
        import datetime
        import tempfile
        from copy import deepcopy
        from django.conf import settings
        from defusedxml import ElementTree as ET
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = f"{tmpdir}/private.key"
            cert_path = f"{tmpdir}/public.cert"

            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            with open(key_path, 'wb') as f:
                f.write(key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption(),
                ))

            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, 'EU'),
                x509.NameAttribute(NameOID.COMMON_NAME, 'proxy.eupeace.eu'),
            ])
            cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(key.public_key())
                .serial_number(1)
                .not_valid_before(datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc))
                .not_valid_after(datetime.datetime(2036, 1, 1, tzinfo=datetime.timezone.utc))
                .sign(key, hashes.SHA256())
            )
            with open(cert_path, 'wb') as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))

            saml_cfg = deepcopy(settings.SAML_CONFIG)
            saml_cfg['key_file'] = key_path
            saml_cfg['cert_file'] = cert_path
            saml_cfg['encryption_keypairs'] = [{'key_file': key_path, 'cert_file': cert_path}]

            with override_settings(
                SAML_CONFIG=saml_cfg,
                ALLOWED_HOSTS=['proxy.eupeace.eu', 'testserver', 'localhost'],
            ):
                resp = self.client.get('/saml2/metadata/', HTTP_HOST='proxy.eupeace.eu', secure=True)
                self.assertEqual(resp.status_code, 200)

                ns = {'md': 'urn:oasis:names:tc:SAML:2.0:metadata'}
                root = ET.fromstring(resp.content)
                self.assertEqual(root.attrib.get('entityID'), saml_cfg['entityid'])

                sp_sso = root.find('md:SPSSODescriptor', ns)
                self.assertIsNotNone(sp_sso)
                self.assertEqual(sp_sso.attrib.get('AuthnRequestsSigned'), 'true')
                self.assertEqual(sp_sso.attrib.get('WantAssertionsSigned'), 'true')

                key_uses = [kd.attrib.get('use') for kd in sp_sso.findall('md:KeyDescriptor', ns)]
                self.assertIn('signing', key_uses)
                self.assertIn('encryption', key_uses)

                acs = sp_sso.find('md:AssertionConsumerService', ns)
                self.assertIsNotNone(acs)
                self.assertTrue(acs.attrib.get('Location', '').endswith('/saml2/acs/'))

                contacts = root.findall('md:ContactPerson', ns)
                self.assertGreaterEqual(len(contacts), 3)


