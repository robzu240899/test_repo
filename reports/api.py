import boto3
import json
import logging
import random
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class EventsManager():
    default_queue_arn = "arn:aws:sqs:us-east-1:645868669589:AL2ProductionQueue"
    default_queue_url = "https://sqs.us-east-1.amazonaws.com/645868669589/AL2ProductionQueue"
    policy_base_dict = {
        "Sid": None,
        "Effect": "Allow",
        "Principal": {
        "Service": "events.amazonaws.com"
        },
        "Action": "sqs:SendMessage",
        "Resource": None,
        "Condition": {
            "ArnEquals": 
            {
                    "aws:SourceArn": None
            }
        }
    }

    def __init__(self):
        self.client = boto3.client('events')

    def get(self, event_rule_name):
        try:
            get_response = self.client.describe_rule(
                Name=event_rule_name)
            return get_response
        except ClientError as e:
            logger.error(e, exc_info=True)
            return None
        
    def add_target(self, event_rule_name, target_id):
        response = self.client.put_targets(
            Rule=event_rule_name,
            Targets = [
                {
                    'Id': str(target_id),
                    'Arn': self.default_queue_arn
                }
            ]
        )

    def create(self, event_rule_name: str, cron_expression: str, description: str):
        """
        Creates an Amazon EventBridge Event Rule
        """
        logger.info(f"Creating/Updating rule with Name: {event_rule_name}. ScheduleExpression: cron({cron_expression}). Description: {description}")
        try:
            response = self.client.put_rule(
                Name=event_rule_name,
                ScheduleExpression=f'cron({cron_expression})',
                State='ENABLED',
                Description=description,
            )
            logger.info(f"Executing put rule with Name: {event_rule_name}. ScheduleExpression: cron({cron_expression})")
        except ClientError as e:
            logger.error(e, exc_info=True)
            return {'exception' : e}
        except Exception as ee:
            logger.error(ee, exc_info=True)
            return {'exception' : ee}
        arn = response['RuleArn']
        target_id = random.getrandbits(32)
        existing_targets = self.client.list_targets_by_rule(Rule=event_rule_name)['Targets']
        if len(existing_targets) == 0: self.add_target(event_rule_name, target_id)
        return {
            'target_id' : target_id,
            'event_rule_arn' : arn
        }

    def get_targets(self, event_rule_name: str):
        targets_ids = []
        try:
            response = self.client.list_targets_by_rule(
                Rule=event_rule_name,
                Limit=100
            )
            for target in response['Targets']:
                targets_ids.append(target['Id'])
        except ClientError as error:
            if 'does not exist' in error.response['Error']['Message']:
                pass
            else:
                logger.error('Failed deleting event rule {event_rule_name}', exc_info=True)
        return targets_ids

    def delete_rule(self, event_rule_name: str):
        targets = self.get_targets(event_rule_name)
        if not targets: return
        self.client.remove_targets(Rule=event_rule_name, Ids=targets)
        self.client.delete_rule(Name=event_rule_name)

    def _add_queue_policy(self, event_rule_payload, queue_arn=None, queue_url=None):
        """
        Adds an Amazon EventBridge Event Rule to a given SQS Queue's policy
        """
        for f in ['name', 'target_id', 'resource_arn']: assert f in event_rule_payload
        queue_arn = queue_arn or self.default_queue_arn
        queue_url = queue_url or self.default_queue_url
        sqs_client = boto3.client("sqs")
        queue_attributes_response = sqs_client.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=['Policy'])
        if queue_attributes_response.get('ResponseMetadata'):
            if not queue_attributes_response.get('ResponseMetadata').get('HTTPStatusCode') == 200:
                raise Exception(f"Failed to load queue {queue_url}")
        queue_policy = queue_attributes_response.get('Attributes').get('Policy')
        if not queue_policy: raise Exception(f"Failed to load queue ({queue_url}) policy") 
        try:
            queue_policy = json.loads(queue_policy)
            new_policy_dict = self.policy_base_dict.copy()
            new_policy_dict['Sid'] = f"AWSEvents_{event_rule_payload.get('name')}_{event_rule_payload.get('target_id')}"
            new_policy_dict['Resource'] = self.default_queue_arn
            new_policy_dict['Condition']['ArnEquals']['aws:SourceArn'] = event_rule_payload.get('resource_arn')
            queue_policy['Statement'].append(new_policy_dict)
            final_policy = json.dumps(queue_policy)
        except Exception as e:
            raise Exception(f"Failed merging policies: {e}")
        try:
            sqs_client.set_queue_attributes(
                QueueUrl = queue_url,
                Attributes = {'Policy': final_policy}
            )
        except Exception as e:
            raise Exception(f"Failed updating queue attributes: {e}")
        return True