from django.contrib import admin
from .models import GuestInvitation, GuestProfile, AllianceService, IdentityProvider, AuditLog, UserFavoriteService


@admin.register(GuestInvitation)
class GuestInvitationAdmin(admin.ModelAdmin):
    list_display = ('guest_email', 'inviter', 'created_at', 'expires_at', 'is_used', 'is_valid_status')
    list_filter = ('is_used', 'created_at')
    search_fields = ('guest_email', 'inviter__email', 'inviter__username')
    
    def is_valid_status(self, obj):
        return obj.is_valid()
    is_valid_status.boolean = True
    is_valid_status.short_description = "Valid"

@admin.register(GuestProfile)
class GuestProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'invited_by', 'valid_until')
    search_fields = ('user__username', 'user__email', 'invited_by__email')
    
@admin.register(AllianceService)
class AllianceServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'provider', 'visibility', 'is_active', 'oauth_application')
    list_filter = ('visibility', 'is_active', 'provider')
    search_fields = ('name', 'description')
    raw_id_fields = ('oauth_application',)

@admin.register(IdentityProvider)
class IdentityProviderAdmin(admin.ModelAdmin):
    list_display = ('name', 'short_code', 'supports_mfa', 'is_active')
    list_filter = ('supports_mfa', 'is_active')
    search_fields = ('name', 'short_code', 'entity_id')

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'eppn', 'status', 'ip_address', 'idp_entity_id', 'service_client_id')
    list_filter = ('status', 'timestamp', 'idp_entity_id')
    search_fields = ('eppn', 'ip_address', 'service_client_id')
    readonly_fields = ('timestamp', 'eppn', 'ip_address', 'idp_entity_id', 'service_client_id', 'status')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

@admin.register(UserFavoriteService)
class UserFavoriteServiceAdmin(admin.ModelAdmin):
    list_display = ('user', 'service', 'created_at')
    list_filter = ('created_at', 'service__provider')
    search_fields = ('user__username', 'user__email', 'service__name')
    raw_id_fields = ('user', 'service')