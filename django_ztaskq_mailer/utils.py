from django.conf import settings


default_settings = {
    'MAX_RETRIES': 5,
    'RETRY_STEP': 30,
    'RETRY_BASE': 4
}


def get_setting(name):
    return getattr(settings, 'ZTASKQ_MAILER', {}).get(
        name,
        default_settings[name]
    )
