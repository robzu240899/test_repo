import logging
import time
from datetime import  datetime, timedelta, date
from django.db import connection
from django.http import HttpResponse
from django.core.mail import send_mail
from main import settings
from queuehandler import job_creator 
from reporting.reliability.outoforder_report import OOOReportManager
from .queue import StepManager, QueueInspector, QueueConfig
from .utils import Aurora, SQSManager
from queuehandler.job_creator import NewMetricsCreator


logger = logging.getLogger(__name__)

class NightlyRunEnums(object):
    NIGHTLY_RUN_STEPS = {
        'user_ingest' : {
            "step_name" : 'Scrape Fascard Users', 
            "env_type" : settings.ENV_TYPE, 
            "enqueue_function" : job_creator.RevenueCreator.create_API_user_scrape_jobs,
            "wait_time" : 3, 
            "number_retries" : 25,
            "retry_pause" : 1, 
            "max_errors" : 0,
            "fail_tolerant" : True
        },
        'transaction_ingest' : {
            "step_name" : 'Scrape Fascard Transactions', 
            "env_type" : settings.ENV_TYPE,
            "enqueue_function" : job_creator.RevenueCreator.create_transaction_ingest_jobs, 
            "wait_time" : 3,
            "number_retries" : 20, 
            "retry_pause" : 1, 
            "max_errors" : 0,
            "fail_tolerant" : False
        },
        'equipment_finder' : {
            "step_name" : 'EquipmentTypes', 
            "env_type" : settings.ENV_TYPE, 
            "enqueue_function" : job_creator.RoomManagerCreator.create_equipment_finder_jobs, 
            "wait_time" : 1, 
            "number_retries" : 10, 
            "retry_pause" : 1, 
            "max_errors" : 0,
            "fail_tolerant" : True
        },
        'slot_finder' : {
            "step_name" : 'Scrape Fascard Slots', 
            "env_type" : settings.ENV_TYPE,
            "enqueue_function" : job_creator.RoomManagerCreator.create_slot_finder_jobs, 
            "wait_time" : 3, 
            "number_retries" : 25, 
            "retry_pause" : 2, 
            "max_errors" : 0,
            "fail_tolerant" : True
        },
        'deactivated_room_finder' : {
            "step_name" : 'Find deactivated rooms', 
            "env_type" : settings.ENV_TYPE,
            "enqueue_function" : job_creator.RoomManagerCreator.deactivated_room_finder, 
            "wait_time" : 1, 
            "number_retries" : 20, 
            "retry_pause" : 1, 
            "max_errors" : 0,
            "fail_tolerant" : True
        },
        'laundry_room_sync' : {
            "step_name" : 'Rooms Sync', 
            "env_type" : settings.ENV_TYPE, 
            "enqueue_function" : job_creator.RoomManagerCreator.laundry_room_sync, 
            "wait_time" : 1, 
            "number_retries" : 20, 
            "retry_pause" : 1, 
            "max_errors" : 0,
            "fail_tolerant" : True
        },
        'match' : {
            "step_name" : 'Match Transactions', 
            "env_type" : settings.ENV_TYPE, 
            "enqueue_function" : job_creator.RevenueCreator.match_transactions, 
            "wait_time" : 2, 
            "number_retries" : 10, 
            "retry_pause" : 1, 
            "max_errors" : 0,
            "fail_tolerant" : False
        },
        'calculate_metrics' : {
            "step_name" : 'Calculate Metrics', 
            "env_type" : settings.ENV_TYPE, 
            "enqueue_function" : job_creator.NewMetricsCreator.create_metrics, 
            "wait_time" : 5, 
            "number_retries" : 100, 
            "retry_pause" : 2, 
            "max_errors" : 0,
            "fail_tolerant" : True
        },
        'ingest_slot_states' : {
            "step_name" : 'Scrape Fascard Slot States', 
            "env_type" : settings.ENV_TYPE,  
            "enqueue_function" : job_creator.OutOfOrderCreator.create_slot_state_finder_jobs, 
            "wait_time" : 6, 
            "number_retries" : 80, 
            "retry_pause" : 2, 
            "max_errors" : 0,
            "fail_tolerant" : False
        },
        'prob_based_anomaly_detection': {
            "step_name" : 'Probability-based Anomaly Detection', 
            "env_type" : settings.ENV_TYPE, 
            "enqueue_function" : job_creator.ProbabilityBasedAnomalyDetectionEnqueuer.enqueue_report, 
            "wait_time" : 6, 
            "number_retries" : 30,
            "retry_pause" : 5, 
            "max_errors" : 0,
            "fail_tolerant" : True
        },
#            'send_time_sheet_report' : {
#            "step_name" : 'Send Time Sheet Report', 
#            "env_type" : settings.ENV_TYPE, 
#            "enqueue_function" : job_creator.TimeSheetsReportJobEnqueuer.enqueue_report, 
#            "wait_time" : 6, 
#            "number_retries" : 30,
#            "retry_pause" : 1, 
#            "max_errors" : 0,
#            "fail_tolerant" : True
#        },
        'send_ooo' : {
            "step_name" : 'Send Out Of Order Report', 
            "env_type" : settings.ENV_TYPE, 
            "enqueue_function" : job_creator.ReportCreator.create_ooo_report_job, 
            "wait_time" : 6, 
            "number_retries" : 30,
            "retry_pause" : 1, 
            "max_errors" : 0,
            "fail_tolerant" : True
        },
        # 'sync_upkeep_meters' : {
        #     "step_name" : "Syncing Machines' meters to Upkeep", 
        #     "env_type" : settings.ENV_TYPE,  
        #     "enqueue_function" : job_creator.CMMSProvidersSyncingEnqueuer.enqueue_meters_syncing, 
        #     "wait_time" : 4, 
        #     "number_retries" : 20,
        #     "retry_pause" : 1,
        #     "max_errors" : 0,
        #     "fail_tolerant" : True
        # },
        'sync_meters' : {
            "step_name" : "Syncing Assets' meters to Maintainx", 
            "env_type" : settings.ENV_TYPE,  
            "enqueue_function" : job_creator.CMMSProvidersSyncingEnqueuer.maintainx_centralized_meter_syncer, 
            "wait_time" : 4, 
            "number_retries" : 20,
            "retry_pause" : 1,
            "max_errors" : 0,
            "fail_tolerant" : True
        },
        'ingest_work_orders' : {
            "step_name" : "Fetch Work Orders",
            "env_type" : settings.ENV_TYPE, 
            "enqueue_function" : job_creator.CMMSProvidersSyncingEnqueuer.enqueue_upkeep_work_orders_fetch, 
            "wait_time" : 4, 
            "number_retries" : 10, 
            "retry_pause" : 2,
            "max_errors" : 0,
            "fail_tolerant" : True
        },
        'ingest_work_orders_maintainx' : {
            "step_name" : "Fetch Work Orders - Maintainx",
            "env_type" : settings.ENV_TYPE, 
            "enqueue_function" : job_creator.CMMSProvidersSyncingEnqueuer.enqueue_maintainx_work_orders_fetch, 
            "wait_time" : 4, 
            "number_retries" : 10, 
            "retry_pause" : 2,
            "max_errors" : 0,
            "fail_tolerant" : True
        },
        'auto_renew_leases' : {
            "step_name" : "Finding leases for auto renew", 
            "env_type" : settings.ENV_TYPE, 
            "enqueue_function" : job_creator.AutoRenewSyncer.enqueue_autorenew_syncer, 
            "wait_time" : 3, 
            "number_retries" : 10, 
            "retry_pause" : 2,
            "max_errors" : 0,
            "fail_tolerant" : True
        },
        'refund_authorize_settled' : {
            "step_name" : "Refund Queue Authorize Transactions", 
            "env_type" : settings.ENV_TYPE, 
            "enqueue_function" : job_creator.RefundsEnqueuer.enqueue_queued_authorize, 
            "wait_time" : 4, 
            "number_retries" : 10, 
            "retry_pause" : 2,
            "max_errors" : 0,
            "fail_tolerant" : True
        },
        'send_upkeep_report' : {
            "step_name" : 'Send Upkeep Report', 
            "env_type" : settings.ENV_TYPE,
            "enqueue_function" : job_creator.ReportCreator.create_upkeep_report_job,
            "wait_time" : 4, 
            "number_retries" : 10, 
            "retry_pause" : 1, 
            "max_errors" : 0,
            "fail_tolerant" : True
        },
        'clean_slot_states' : {
            "step_name" : 'Clean Slot States Table', 
            "env_type" : settings.ENV_TYPE,
            "enqueue_function" : job_creator.SlotStateCleaningEnqueuer.enqueue_cleanslotstates,
            "wait_time" : 4, 
            "number_retries" : 10, 
            "retry_pause" : 1, 
            "max_errors" : 0,
            "fail_tolerant" : True
        },
        'employee_scans_analysis' : {
            "step_name" : 'Employees Scans Analysis', 
            "env_type" : settings.ENV_TYPE,
            "enqueue_function" : job_creator.EmployeeScansAnalysisEnqueuer.enqueue_job,
            "wait_time" : 4, 
            "number_retries" : 10, 
            "retry_pause" : 1, 
            "max_errors" : 0,
            "fail_tolerant" : True
        },
        'volatility_anomaly_detection' : {
            "step_name" : 'Volatility-Based Anomaly Detection', 
            "env_type" : settings.ENV_TYPE,
            "enqueue_function" : job_creator.VolatilityAnomalyDetectionEnqueuer.enqueue_job,
            "wait_time" : 4,
            "number_retries" : 20,
            "retry_pause" : 2,
            "max_errors" : 0,
            "fail_tolerant" : True
        }
    }
    CHOICES = [(step, step) for step in NIGHTLY_RUN_STEPS.keys()]

class NightlyRun(object):
    """
    This is the processor for the nightly run job. It automatically creates new jobs to be
    processed by the main backend. All the jobs get enqeued by the StepManager.

    Before running jobs it modifies Aurora's minimun instance capacity and set it to 8
    then it tries to clean the production dead letter queue.
    """
    DEFAULT_PROD_QUEUE = QueueConfig.PRODUCTION_QUEUE_NAME
    
    @classmethod 
    def run(cls, steps_to_run=None, notify_email=None):
        nrm = StepManager.create_nightly_run_model()
        to_emails = settings.DEFAULT_TO_EMAILS.copy()
        logger.info(f"Default to_emails: {to_emails}")
        if notify_email:
            logger.info(f"Custom notify email: {notify_email}")
            to_emails.append(notify_email)
        if not nrm:
            send_mail(
                'Failed to start laundry nightly run.  Another process ran too soon.', 'started',
                settings.DEFAULT_FROM_EMAIL,
                to_emails,
                fail_silently=False
            )
            return HttpResponse("Another process started less than 5 minutes ago.  Aborting.")
        
        start_body_msg = '.\n'.join(steps_to_run.split(',')) if steps_to_run else 'started'
        send_mail(
            'started laundry nightly run',
            start_body_msg,
            settings.DEFAULT_FROM_EMAIL,
            to_emails,
            fail_silently=False
        )

        #NOTE: Increase Aurora's Min Capacity Units
        logger.info("AUTOSCALING DATABASE")
        Aurora().modify_aurora_cluster_min_capacity(64)
        logger.info("CALLED AURORA HELPER AND REQUESTED 64 INSTANCES")
        #Clean Production DeadLetter Qeueue
        try:
            SQSManager.clean_production_queue()
        except Exception as e:
            logger.error(f"Failed to clean production queue: {e}", exc_info=True)

        revenue_end = datetime.utcnow().date() + timedelta(days=1)  #NB this is interpreted as UTC time
        revenue_start = revenue_end - timedelta(days=5)
        metric_end = datetime.now().date()
        metric_start = metric_end - timedelta(days=settings.METRIC_TRAILING_DAYS)
        #Prevents nighly run from starting if there are messages in the queue.
        #For example, we could be doing a manual metrics recalculation and starting the nightly run would cause issues.
        inspector = QueueInspector()
        num_msgs_in_queue = inspector.get_number_messages_in_queue()
        if num_msgs_in_queue == 0:
            pass 
        else:
            Aurora().modify_aurora_cluster_min_capacity(1)
            send_mail('Nightly run did not start', 'Nightly run did not start because there are other messages in the queue.', 
                      settings.DEFAULT_FROM_EMAIL, to_emails, fail_silently=False)
            return HttpResponse("Finished with errors")            
        
        if not steps_to_run:
            #if None were specified, run all
            steps_to_run = NightlyRunEnums.NIGHTLY_RUN_STEPS.keys()
            steps_executed = ','.join(steps_to_run)
        else:
            steps_to_run = steps_to_run.split(',')
            steps_executed = steps_to_run
            logger.info(f"Executing specific steps: {steps_executed}")
        for step in steps_to_run:
            start = time.time()
            assert step in NightlyRunEnums.NIGHTLY_RUN_STEPS
            if step == 'clean_slot_states' and date.today().day != 1: continue
            logger.info("Processing Step: {}".format(step))
            with connection.cursor() as cursor:
                cursor.execute("SHOW STATUS WHERE variable_name = 'Threads_connected';")
                logger.info(f"Connected Threads: {cursor.fetchone()}")
            step_data = NightlyRunEnums.NIGHTLY_RUN_STEPS.get(step)
            #step_data['queue'] = QueueConfig.NIGHTLY_RUN_PROCESSING_QUEUE
            #step_data['deadqueue'] = QueueConfig.NIGHTLY_RUN_PROCESSING_QUEUE_DEAD
            StepManager(**step_data).run_step()
            end = time.time()
            logger.info(f"Finished Processing Step: {step} in {(end-start)/60.0} minutes")
        logger.info("Finished Processing all steps in nightly run")
        logger.info(f"Steps executed: {steps_executed}")
        end_body_msg = 'Steps executed: \n' + '.\n'.join(steps_executed.split(',')) if steps_to_run else 'done'
        send_mail(
            'finished laundry nightly run',
            end_body_msg,
            settings.DEFAULT_FROM_EMAIL,
            to_emails,
            fail_silently=False
        )
        #NOTE: Decrease Aurora's Min Capacity Units
        Aurora().modify_aurora_cluster_min_capacity(1)
        return HttpResponse("Finished")


# class TiedStepsNightlyRun():

#     @classmethod
#     def run(cls, *args, **kwargs):
#         if 'steps' in kwargs:
#             steps = kwargs.get('steps')
#             all_steps = ','.join(steps)
#             all_steps = [all_steps]
#         else:
#             all_steps = NightlyRunEnums.TIED_RUNS
#             all_steps = [','.join(tied) for tied in all_steps]
#         for tied_steps in all_steps:
#             job_creator.TiedRunEnqueuer.enqueue_tied_run(tied_steps)


class NightlyMetricsRun():
    """
    Job processor to exclusively compute metrics every night.
    """


    @classmethod 
    def run(cls):
        nrm = StepManager.create_nightly_run_model()
        if not nrm:
            send_mail('Failed to start laundry nightly metrics computation.  Another process ran too soon.', 'started', settings.DEFAULT_FROM_EMAIL,settings.DEFAULT_TO_EMAILS,fail_silently=False)
            return HttpResponse("Another process started less than 5 minutes ago.  Aborting.")
        
        send_mail('started nightly metrics computation', 'started', settings.DEFAULT_FROM_EMAIL,settings.DEFAULT_TO_EMAILS,fail_silently=False)

        revenue_end = datetime.utcnow().date() + timedelta(days=1)  #NB this is interpreted as UTC time
        revenue_start = revenue_end - timedelta(days=5)
        metric_end = datetime.now().date()
        metric_start = metric_end - timedelta(days=settings.METRIC_TRAILING_DAYS)
        
        
        #Prevents nighly run from starting if there are messages in the queue.
        #For example, we could be doing a manual metrics recalculation and starting the nightly run would cause issues.
        inspector = QueueInspector()
        num_msgs_in_queue = inspector.get_number_messages_in_queue()
        if num_msgs_in_queue == 0:
            pass 
        else:
            a = 'Nightly metrics computation did not start'
            b = 'Nightly run did not start because there are other messages in the queue.'
            send_mail(a, b, settings.DEFAULT_FROM_EMAIL, settings.IT_EMAIL_LIST,fail_silently=False)
            return HttpResponse("Finished with errors")            
        
        Aurora().increase_aurora_capacity(32, sleep_time=60)
        
        env_type = settings.ENV_TYPE
        StepManager.run_step(
            step_name = 'Calculate Metrics', 
            env_type = env_type, 
            #enqueue_function = MetricsCreator.create_metrics,
            enqueue_function = NewMetricsCreator.create_metrics, 
            wait_time = 5, 
            number_retries = 100, 
            retry_pause = 2, 
            max_errors = 0, 
            #**{'start_date':metric_start, 'end_date':metric_end}
        )
        send_mail('finished laundry nightly run', 'done', settings.DEFAULT_FROM_EMAIL, settings.IT_EMAIL_LIST,fail_silently=False)
        return HttpResponse("Finished")


class TiedRunManager():
    """
    Runs a list of steps in a blocking schema by enqueing them via SQS similar to the
    way nightly runs work.

    params:
        -steps: a string with comma separated step values
        -fault_tolerant: determines if the next step in the list should be run or not in case
        the previous step failed
    """
    DEFAULT_AURORA_CAPACITY = 1 #Run jobs on 2 rds units

    AURORA_CAPACITY_MAP = {
        'send_ooo' : 8,
        'transaction_ingest' : 1
    }

    @classmethod
    def _should_run(cls, steps):
        if 'send_ooo' in steps: return OOOReportManager.decide_to_run()
        else: return True


    @classmethod
    def check_aurora_resources(cls, expected_capacity, retries=0):
        if retries == 0:
            return
        current = Aurora.get_aurora_capacity()
        if not current:
           time.sleep(60)
           cls.check_aurora_resources(retries-1)
        else:
            if current < cls.DEFAULT_AURORA_CAPACITY:
                try:
                    Aurora.increase_aurora_capacity(expected_capacity)
                except:
                    pass

    @classmethod
    def calculate_expected_capacity(cls, steps):
        expected_capacity = cls.DEFAULT_AURORA_CAPACITY
        steps = steps.split(',')
        for step in steps:
            if cls.AURORA_CAPACITY_MAP.get(step): expected_capacity = cls.AURORA_CAPACITY_MAP.get(step)
        return expected_capacity

    @classmethod
    def run(cls, steps, increase_aurora_capacity=True, fail_tolerant=True):
        if increase_aurora_capacity:
            cls.check_aurora_resources(
                cls.calculate_expected_capacity(steps),
                retries=2
            )
        #Clean Production DeadLetter Qeueue
        # try:
        #     SQSManager.clean_production_queue()
        # except:
        #     pass
        logger.info('Tied Run with Steps: {}'.format(steps))
        steps = steps.split(',')
        if cls._should_run(steps):
            for step in steps:
                logger.info (f"Starting Step {step}")
                assert step in NightlyRunEnums.NIGHTLY_RUN_STEPS
                step_data = NightlyRunEnums.NIGHTLY_RUN_STEPS.get(step)
                step_data["fail_tolerant"] = fail_tolerant
                StepManager(**step_data).run_step()
                logger.info (f"Finishing Step {step}")
        if increase_aurora_capacity: Aurora.modify_aurora_cluster_min_capacity(min_capacity=1)
        return HttpResponse("Finished")