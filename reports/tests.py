import json
import time
from datetime import datetime
from botocore.exceptions import ClientError
from django.test import TestCase
from reporting.enums import DurationType, LocationLevel, MetricType, SortParameters
from .api import EventsManager
from .jobs import EventRuleProcessor
from .models import EventRule, InternalReportConfig

# Create your tests here.
class TestEventRuleProcessor(TestCase):
    def setUp(self):
        timestamp = str(
            datetime.timestamp(datetime.now())
        ).split('.')[0]
        self.event_rule_response = EventsManager().create(
            event_rule_name = 'InternalReportConfig-{}'.format(timestamp),
            cron_expression = '0/25 * * * ? *',
            description = 'unit test'
        )
        self.arn = self.event_rule_response.get('event_rule_arn')
        self.event_rule_obj = EventRule.objects.create(
            name = 'InternalReportConfig-{}'.format(timestamp),
            arn = self.event_rule_response.get('event_rule_arn'),
            target_id = self.event_rule_response.get('target_id')
        )
        report_config_instance = InternalReportConfig.objects.create(
            time_grouping = DurationType.MONTH,
            location_grouping = LocationLevel.LAUNDRY_ROOM,
            revenue_rule = MetricType.FASCARD_REVENUE_FUNDS,
            sort_by = SortParameters.FASCARD_CODE,
            email = "suricatadev@gmail.com",
            cron_expression = "0/25 * * * ? *"
        )
        report_config_instance.event_rule = self.event_rule_obj
        report_config_instance.save()

    def test_event_rule_config_finder(self):
        self.fake_sqs_msg_body = {
            "version": "0",
            "id": "bb8f4213-a9f8-81f9-9a8d-b9ee70d73d5e",
            "detail-type": "Scheduled Event",
            "source": "aws.events",
            "account": "645868669589",
            "time": "2021-05-18T21:06:00Z",
            "region": "us-east-1",
            "resources": [self.arn],
            "detail": {}
        }
        processor = EventRuleProcessor(self.fake_sqs_msg_body)
        config_query = processor.find_config()
        self.assertEqual(config_query.count(), 1)

    def test_delete(self):
        event_bridge_manager = EventsManager()
        time.sleep(10)
        event_bridge_manager.delete_rule(self.event_rule_obj.name)
        try:
            response = event_bridge_manager.client.describe_rule(Name=self.event_rule_obj.name)
            raise Exception("Rule was not deleted")
        except ClientError as error:
            self.assertIn('does not exist', error.response['Error']['Message'])