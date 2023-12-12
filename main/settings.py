import boto3
import os
import csv
import json
import sys
from django.utils.translation import gettext_lazy as _
from main import secretkeys
from main.utils import WatchTowerLogger, SecretManager, ParameterGetter
from Utils.patchenv import EnvironmentPatcher


class EnvironmentType(object):
    SANDBOX = 'Sandbox'
    PRODUCTION = 'Production'
    LOCAL = 'Local'

class SetupSettings():

    @classmethod
    def get_credentials(cls,file_name):
        with open(file_name) as f:
            cred_text = f.read()
            return json.loads(cred_text)

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')



SITE_ID = 1

DB_SECRET_NAME = None

try:
    EnvironmentPatcher.patch()
except:
    pass


if os.environ.get('IS_BACKEND'):
    IS_BACKEND = True
    IS_FRONTEND= False
    DEBUG = False
else:
    IS_BACKEND = False
    IS_FRONTEND= True
    DEBUG = False

DB_CLUSTER_IDENTIFIER = None

if os.environ.get('IS_PRODUCTION'):
    ENV_TYPE = EnvironmentType.PRODUCTION
    CRED_FOLDER = 'prod'
    DB_CRED_FOLDER = 'prod'
    DB_SECRET_NAME = 'rds-db-credentials/cluster-BQDDJEPYAAAPGJLRNPXMC5WPEQ/laundryuser'
    DB_NAME = "laundrydb"
    ON_AWS = True
    USE_SENTRY_LOGGING = True
    DB_CLUSTER_IDENTIFIER = 'py3-production-database'
elif os.environ.get('IS_SANDBOX'):
    ENV_TYPE =  EnvironmentType.SANDBOX
    CRED_FOLDER = 'sandbox'
    DB_CRED_FOLDER = 'sandbox'
    ON_AWS = True
    USE_SENTRY_LOGGING = False
    DB_CLUSTER_IDENTIFIER = 'sandbox-test-cluster'
    DEBUG=True
    #TODO: Add DB Cluster Identifier for sandbox env
else:
    ENV_TYPE = EnvironmentType.LOCAL
    CRED_FOLDER = 'sandbox' #TODO: change back
    DB_CRED_FOLDER = 'local'
    ON_AWS = False
    DEBUG = True
    IS_BACKEND = True
    DB_CLUSTER_IDENTIFIER = 'sandbox-test-cluster' #For testing purposes
    USE_SENTRY_LOGGING = False
#Just a test
if os.environ.get("TEST_PROD"):
    CRED_FOLDER = 'testprod'
    DB_CRED_FOLDER = 'testprod'

IS_PRODUCTION = (ENV_TYPE == EnvironmentType.PRODUCTION)
IS_SANDBOX = (ENV_TYPE == EnvironmentType.SANDBOX)

BASE_DIR =  os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..'))
WSGI_DIR = BASE_DIR
REPO_DIR = BASE_DIR

#STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')
#STATIC_ROOT = "/var/www/supersecure.codes/static"
#STATICFILES_DIRS = [BASE_DIR / "static"]

AWS_STORAGE_BUCKET_NAME  = 'laundry-static'
AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
S3_STATIC_DIR = 'static'
STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/{S3_STATIC_DIR}/'
#STATICFILES_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'

STATICFILES_STORAGE = "main.storage.ManifestStaticFilesStorage"


MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

TEST_FILE_FOLDER = os.path.join(BASE_DIR,'test_files')
LOG_DIR = os.path.join(REPO_DIR, 'logs')

if ON_AWS:
    USE_BING_PROD = True
    DATA_DIR = os.path.join(REPO_DIR, '/tmp')
    TEMP_DIR = '/tmp'
    USE_STRIPE_PROD = True
    USE_AWS_EMAIL = True
else:
    USE_BING_PROD = False
    DATA_DIR = os.path.join(REPO_DIR, 'data')
    TEMP_DIR = os.path.join(REPO_DIR, 'temp_files')
    USE_STRIPE_PROD = False
    USE_AWS_EMAIL = True


#DATABASE_ROUTERS = ['main.dbrouters.DBRouter']
DB_CRED_FILE = os.path.join(BASE_DIR,'credentials', DB_CRED_FOLDER, 'db.txt')
AWS_CONFIG_FILE = os.path.join(BASE_DIR,'credentials', CRED_FOLDER, 'aws.txt')
FASCARD_CREDENTIALS_FILE = os.path.join(BASE_DIR,'credentials', CRED_FOLDER, 'fascard_credentials.csv')
QUEUE_CREDENTIALS_FILE = os.path.join(BASE_DIR,'credentials', CRED_FOLDER, 'queue.txt')

QUEUE_CREDENTIALS = SetupSettings.get_credentials(QUEUE_CREDENTIALS_FILE)

#Selenium
#SELENIUM_CONFIG_FILE = os.path.join(BASE_DIR,'credentials', CRED_FOLDER, 'selenium.txt')
#SELENIUM_CREDENTIALS = SetupSettings.get_credentials(SELENIUM_CONFIG_FILE)
#PHANTOM_JS_PATH = SELENIUM_CREDENTIALS['PHANTOM_JS_PATH']
#PHANTOM_JS_LOG_PATH = SELENIUM_CREDENTIALS['PHANTOM_JS_LOG_PATH']


os.environ["AWS_CONFIG_FILE"] = AWS_CONFIG_FILE

FASCARD_CREDENTIALS = {}
with open(FASCARD_CREDENTIALS_FILE) as f:
    rows = csv.reader(f)
    next(rows)
    for row in rows:
        FASCARD_CREDENTIALS[row[0].lower().strip()]=row[1:]

FASCARD_USERNAME = ParameterGetter.get(name='LaundrySystem-FascardUserName')
FASCARD_PASSWORD = ParameterGetter.get(name='LaundrySystem-FascardUserPassword')


if IS_PRODUCTION: SECRET_KEY = ParameterGetter.get(name='LaundrySystem-Secret-Key')
else: SECRET_KEY =  secretkeys.generator()['secret_key']

#TODO: add in sandbox
ALLOWED_HOSTS = [
'laundrysystem20-frontend-8.us-east-1.elasticbeanstalk.com',
'system.aceslaundry.com',
'laundrysandbox-frontend.us-east-1.elasticbeanstalk.com',
'127.0.0.1',
'localhost',
'frontend-sandbox.mzfp83dj3z.us-east-1.elasticbeanstalk.com', #new sandbox env
'py3-frontend.mzfp83dj3z.us-east-1.elasticbeanstalk.com', #new py3 env
'py3reporting.aceslaundry.com', #CNAME for py3env
'py3temp-front.mzfp83dj3z.us-east-1.elasticbeanstalk.com',
'*.aceslaundry.com',
'*'
]


# Application definition
INSTALLED_APPS = (
    'django.contrib.sites',
    'rest_framework',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'import_export',
    'main',
    'roommanager',
    'revenue',
    'outoforder',
    'reporting',
    'reports',
    'upkeep',
    

    #'maintainx',
    'django_extensions',
    'queuehandler',
    'expensetracker',
    'storages',
    'profiles',
    'formtools',
    'explorer',
    'data_browser',
)

AWS_DEFAULT_ACL = None


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


# DEBUG_TOOLBAR_PANELS = [
#     'debug_toolbar.panels.versions.VersionsPanel',
#     'debug_toolbar.panels.timer.TimerPanel',
#     'debug_toolbar.panels.settings.SettingsPanel',
#     'debug_toolbar.panels.headers.HeadersPanel',
#     'debug_toolbar.panels.request.RequestPanel',
#     'debug_toolbar.panels.sql.SQLPanel',
#     'debug_toolbar.panels.cache.CachePanel',
#     'debug_toolbar.panels.signals.SignalsPanel',
#     'debug_toolbar.panels.logging.LoggingPanel',
#     'debug_toolbar.panels.redirects.RedirectsPanel',
#     'debug_toolbar.panels.profiling.ProfilingPanel',
# ]

ROOT_URLCONF = 'main.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
           os.path.join(BASE_DIR,'finance','templates')
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                # Insert your TEMPLATE_CONTEXT_PROCESSORS here or use this
                # list if you haven't customized them:
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.debug',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                'django.template.context_processors.static',
                'django.template.context_processors.tz',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.request',
            ],
        },
    },
]


WSGI_APPLICATION = 'wsgi.application'


if DB_SECRET_NAME:
    DATABASES = SecretManager(DB_SECRET_NAME, DB_NAME).format_db()
else:
    DATABASES = SetupSettings.get_credentials(DB_CRED_FILE)


# Internationalization
# https://docs.djangoproject.com/en/1.8/topics/i18n/

LANGUAGE_CODE = 'en-us'

USE_I18N = True

USE_L10N = True

USE_TZ = False

TIME_ZONE = 'America/New_York'

LANGUAGES = [
    ('en', _('English')),
    ('es', _('Spanish')),
]

LOCALE_PATHS = [os.path.join(BASE_DIR, 'locale')]

#INTERNAL_IPS = ('127.0.0.1',)

DEFAULT_LAUNDRYROOM_TIMEZONE = 'US/Eastern'

STATICFILES_DIRS = (
     os.path.join(BASE_DIR,'main','static'),
#     os.path.join(os.path.dirname(__file__),'static','images'),
#     os.path.join(os.path.dirname(__file__),'static','js'),
)


# REST_FRAMEWORK = {
#     'DEFAULT_PERMISSION_CLASSES': (
#         'rest_framework.permissions.IsAuthenticated',
#     )
# }

PRICING_REPORT_DEFAULT_EMAIL_TO = 'daniel.scharfman@gmail.com'

DEFAULT_IT_EMAIL = ParameterGetter.get(name='LaundrySystem-DEFAULT_IT_EMAIL')


if USE_AWS_EMAIL:
    EMAIL_USE_TLS = True
    EMAIL_HOST = 'email-smtp.us-east-1.amazonaws.com'
    EMAIL_PORT = 25
    EMAIL_HOST_USER = 'AKIAJMW4L6C5X7M5SIIA'
    EMAIL_HOST_PASSWORD = SecretManager('LaundrySystem/EMAIL_HOST_PASSWORD').get_secret_value()
    DEFAULT_FROM_EMAIL = ParameterGetter.get(name='LaundrySystem-DefaultFromEmail')
    DEFAULT_TO_EMAILS = ParameterGetter.get(name='LaundrySystem-DEFAULT_TO_EMAILS')
    OUT_OF_ORDER_TO_LIST = ParameterGetter.get(name='LaundrySystem-OUT_OF_ORDER_TO_LIST')
    IT_EMAIL_LIST = ParameterGetter.get(name='LaundrySystem-IT_EMAIL_LIST')
    PRICING_CHANGES_EMAIL_LIST = ParameterGetter.get(name='LaundrySystem-PricingChange-MailingList')
else:
    EMAIL_USE_TLS = True
    EMAIL_HOST = 'smtp.gmail.com'
    EMAIL_PORT = 587
    EMAIL_HOST_USER = 'SerengetiAnalytics@gmail.com'
    EMAIL_HOST_PASSWORD = '1Or$d@taAnd'
    DEFAULT_FROM_EMAIL = 'SerengetiAnalytics@gmail.com'
    # EMAIL_HOST = 'email-smtp.us-east-1.amazonaws.com'
    # EMAIL_PORT = 25
    # EMAIL_HOST_USER = 'AKIAJMW4L6C5X7M5SIIA'
    # EMAIL_HOST_PASSWORD = 'AkMeaskfqEmELIAIE40DspwFnIr8DcjIURjRENmkP3tz'
    # DEFAULT_FROM_EMAIL = 'Aces Laundry <noreply@amazonses.aceslaundry.com>'
    DEFAULT_TO_EMAILS = ['suricatadev@gmail.com', 'robzu.99@gmail.com']
    OUT_OF_ORDER_TO_LIST = ['suricatadev@gmail.com', 'robzu.99@gmail.com']
    IT_EMAIL_LIST = ['suricatadev@gmail.com', 'robzu.99@gmail.com']
    PRICING_CHANGES_EMAIL_LIST = IT_EMAIL_LIST

if USE_SENTRY_LOGGING:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    sentry_sdk.init(
        dsn=ParameterGetter.get(name='LaundrySystem-SentryDNS'),
        integrations=[DjangoIntegration()]
    )


if ON_AWS:
    LOG_PATH = '/var/log/app-logs'
else:
    LOG_PATH = BASE_DIR + "/"

# if IS_PRODUCTION and IS_BACKEND:
#     logging_env_name = 'production-backend'
# elif IS_PRODUCTION and IS_FRONTEND:
#     logging_env_name = 'production-frontend'
# elif IS_SANDBOX and IS_BACKEND:
#     logging_env_name = 'sandbox-backend'
# elif IS_SANDBOX and IS_FRONTEND:
#     logging_env_name = 'sandbox-frontend'
# else:
#     logging_env_name = 'local'

if IS_PRODUCTION:
    logging_env_name = 'production'
elif IS_SANDBOX:
    logging_env_name = 'sandbox'
else:
    logging_env_name = 'local'

if os.environ.get('PYTHON3'):
    logging_env_name = 'py3'+logging_env_name

if os.environ.get('PY3TEMP'):
    logging_env_name = 'py3temp'+logging_env_name

boto3_session = boto3.session.Session()

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'console': {
            'format': '%(asctime)s %(name)-12s %(levelname)-8s %(module)s %(message)s',
        },
        'aws': {
            'format': u"%(asctime)s %(name)-12s [%(levelname)-8s] %(module)s-%(funcName)s: %(message)s",
            'datefmt': "%Y-%m-%d %H:%M:%S"
        },
    },
    'handlers': {
        'null': {
            'level': 'DEBUG',
            'class': 'logging.NullHandler',
        },
    },
    'loggers': {
        'django.security.DisallowedHost': {
            'handlers': ['null'],
            'propagate': False,
        },
    },
}

if logging_env_name != 'local':
    #Tuple first position: List of verbosity levels
    #Tuple second position: auto-generate logger or not
    #when logger auto-generate is setted to False, it's necessary to define a logger by hand
    MODULES_FOR_LOGGING = {
            'reporting': {
                'levels': ['ERROR', 'INFO'],
            },
            'reports': {
                'levels': ['ERROR', 'INFO'],
            },
            'outoforder': {
                'levels': ['ERROR', 'INFO'],
            },
            'fascard': {
                'levels': ['ERROR', 'INFO'], 
            },
            'queuehandler': {
                'levels': ['ERROR', 'INFO'],
            },
            'roommanager': {
                'levels': ['ERROR', 'INFO'], 
            },
            'main': {
                'levels': ['ERROR', 'INFO'], 
            },
            'revenue': {
                'levels': ['ERROR', 'INFO'], 
            },
            'upkeep': {
                'levels': ['ERROR', 'INFO'], 
            },
            'cmmsproviders': {
                'levels': ['ERROR', 'INFO'], 
            },
            'maintainx': {
                'levels': ['ERROR', 'INFO'], 
            },
            'Utils': {
                'levels': ['ERROR', 'INFO'], 
            },
            'django': {
                'levels': ['ERROR'],
                'propagate': True
            }
    }

    LOGGER_HANDLER = 'watchtower'

    WatchTowerLoggerHandler =  WatchTowerLogger(MODULES_FOR_LOGGING, logging_env_name, boto3_session)
    extra_handlers = WatchTowerLoggerHandler.get_handlers()
    extra_loggers = WatchTowerLoggerHandler.get_loggers()

    LOGGING['handlers'].update(extra_handlers)
    LOGGING['loggers'].update(extra_loggers)


TMP_STORAGE_ROOT = os.path.join(BASE_DIR,'tmp')

FASCARD_ACES_ID = ParameterGetter.get(name='LaundrySystem-FASCARD_ACES_ID')

METRIC_TRAILING_DAYS = 3

#UPKEEP API CREDENTIALS
UPKEEP_USER = SecretManager('LaundrySystem/UPKEEP_USER').get_secret_value()
UPKEEP_PASSWORD = SecretManager('LaundrySystem/UPKEEP_PASSWORD').get_secret_value()


UPKEEP_METER_FREQUENCY = '1'
UPKEEP_METER_UNITS = 'Total Cycle Count'

MAIN_DOMAIN = ParameterGetter.get(name='LaundrySystem-MAIN_DOMAIN')

if IS_PRODUCTION:
    DEFAULT_BUNDLE_CHANGE_REQ_EMAILS = ParameterGetter.get(name='LaundrySystem-BundleChanges-MailingList')
else:
    DEFAULT_BUNDLE_CHANGE_REQ_EMAILS = ['suricatadev@gmail.com','robzu.99@gmail.com']

# TESTING = len(sys.argv) > 1 and sys.argv[1] == 'test'
# if TESTING:
#     print('=========================')
#     print('In TEST Mode - Disableling Migrations')
#     print('=========================')
#
#     class DisableMigrations(object):
#
#         def __contains__(self, item):
#             return True
#
#         def __getitem__(self, item):
#             return "notmigrations"
#
#     MIGRATION_MODULES = DisableMigrations()


#API KEYS

API2_PDF_KEY = SecretManager('LaundrySystem/API2_PDF_KEY').get_secret_value()

#Maintainx Config

MAINTAINX_API_KEY = ParameterGetter.get(name='MAINTAINX_API_KEY')

MAINTAINX_METER_FREQUENCY = ParameterGetter.get(name='MAINTAINX_METER_FREQUENCY')

MAINTAINX_METER_UNITS = ParameterGetter.get(name='MAINTAINX_METER_UNITS')

MAINTAINX_ADMIN_TEAM_ID = ParameterGetter.get(name='MAINTAINX_ADMIN_TEAM_ID')

MAINTAINX_PRICING_CHANGES_TEAM_ID = ParameterGetter.get(name='MAINTAINX_PRICING_CHANGES_TEAM_ID')

#data explorer
EXPLORER_CONNECTIONS = { 'Default': 'default' }

EXPLORER_DEFAULT_CONNECTION = 'default'

REVENUE_ANOMALY_MAILING_LIST = ParameterGetter.get(name='LaundrySystem-RevenueAnomaly-MailList')