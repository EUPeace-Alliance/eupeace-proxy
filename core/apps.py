from django.apps import AppConfig


from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        import core.signals

        # Monkey-patch to solve djangosaml2 bug with MDQ
        from djangosaml2 import utils as djangosaml2_utils
        import djangosaml2.views
        from saml2.mdstore import MetaDataMDX

        def safe_available_idps(config, langpref=None, idp_to_check=None):
            if langpref is None:
                langpref = "en"
            idps = set()
            for metadata in config.metadata.metadata.values():
                if isinstance(metadata, MetaDataMDX) and idp_to_check:
                    try:
                        m = metadata[idp_to_check]
                    except KeyError:
                        pass
                result = metadata.any("idpsso_descriptor", "single_sign_on_service")
                if result:
                    idps.update(result.keys())
            return {idp: config.metadata.name(idp, langpref) for idp in idps}

        djangosaml2_utils.available_idps = safe_available_idps
        djangosaml2.views.available_idps = safe_available_idps