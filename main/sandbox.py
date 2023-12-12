from .settings import *

#LOGGING FOR SANDBOX

SANDBOX_APPS = (
#    'django_extensions',
)

INSTALLED_APPS = INSTALLED_APPS + SANDBOX_APPS 

if USE_AWS_EMAIL and ENV_TYPE == EnvironmentType.SANDBOX:
    OUT_OF_ORDER_TO_LIST = ['juaneljach10@gmail.com']
