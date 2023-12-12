import logging
from django.contrib.contenttypes.models import ContentType


logger = logging.getLogger(__name__)


class EventRuleProcessor():
    
    def __init__(self, request_body):
        self.request_body = request_body

    def find_config(self):
        resources = self.request_body.get('resources')
        if not resources: return False
        arn_name = resources[0]
        config_name = arn_name.split('/')[1]
        assert '-' in config_name #it's supposed to follow format ModelNameConfig-Timestamp
        config_model_name = config_name.split('-')[0]
        model_content_type = ContentType.objects.get(app_label='reports', model=config_model_name)
        model_class = model_content_type.model_class()
        config_instance = model_class.objects.filter(event_rule__arn=arn_name)
        return config_instance

    def process(self):
        logger.info(f"Event Rule Processor: {self.request_body}")
        config = self.find_config().first()
        logger.info("got config while processing an event-rule job: {}".format(config))
        config.process_as_job()