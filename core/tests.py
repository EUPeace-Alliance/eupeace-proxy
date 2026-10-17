from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.urls import reverse
from oauth2_provider.models import Application
from core.models import UserProfile, AllianceService, AuditLog


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
