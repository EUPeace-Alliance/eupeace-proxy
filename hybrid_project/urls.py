from django.contrib import admin
from django.urls import path, include
from django.conf.urls import handler403
from core import views
from django.views.generic import TemplateView
from core.views import CustomSAML2LoginView, custom_logout, CustomAuthorizationView
from django.views.decorators.csrf import csrf_exempt
from djangosaml2 import views as djangosaml2_views
from oauth2_provider import urls as oauth2_urls

oauth2_patterns = [
    path('authorize/', CustomAuthorizationView.as_view(), name='authorize'),
] + [p for p in oauth2_urls.urlpatterns if getattr(p, 'name', None) != 'authorize']

urlpatterns = [
    path('gestione/', admin.site.urls),
    path('', views.wayf_view, name='wayf'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('logout/', custom_logout, name='custom_logout'),
    
    path('saml2/login/', CustomSAML2LoginView.as_view(), name='saml2_login'),
    path('saml2/', include('djangosaml2.urls')),
    path('o/', include((oauth2_patterns, 'oauth2_provider'), namespace='oauth2_provider')),
    path('invite/new/', views.create_invitation_view, name='create_invitation'),
    path('invite/<uuid:token>/', views.redeem_invite_view, name='redeem_invite'),
    path('invite/<uuid:token>/revoke/', views.revoke_invitation_view, name='revoke_invitation'),
    path('privacy/', TemplateView.as_view(template_name='privacy.html'), name='privacy'),
    path('helpdesk/', TemplateView.as_view(template_name='helpdesk.html'), name='helpdesk'),
    path('info/', TemplateView.as_view(template_name='info.html'), name='service_info'),
]
handler403 = views.custom_permission_denied_view