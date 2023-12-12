import base64
import boto3
import logging
from botocore.exceptions import ClientError
import json
from django import forms
from django.conf import settings
from django.core.mail import EmailMessage
from sentry_sdk import capture_exception
from sentry_sdk import configure_scope

logger = logging.getLogger()


class ParameterGetter():
    """
    Local client for AWS SSM Parameter Store
    """

    @classmethod
    def get(cls, name=None):
        if not name: return name
        client = boto3.client('ssm')
        try:
            param_object = client.get_parameter(Name=name)
        except ClientError as e:
            logger.error(e, exc_info=True)
            return None
        param_type = param_object['Parameter']['Type']
        if param_type == 'SecureString':
            param_object = client.get_parameter(Name=name, WithDecryption=True)
        val = param_object['Parameter']['Value']
        if param_type == 'StringList':
            val = val.strip('][').split(',')
        return val


def custom_capture_exception(err, msg=None):
    if settings.IS_PRODUCTION:
        if msg is not None:
            with configure_scope() as scope:
                scope.set_extra("custom_message", msg)
        capture_exception(err)
    else:
        logger.error(err)


class FieldExtractor():

    @classmethod
    def extract_fields(cls, fields, obj):
        row = []
        for field in fields:
            if hasattr(obj, field):
                value = getattr(obj, field)
                if callable(value):
                    value = value()
            else:
                if '__' in field:
                    try:
                        value = obj
                        for deep_field in field.split('__'):
                            value = getattr(value, deep_field)
                            if value is None:
                                break
                    except Exception as e:
                        logger.error(e)
                        raise Exception(e)
            row.append(value)
        return row


class CustomDateInput(forms.widgets.TextInput):
    input_type = 'date'

LEVEL_MAP = [
    'DEBUG',
    'INFO',
    'ERROR',
    'CRITICAL',
]

class WatchTowerLogger:
    default_handler = 'watchtower.CloudWatchLogHandler'
    use_queues = True


    def __init__(self, modules, env, boto3_session, custom_handler='watchtower'):
        self.boto3_session = boto3_session
        self.modules = modules
        self.handlers_dict = {}
        self.loggers_dict = {}
        self.environment_name = env
        self.custom_logger_handler = custom_handler
        self.setup()

    def setup_boto3(self):
        self.boto3_session = boto3.session.Session()

    def create_handler(self, module, level):
        handler = {}
        handler_name = "{}_{}_{}".format(self.custom_logger_handler, module, level.lower())
        handler[handler_name] = {
                    'level' : level.upper(),
                    'class' : self.default_handler,
                    'boto3_session' : self.boto3_session,
                    'log_group' : "{}-{}".format(
                        self.environment_name, module),
                    'stream_name' : level.lower(),
                    'use_queues' : self.use_queues,
                    'formatter' : 'aws'
        }
        self.update_attrs(module, handler_name)
        return handler

    def update_attrs(self, module, handler_name):
        if not module in self.__dict__:
            self.__dict__[module] = [handler_name]
        else:
            self.__dict__[module].append(handler_name)

    def create_logger(self, module, levels, propagate):
        """
         Adds the less important level as initial level for logger.
        """
        int_levels = list(map(lambda level: LEVEL_MAP.index(level), levels))
        sorted_int_levels = sorted(int_levels)
        logger_data = {
           'handlers' : getattr(self, module),
           'level' : LEVEL_MAP[sorted_int_levels[0]],
           'propagate': propagate
        }
        if not propagate:
            logger_data.pop('propagate')
        self.loggers_dict[module] = logger_data

    def setup(self):
        for module, data_dict in self.modules.items():
            levels = data_dict['levels']
            generate_handler = data_dict.get('generate_logger', True)
            propagate = data_dict.get('propagate', False)
            module_handlers = [self.create_handler(module, level) for level in levels]
            for handler in module_handlers:
                self.handlers_dict.update(handler)
            if generate_handler:
                self.create_logger(module, levels, propagate)
            #map(lambda x: setattr(self, module, x), [handler['name'] for handler in module_handlers])

    def get_handlers(self):
        return self.handlers_dict

    def get_loggers(self):
        return self.loggers_dict


class SecretManager():
    default_db_engine = "django.db.backends.mysql"

    def __init__(self, secret_name, db_name=None):
        self.secret_name = secret_name
        self.db_name = db_name

    def format_db(self):
        if not getattr(self, 'secret', None):
            self.get_secret()
        data = {
            "default": {
                "ENGINE": self.default_db_engine,
                "NAME": self.db_name,
                "USER": self.secret.get("username"),
                "PASSWORD": self.secret.get("password"),
                "HOST": self.secret.get("host"),
                "PORT": self.secret.get("port"),
            }
        }
        return data

    def get_secret_value(self):
        self.get_secret()
        if isinstance(self.secret, dict):
            return list(self.secret.values())[0]

    def get_secret(self):
        secret_name = self.secret_name
        region_name = "us-east-1"

        # Create a Secrets Manager client
        session = boto3.session.Session()
        client = session.client(
            service_name='secretsmanager',
            region_name=region_name
        )

        # In this sample we only handle the specific exceptions for the 'GetSecretValue' API.
        # See https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        # We rethrow the exception by default.

        try:
            get_secret_value_response = client.get_secret_value(
                SecretId=secret_name
            )
        except ClientError as e:
            if e.response['Error']['Code'] == 'DecryptionFailureException':
                # Secrets Manager can't decrypt the protected secret text using the provided KMS key.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise e
            elif e.response['Error']['Code'] == 'InternalServiceErrorException':
                # An error occurred on the server side.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise e
            elif e.response['Error']['Code'] == 'InvalidParameterException':
                # You provided an invalid value for a parameter.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise e
            elif e.response['Error']['Code'] == 'InvalidRequestException':
                # You provided a parameter value that is not valid for the current state of the resource.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise e
            elif e.response['Error']['Code'] == 'ResourceNotFoundException':
                # We can't find the resource that you asked for.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise e
        else:
            # Decrypts secret using the associated KMS CMK.
            # Depending on whether the secret is a string or binary, one of these fields will be populated.
            if 'SecretString' in get_secret_value_response:
                secret = get_secret_value_response['SecretString']
            else:
                decoded_binary_secret = base64.b64decode(get_secret_value_response['SecretBinary'])
                secret = decoded_binary_secret
        self.secret = json.loads(secret)


class EmailExceptionClient():
    """
    Reports exceptions via email
    """

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.content_type = None
        self._build_to_list()

    def _build_to_list(self):
        current_to = None
        if 'to' in self.kwargs and self.kwargs.get('to') is not None:
            if isinstance(self.kwargs.get('to'), str): current_to = self.kwargs.get('to').split(',')
            elif isinstance(self.kwargs.get('to'), list): current_to = self.kwargs.get('to')
        to = settings.IT_EMAIL_LIST
        if current_to: to.extend(current_to)
        self.kwargs['to'] = to
        
    def send(self):
        message = EmailMessage(**self.kwargs)
        if self.content_type: message.content_subtype = self.content_type
        message.send(fail_silently=False)