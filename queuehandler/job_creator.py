import boto3
import logging
import time
from datetime import date, timedelta, datetime
from dateutil import relativedelta
from django.db import transaction
from roommanager import models as roommanager_models
from reporting.models import BillingGroup
from reporting.enums import LocationLevel, DurationType
from reporting.models import MetricsCache, AnomalyDetectionJobTracker, AnomalyDetectionJobInfo
from reporting.metric.job import MetricsJobProcessor
from revenue.ingest import TransactionDatasetManager 
from revenue.models import LaundryTransaction, TransactionGaps, TransactionsPool
from revenue.matcher import CheckAttributionMatcher, MatchFilters, StandardMatcher as StandardRevenueMatcher
from roommanager.enums import HardwareType
from roommanager.models import LaundryRoomMeter, MachineMeter, CardReaderMeter, LaundryRoom
from .config import JobInstructions, QueueConfig
from .queue import Enqueuer


logger = logging.getLogger(__name__)


class EnqueuerUtil:

    @classmethod
    def initialize_enqueuer(cls, queue):
        if queue:
            return Enqueuer(queue_name=queue)
        else:
            return Enqueuer()



class DebugJobCreator():
    @classmethod
    def create_debug_job(cls):
        enqueuer = Enqueuer()
        enqueuer.add_message(JobInstructions.DEBUG_INSTRUCTION.job_name, {})
        enqueuer.close()

class RoomManagerCreator():

    @classmethod
    def create_slot_finder_jobs(cls, *args, queue=None, **kwargs):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        for laundry_room in roommanager_models.LaundryRoom.objects.filter(is_active=True):
            enqueuer.add_message(JobInstructions.SLOT_FINDER_INSTRUCTION.job_name,
                             {'laundryroomid':laundry_room.id})
        enqueuer.close()

    @classmethod
    def create_equipment_finder_jobs(cls, *args, queue=None, **kwargs):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        for laundry_room in roommanager_models.LaundryRoom.objects.filter(is_active=True):
            enqueuer.add_message(JobInstructions.EQUIPMENT_FINDER_INSTRUCITON.job_name,
                                 {'laundryroomid': laundry_room.id})
        enqueuer.close()

    @classmethod
    def deactivated_room_finder(cls, *args, queue=None, **kwargs):
        """
        Queries the API for every single active laundry room and detects wether all the machines
        in the room are disabled or there is none. If any case is true, the laundry room should be disabled.
        """
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        for laundry_room in roommanager_models.LaundryRoom.objects.all():
            enqueuer.add_message(JobInstructions.LAUNDRY_ROOM_STATUS_FINDER.job_name,
                                 {'laundryroomid': laundry_room.id})
        enqueuer.close()

    @classmethod
    def deactivated_billing_group_finder(cls, *args, queue=None, **kwargs):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        enqueuer.add_message(JobInstructions.BILLING_GROUP_STATUS_FINDER.job_name, {})
        enqueuer.close()

    @classmethod
    def laundry_room_sync(cls, *args, queue=None, **kwargs):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        for laundry_group in roommanager_models.LaundryGroup.objects.filter(is_active=True):
            enqueuer.add_message(
                JobInstructions.LAUNDRY_ROOM_SYNC_INSTRUCTION.job_name,
                {'laundrygroupid':laundry_group.id} #hardcoded id
            )
        enqueuer.close()
        

class OutOfOrderCreator():

    @classmethod
    def create_slot_state_finder_jobs(cls, *args, queue=None, **kwargs):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        for laundry_room in roommanager_models.LaundryRoom.objects.filter(is_active=True):
            enqueuer.add_message(JobInstructions.SLOT_STATE_FINDER_INSTRUCTION.job_name,
                             {'laundryroomid':laundry_room.id}
                             )
        enqueuer.close()

class RevenueCreator():

    @classmethod
    def create_user_scrape_jobs(cls, *args, **kwargs):
        enqueuer = Enqueuer()
        for laundry_group in roommanager_models.LaundryGroup.objects.filter(is_active=True):
            enqueuer.add_message(JobInstructions.FASCARD_USER_SCRAPE_INSTRUCTION.job_name,
                             {'laundrygroupid':laundry_group.id})
        enqueuer.close()

    @classmethod
    def create_API_user_scrape_jobs(cls, *args, queue: str=None, **kwargs):
        """
        queue: the name of the queue to send the message to
        """
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        for laundry_group in roommanager_models.LaundryGroup.objects.filter(is_active=True):
            enqueuer.add_message(JobInstructions.FASCARD_API_USER_SCRAPE_INSTRUCTION.job_name,
                             {'laundrygroupid':laundry_group.id})
        enqueuer.close()

    @classmethod
    def create_revenue_scrape_jobs(cls,start_date,end_date):
        enqueuer = Enqueuer()
        for laundry_group in roommanager_models.LaundryGroup.objects.filter(is_active=True):
            for offset in range( (end_date-start_date).days):
                dt = start_date + timedelta(days=offset)
                enqueuer.add_message(JobInstructions.REVENUE_SCRAPE_INSTRUCTION.job_name,
                     {'laundrygroupid':laundry_group.id,
                     'startdate':dt,
                     'finaldate':dt}
                 )
        enqueuer.close()

    @classmethod
    def create_transaction_update_job(cls, start, end, slot, machine):
        enqueuer = Enqueuer()
        enqueuer.add_message(
            JobInstructions.UPDATE_TRANSACTIONS.job_name,
            {
                'startdate' : start,
                'enddate' : end,
                'slot' : slot,
                'machine' : machine
            }
        )

    @classmethod
    def create_transaction_ingest_jobs(cls, *args, queue=None, **kwargs):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        for laundry_group in roommanager_models.LaundryGroup.objects.filter(is_active=True):
            enqueuer.add_message(
                JobInstructions.API_TRANSACTION_INGEST.job_name,
                {
                    'laundrygroupid':laundry_group.id,
                }
            )
        enqueuer.close()

    @classmethod
    def create_pricing_history(cls, *args, **kwargs):
        enqueuer = Enqueuer()
        for laundry_room in roommanager_models.LaundryRoom.objects.all():
                enqueuer.add_message(JobInstructions.PRICING_HISTORY_SCRAPE_INSTRUCTION.job_name,
                     {'laundryroomid':laundry_room.id}
                 )
        enqueuer.close()

    @classmethod
    def match_transactions(cls, *args, queue=None,**kwargs):
        StandardRevenueMatcher.match_all()
        CheckAttributionMatcher.match()
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        for tx in MatchFilters.add_web_based_filter(LaundryTransaction.objects.all()).filter(assigned_laundry_room=None):
                enqueuer.add_message(JobInstructions.REVENUE_MATCH_INSTRUCTION.job_name,
                     {'laundrytransactionid':tx.id}
                 )
        enqueuer.close()


class MetricsCreator():
    LOCATIONS_MAP = {
        LocationLevel.LAUNDRY_ROOM : roommanager_models.LaundryRoom,
        LocationLevel.MACHINE : roommanager_models.Machine,
        LocationLevel.BILLING_GROUP : BillingGroup
    }
    DURATION_TIMEDELTA_MAP = {
        DurationType.MONTH : 'months'
    } 

    @classmethod
    def _compute_dates(cls, start_date, end_date, duration_type):
        if duration_type == DurationType.MONTH:
            new_start_date = date(start_date.year, start_date.month, 1)
            delta_param = 'months'
        elif duration_type == DurationType.YEAR:
            new_start_date = date(start_date.year, 1, 1)
            delta_param = 'years'
        else:
            new_start_date = start_date
            delta_param = 'days'
        scheduled_dates = []
        while True:
            if new_start_date > end_date: break
            scheduled_dates.append(
                (new_start_date, new_start_date + relativedelta.relativedelta(days=1))
            )
            new_start_date = new_start_date + relativedelta.relativedelta(**{delta_param:1})
        return scheduled_dates

    @classmethod
    def metrics_recalc(cls, queue=None, location_level=None, duration_type='daily-basis', **kwargs):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        if location_level:
            assert location_level in cls.LOCATIONS_MAP
            location_levels = [location_level]
        else:
            location_levels = cls.LOCATIONS_MAP.keys()
        start_date = kwargs.get('start_date')
        end_date = kwargs.get('end_date')

        if duration_type == 'daily-basis':
            scheduled_dates = []
            for offset in range((end_date-start_date).days):
                t1 = start_date + timedelta(days=offset)
                t2 = t1 + timedelta(days=1)
                scheduled_dates.append(t1, t2)
        else:
            scheduled_dates = cls._compute_dates(start_date, end_date, duration_type)

        for t1, t2 in scheduled_dates:
            for location_level in location_levels:
                location_model_class = cls.LOCATIONS_MAP.get(location_level)
                for obj in location_model_class.objects.all():
                    logger.info(f"""
                    Enqueuing message with parameters locationlevel: 
                    location_level: {location_level}
                    locationid: {obj.id}
                    startdate: {t1}
                    enddate: {t2} 
                    durationtype: {duration_type}
                    """
                    )
                    enqueuer.add_message(JobInstructions.METRICS_CREATION.job_name,
                        {
                            'locationlevel':location_level,
                            'locationid':obj.id,
                            'startdate':t1,
                            'enddate':t2,
                            'durationtype':duration_type
                        }
                    )

    @classmethod
    def create_metrics(cls,start_date,end_date,queue=None, duration_type='daily-basis', location_level_maps=[]):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        if not location_level_maps:
            location_level_maps = [
                (LocationLevel.LAUNDRY_ROOM, [laundry_room.id for laundry_room in roommanager_models.LaundryRoom.objects.all()]),
                (LocationLevel.BILLING_GROUP, [billing_group.id for billing_group in BillingGroup.objects.all()]),
                (LocationLevel.MACHINE, [machine.id for machine in roommanager_models.Machine.objects.all()]),
            ]
        for offset in range((end_date-start_date).days):
            t1 = start_date + timedelta(days=offset)
            t2 = t1 + timedelta(days=1)
            for location_level, location_ids in location_level_maps:
                for location_id in location_ids:
                    enqueuer.add_message(JobInstructions.METRICS_CREATION.job_name,
                        {'locationlevel':location_level,'locationid':location_id,
                        'startdate':t1,'enddate':t2, 'durationtype':duration_type})
        enqueuer.close()

class NewMetricsCreator():
    model = TransactionsPool

    @classmethod
    def enqueue_extra_metrics(cls, enqueuer):
        q = MetricsJobProcessor.get_extrametrics_queryset()
        for metric in q:
            t1 = metric.start_date
            t2 = t1 + timedelta(days=1)
            enqueuer.add_message(
                JobInstructions.METRICS_CREATION.job_name,
                {
                    'locationlevel':metric.location_level,
                    'locationid':metric.location_id,
                    'startdate':t1,
                    'enddate':t2,
                    'durationtype':metric.duration
                }
            )

    #TOOO: Manual test
    #Compute all metrics for march but the monthly
    #then manually create a transaction dated at April 5
    #Run it thru the function in order to see whether 
    #it triggers a recompute or not.

    @classmethod
    def _enqueue_metrics_calculation(cls, enqueuer, locations_map, start_date, end_date, duration_type):
        for location in locations_map:
            for loc_id in location[1]:
                enqueuer.add_message(
                    JobInstructions.METRICS_CREATION.job_name,
                    {
                        'locationlevel': location[0],
                        'locationid': loc_id,
                        'startdate': start_date,
                        'enddate': end_date,
                        'durationtype': duration_type
                    }
                )

    @classmethod
    def create_metrics(cls, reprocess=False, queue=None):
        logger.info(f"Inside NewMetrics Create metrics function. Datetime: {datetime.now()}")
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        logger.info("Calling MetricsJobProcessor.schedule_extra_metrics")
        MetricsJobProcessor.schedule_extra_metrics()
        logger.info("Called MetricsJobProcessor.schedule_extra_metrics")
        cls.enqueue_extra_metrics(enqueuer)
        logger.info("Enqueued extra metrics")
        q = cls.model.objects.filter(fully_processed=False)
        for tracker_model in q:
            dataset_manager = TransactionDatasetManager(tracker_model, reprocess)
            data_dict = dataset_manager.get_data()
            
            today = date.today()
            for tx_date, data in data_dict.items():
                if (today==tx_date):
                    continue
                t1 = tx_date
                t2 = t1 + timedelta(days=1)
                locations_to_compute = [
                    (LocationLevel.LAUNDRY_ROOM, data['rooms']),
                    (LocationLevel.BILLING_GROUP, data['billing_groups']),
                    (LocationLevel.MACHINE, data['machines']),
                ]
                metric_maps = [
                    ('daily-basis', t1, t2)
                ]
                if (today.month > tx_date.month or today.year > tx_date.year):
                    start_of_month = date(tx_date.year, tx_date.month, 1)
                    metric_maps.append(
                        (DurationType.MONTH, start_of_month, start_of_month + timedelta(days=1))
                    )
                    #NOTE:
                    #here we compute monthly metrics only for the locations stored in the variables
                    #locations_to_compute. these may be the reason why we get plenty of rooms with no metrics at all.
                with transaction.atomic():
                    for metric_map in metric_maps:
                        cls._enqueue_metrics_calculation(
                            enqueuer,
                            locations_to_compute,
                            metric_map[1], #start_date
                            metric_map[2], #end_date
                            metric_map[0] #duration_type
                        )
                    dataset_manager.mark_as_processed(tx_date)
            dataset_manager.persist_changes()
            logger.info("Finished processing transactions pool with tracker model(ID): {}".format(tracker_model.id))
        enqueuer.close()
        logger.info("Finished enqueuing transactions-based metrics")

        #Extra Step: Enqueue missing monthly and annual metrics
        return True


class PricingChangesJobCreator():

    @classmethod
    def create_report(cls, report_job_info):
        enqueuer = Enqueuer()
        enqueuer.add_message(
            JobInstructions.PRICING_REPORT_CREATION.job_name,
            {'reportjobinfo':report_job_info.id}
        )
        enqueuer.close()

class PricingJobsTrackerJobCreator():

    @classmethod
    def enqueue_job_tracker(cls, jobs_tracker):
        enqueuer = Enqueuer()
        enqueuer.add_message(
            JobInstructions.PRICING_REPORT_JOBS_TRACKER.job_name,
            {'jobstracker':jobs_tracker.id}
        )
        enqueuer.close()

class PricingDataFetchTaskCreator():

    @classmethod
    def enqueue_data_fetch(cls, laundry_group_id):
        enqueuer = Enqueuer()
        enqueuer.add_message(
            JobInstructions.PRICING_DATA_FETCH.job_name,
            {'laundrygroupid': laundry_group_id}
        )
        enqueuer.close()


class ReportCreator():

    @classmethod
    def create_ooo_report_job(cls, *args, queue=None, **kwargs):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        enqueuer.add_message(JobInstructions.OUT_OF_ORDER_SEND.job_name,
                     {} )
        enqueuer.close()

    @classmethod
    def create_upkeep_report_job(cls, *args, queue=None, **kwargs):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        enqueuer.add_message(JobInstructions.UPKEEP_REPORT_SEND.job_name,
                     {})
        enqueuer.close()


class ClientRevenueReportEnqueuer():
    @classmethod
    def enqueue_report(cls, report_job_info):
        enqueuer = Enqueuer()
        enqueuer.add_message(
            JobInstructions.CLIENT_REVENUE_REPORT.job_name,
            {'reportjobinfo':report_job_info}
        )
        enqueuer.close()


class ClientRevenueJobsTrackerEnqueuer():

    @classmethod
    def enqueue_job_tracker(cls, jobs_tracker_id):
        enqueuer = Enqueuer()
        enqueuer.add_message(
            JobInstructions.CLIENT_REVENUE_JOBS_TRACKER.job_name,
            {'reportjobstracker':jobs_tracker_id}
        )
        enqueuer.close()


class ClientRevenueFullReportEnqueuer():

    @classmethod
    def enqueue_report(cls, report_job_info):
        enqueuer = Enqueuer()
        #enqueuer = EnqueuerUtil.initialize_enqueuer(QueueConfig.NIGHTLY_RUN_PROCESSING_QUEUE)
        enqueuer.add_message(
            JobInstructions.CLIENT_REVENUE_FULL_REPORT.job_name,
            {'fullreportjobinfo':report_job_info}
        )
        enqueuer.close()

class ClientRevenueFullJobsTrackerEnqueuer():

    @classmethod
    def enqueue_job_tracker(cls, jobs_tracker_id):
        enqueuer = Enqueuer()
        #enqueuer = EnqueuerUtil.initialize_enqueuer(QueueConfig.NIGHTLY_RUN_PROCESSING_QUEUE)
        enqueuer.add_message(
            JobInstructions.CLIENT_REVENUE_FULL_JOBS_TRACKER.job_name,
            {'fullreportjobstracker':jobs_tracker_id}
        )
        enqueuer.close()


class TimeSheetsReportJobEnqueuer():
    
    @classmethod
    def enqueue_report(cls, report_job_info):
        enqueuer = Enqueuer()
        # enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        enqueuer.add_message(
            JobInstructions.TIMESHEETS_REPORT.job_name,
            {'timesheetsjobinfo':report_job_info}
        )
        enqueuer.close()


class TimeSheetsReportTrackerEnqueuer():

    @classmethod
    def enqueue_job_tracker(cls, jobs_tracker_id):
        enqueuer = Enqueuer()
        #enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        enqueuer.add_message(
            JobInstructions.TIMESHEETS_REPORT_TRACKER.job_name,
            {'timesheetsreportjobstracker':jobs_tracker_id}
        )
        enqueuer.close()


class SlotMachinePairingEnqueuer():

    @classmethod
    def enqueue_pairing_process(cls, job_payload):
        enqueuer = Enqueuer()
        enqueuer.add_message(
            JobInstructions.SLOTMACHINE_PAIRING_JOB.job_name,
            job_payload
        )
        enqueuer.close()

class TransactionGapsJobEnqueuer():

   @classmethod
   def enqueue(cls, *args, **kwargs):
       enqueuer = Enqueuer()
       unprocessed_tx_gaps = TransactionGaps.objects.filter(processed=False)
       for gap_tracker in unprocessed_tx_gaps:
           enqueuer.add_message(
            JobInstructions.TRANSACTIONS_GAPS_TRACKER.job_name,
            {'gaptrackerid':gap_tracker.id}
        )

#Meter syncing
class CMMSProvidersSyncingEnqueuer():

    @classmethod
    def enqueue_meters_syncing(cls, *args,queue=None, **kwargs):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        #machines and card readers
        q = {'maintainx_id__isnull' : False, 'transactions_counter__gt' : 0}
        asset_meters_instructions = [
            JobInstructions.SYNC_UPKEEP_ASSET_METERS.job_name,
            JobInstructions.SYNC_MAINTAINX_ASSET_METERS.job_name
        ]
        for meter in roommanager_models.MachineMeter.objects.filter(**q):
            for job_instruction in asset_meters_instructions:
                enqueuer.add_message(
                    job_instruction,
                    {
                        'assetmeterid':meter.id,
                        'assettype' : HardwareType.MACHINE,
                    })

        for meter in CardReaderMeter.objects.filter(**q):
            for job_instruction in asset_meters_instructions:
                enqueuer.add_message(
                    job_instruction,
                    {
                        'assetmeterid':meter.id,
                        'assettype' : HardwareType.CARD_READER,
                    })
        #rooms
        room_meters_instructions = [
            JobInstructions.SYNC_UPKEEP_ROOM_METERS.job_name,
            JobInstructions.SYNC_MAINTAINX_ROOM_METERS.job_name
        ]
        qq = {'maintainx_id__isnull' : False, 'dryers_start_counter__gt' : 0}
        for meter in roommanager_models.LaundryRoomMeter.objects.filter(**qq):
            for job_instruction in room_meters_instructions:
                enqueuer.add_message(job_instruction, {'roommeterid':meter.id})
        enqueuer.close()

    @classmethod
    def enqueue_upkeep_work_orders_fetch(cls, *args, queue=None, **kwargs):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        enqueuer.add_message(JobInstructions.WORK_ORDERS_FETCHER.job_name, {})
        enqueuer.close()

    @classmethod
    def enqueue_maintainx_work_orders_fetch(cls, *args, queue=None, **kwargs):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        enqueuer.add_message(JobInstructions.MAINTAINX_WORK_ORDERS_FETCHER.job_name, {})
        enqueuer.close()

    @classmethod
    def maintainx_centralized_meter_syncer(cls, *args, queue=None, **kwargs):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        enqueuer.add_message(JobInstructions.SYNC_MAINTAINX_METER_SINGLE_JOB.job_name, {})
        enqueuer.close()

    @classmethod
    def maintainx_centralized_assets_syncer(cls, *args, queue=QueueConfig.MAINTAINX_METER_UPDATE_QUEUE, **kwargs):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        enqueuer.add_message(JobInstructions.SYNC_MAINTAINX_ASSETS_CENTRALIZED.job_name, {})
        enqueuer.close()

#Asset syncing
class UpkeepAssetSyncEnqueuer():

    @classmethod
    def enqueue_asset_syncing(cls, asset_id, asset_type):
        enqueuer = Enqueuer()
        enqueuer.add_message(
            JobInstructions.SYNC_UPKEEP_ASSET.job_name, 
            {
                'assetid':asset_id,
                'assettype' : asset_type
            })
        enqueuer.close()


class AutoRenewSyncer():

    @classmethod
    def enqueue_autorenew_syncer(cls, *args, queue=None, **kwargs):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        enqueuer.add_message(JobInstructions.AUTORENEW_LEASE_SYNCER.job_name, {})
        enqueuer.close()


class TimeUsageReportEnqueuer():

    @classmethod
    def enqueue_report(cls, send_to, days, months):
        enqueuer = Enqueuer()
        enqueuer.add_message(
            JobInstructions.TIME_USAGE_REPORT.job_name, 
            {
                'sendto':send_to,
                'days':days,
                'months':months
            }
        )
        enqueuer.close()


class RefundsEnqueuer():

    @classmethod
    def enqueue_queued_authorize(cls, *args, queue=None, **kwargs):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        enqueuer.add_message(JobInstructions.REFUND_QUEUED_AUTHORIZE.job_name, {})
        enqueuer.close()

    @classmethod
    def enqueue_refund_request(cls, request_id, queue=None):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        enqueuer.add_message(JobInstructions.PROCESS_REFUND_REQUEST.job_name, {
            'requestid' : request_id
        })
        enqueuer.close()


class SlotStateCleaningEnqueuer():

    @classmethod
    def enqueue_cleanslotstates(cls, *args, queue=None, **kwargs):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        enqueuer.add_message(JobInstructions.CLEAN_SLOTSTATE_TABLE.job_name, {})
        enqueuer.close()


class UploadAssetAttachmentsEnqueuer():

    @classmethod
    def enqueue_job(cls, asset_id, queue=None):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        enqueuer.add_message(JobInstructions.UPLOAD_ASSET_ATTACHMENTS.job_name, {
            'assetid' : asset_id
        })
        enqueuer.close()


class EmployeeScansAnalysisEnqueuer():

    @classmethod
    def enqueue_job(self, queue=None):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        enqueuer.add_message(JobInstructions.EMPLOYEE_SCANS_ANALYSIS.job_name, {})
        enqueuer.close()

class MaintainxMeterUpdateEnqueuer():

    @classmethod
    def enqueue_job(self, queue=QueueConfig.MAINTAINX_METER_UPDATE_QUEUE):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        enqueuer.add_message(JobInstructions.SYNC_MAINTAINX_METER_SINGLE_JOB.job_name, {})
        enqueuer.close()


class VolatilityAnomalyDetectionEnqueuer():

    @classmethod
    def enqueue_job(self, queue=None):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        enqueuer.add_message(JobInstructions.VOLATILITY_BASED_ANOMALY_DETECTION.job_name, {})
        enqueuer.close()



class ProbabilityBasedAnomalyDetectionEnqueuer():

    @classmethod
    def enqueue_job_tracker(self, job_tracker_id, queue=None):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        enqueuer.add_message(
            JobInstructions.PROB_BASED_ANOMALY_TRACKER.job_name,
            {'probbasedanomalyjobtracker':job_tracker_id}
        )
        enqueuer.close()

    @classmethod
    def enqueue_job_info(cls, report_job_info_id, queue=None):
        enqueuer = EnqueuerUtil.initialize_enqueuer(queue)
        enqueuer.add_message(
            JobInstructions.PROB_BASED_ANOMALY.job_name,
            {'probbasedanomalyjobinfo':report_job_info_id}
        )
        enqueuer.close()

    @classmethod
    def enqueue_report(cls, queue = None):
        jobs_tracker = AnomalyDetectionJobTracker.objects.create(user_requested_email='reports_anomaly_detections@aceslaundry.com')
        jobs_buffer = []
        rooms = LaundryRoom.objects.filter(is_active=True, test_location=False)
        for room in rooms:
            slots = room.slot_set.filter(is_active=True)
            for slot in slots:
                machine = slot.get_current_machine(slot)
                job_info = AnomalyDetectionJobInfo.objects.create(
                    machine = machine,
                    job_tracker = jobs_tracker
                )
                jobs_buffer.append(job_info.id)                
        #enqueue jobs_tracker first
        cls.enqueue_job_tracker(jobs_tracker.id)
        for job_info_id in jobs_buffer: cls.enqueue_job_info(job_info_id)
        #loop over buffer and enqueue job infos.


# class TiedRunEnqueuer():

#     @classmethod
#     def enqueue_tied_run(cls, steps, *args, **kwargs):
#         enqueuer = Enqueuer()
#         enqueuer.add_message(JobInstructions.TIED_RUN.job_name, {'steps':steps})
#         enqueuer.close()


#Not used anymore. Done via Nightly Run as a step

# class DeactivatedRoomFinderEnqueuer():

#     @classmethod
#     def enqueue_finder(cls):
#         enqueuer = Enqueuer()
#         for laundry_room in LaundryRoom.objects.all():
#             enqueuer.add_message(
#                 JobInstructions.DEACTIVATED_ROOM_FINDER.job_name,
#                 {'laundryroomid':laundry_room.id}
#             )
#         enqueuer.close()