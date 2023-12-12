import boto3
import logging
import time
from django.conf import settings
from main.decorators import ProductionCheck

logger = logging.getLogger(__name__)

class Aurora():
    acu_failed_err_msg  = "NightlyRun manager failed to increase Aurora Capacity: {}"

    @classmethod
    # @ProductionCheck
    def _get_response(cls, payload, f):
        client = boto3.client('rds')
        err_msg = None
        try:
            func = getattr(client, f)
            response = func(**payload)
        except Exception as e:
            response = None
            err_msg = cls.acu_failed_err_msg.format(e)
        
        if response:
            response_code = response['ResponseMetadata']['HTTPStatusCode']
            if response and response_code>299 or response_code<200:
                err_msg = cls.acu_failed_err_msg.format(response_code) + 'response code'

        if err_msg:
            logger.error(err_msg)
        return response

    @classmethod
    @ProductionCheck
    def get_aurora_capacity(cls):
        data = {
            'DBClusterIdentifier': settings.DB_CLUSTER_IDENTIFIER, 
        }
        r = cls._get_response(data, f='describe_db_clusters')
        return r['DBClusters'][0]['Capacity']

    @classmethod
    @ProductionCheck
    def increase_aurora_capacity(cls, n, sleep_time=60):
        import boto3
        data = {
            'DBClusterIdentifier': settings.DB_CLUSTER_IDENTIFIER, 
            'Capacity': n, 
            'TimeoutAction': 'RollbackCapacityChange'
        }
        cls._get_response(data, f='modify_current_db_cluster_capacity')
        time.sleep(sleep_time)
        #Give Aurora some time to fire up ACUs

    @classmethod
    @ProductionCheck
    def modify_aurora_cluster_min_capacity(cls, min_capacity=16, sleep_time=120):
        #if not settings.IS_PRODUCTION:
        #    return
        current_capacity = cls.get_aurora_capacity()
        logger.info(f"Current Aurora Capacity: {current_capacity}. New requested capacity: {min_capacity}")
        data = {
            'DBClusterIdentifier' : settings.DB_CLUSTER_IDENTIFIER,
            'ApplyImmediately' : True,
            'ScalingConfiguration' : {
                'MinCapacity' : min_capacity,
                'MaxCapacity': 128,
                'AutoPause': False,
                'TimeoutAction' : 'RollbackCapacityChange' 
            }
        }
        cls._get_response(data, f='modify_db_cluster')
        logger.info("Successfully requested new units")
        time.sleep(sleep_time)
        

class SQSManager():

    @classmethod
    @ProductionCheck
    def clean_production_queue(cls, queue=None, deadqueue=None):
        client = boto3.client('sqs')
        queue_name = queue or 'PRODUCTION_URL_STRING'
        dead_queue_name = deadqueue or 'PRODUCTION_DEADLETTER_URL'
        queue_url = settings.QUEUE_CREDENTIALS.get(queue_name)
        if queue_url: response = client.purge_queue(QueueUrl=queue_url)
        dead_queue_url = settings.QUEUE_CREDENTIALS.get(dead_queue_name)
        if dead_queue_url: response = client.purge_queue(QueueUrl=dead_queue_url)
        return True