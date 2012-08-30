from django.conf import settings


default_settings = {
    'MAX_RETRIES': 5,
    'RETRY_STEP': 30,
    'RETRY_BASE': 4
}


def get_setting(name):
    mailer_settings = default_settings
    mailer_settings.update(getattr(settings, 'ZTASKQ_MAILER', {}))
    return mailer_settings[name]
