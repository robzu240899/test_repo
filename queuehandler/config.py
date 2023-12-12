from main import settings
from fascard.pricing import PriceScraperManager
from reporting.finance.clientreport.job import *
from reporting.job import ReporterJobs, AutoRenewLeases, BillingGroupStatusFinder, AnomalyDetectionJobProcessor, AnomalyDetectionJobTrackerProcessor
from reporting.metric.job import MetricsJobProcessor, PricingReportJobProcessor, PricingDataFetchJobProcessor, PricingJobsTrackerJobProcessor
from reporting.finance.internal.usage_report import TimeUsageReport
from reporting.reliability.anomaly_detection import VolatilityAnomalyDetector
from revenue.ingest import FascardTransactionIngestor, FascardUserIngestor, FascardUserAccountSync, FascardTransactionSync
from revenue.matcher import WebBasedMatcherAdaptor
from revenue.job import CompleteAuthorizeRefunds, CompleteEnqueuedCreditCardRefund
from roommanager.job import LaundryRoomStatusFinderJob, LaundryRoomSync, EmployeeScanAnalysis
from roommanager.slot_finder import ConfigurationRecorder
from roommanager.helpers import MachineSlotMapUpdateManager, UploadAssetAttachments
from outoforder.job import SlotStateJobManager, CleanSlotStateTable
from maintainx.managers.managers import MaintainxAssetManager, MaintainxWorkOrderManager
from maintainx.jobs import MaintainxWorkOrderFetcher, MaintainxSync
from upkeep.manager import BaseUpkeepAssetManager, UpkeepAssetSyncJob
from upkeep.jobs import WorkOrderFetcher
from .queue_instructions import QueueJobInstruction
#from .job import TiedRunManager
from .enums import ParameterType

class JobInstructions(object):

    DEBUG_INSTRUCTION = QueueJobInstruction('debugjob', None)

    SLOT_FINDER_INSTRUCTION = QueueJobInstruction('slotfinder', ConfigurationRecorder.record_slot_configuration)
    SLOT_FINDER_INSTRUCTION.add_parameter_instruction('laundryroomid',  ParameterType.INTEGER,  'limit_to_rooms') #NB: limit_to_rooms can either be int or list of ints

    EQUIPMENT_FINDER_INSTRUCITON = QueueJobInstruction('equipment', ConfigurationRecorder.record_equipment)
    EQUIPMENT_FINDER_INSTRUCITON.add_parameter_instruction('laundryroomid',  ParameterType.INTEGER,  'laundry_room_id') #NB: limit_to_rooms can either be int or list of ints

    LAUNDRY_ROOM_STATUS_FINDER = QueueJobInstruction('deactivatedroomdetector', LaundryRoomStatusFinderJob.run_analysis)
    LAUNDRY_ROOM_STATUS_FINDER.add_parameter_instruction('laundryroomid', ParameterType.INTEGER,  'laundry_room_id')

    BILLING_GROUP_STATUS_FINDER = QueueJobInstruction(
        'deactivatedbillinggroupdetector', 
        BillingGroupStatusFinder.run_analysis)

    SLOT_STATE_FINDER_INSTRUCTION = QueueJobInstruction('slotstatefinder', SlotStateJobManager.run)
    SLOT_STATE_FINDER_INSTRUCTION.add_parameter_instruction('laundryroomid',  ParameterType.INTEGER,  'laundry_room_id')

    OUT_OF_ORDER_SEND = QueueJobInstruction('outoforderreportsend', ReporterJobs.out_of_order)
    UPKEEP_REPORT_SEND = QueueJobInstruction('upkeepreportsend', ReporterJobs.upkeep_report)

    REVENUE_SCRAPE_INSTRUCTION = QueueJobInstruction('revenuescrape', FascardTransactionIngestor.ingest)
    REVENUE_SCRAPE_INSTRUCTION.add_parameter_instruction('laundrygroupid',  ParameterType.INTEGER, 'laundry_group_id')
    REVENUE_SCRAPE_INSTRUCTION.add_parameter_instruction('startdate',  ParameterType.DATE, 'start_date')
    REVENUE_SCRAPE_INSTRUCTION.add_parameter_instruction('finaldate',  ParameterType.DATE, 'final_date')


    UPDATE_TRANSACTIONS = QueueJobInstruction('updatetransactions', MachineSlotMapUpdateManager.update_transactions)
    UPDATE_TRANSACTIONS.add_parameter_instruction('startdate',  ParameterType.DATE, 'start')
    UPDATE_TRANSACTIONS.add_parameter_instruction('enddate',  ParameterType.DATE, 'end')
    UPDATE_TRANSACTIONS.add_parameter_instruction('slot',  ParameterType.DATE, 'slot_id')
    UPDATE_TRANSACTIONS.add_parameter_instruction('machine',  ParameterType.DATE, 'machine_id')


    FASCARD_USER_SCRAPE_INSTRUCTION = QueueJobInstruction('fascarduserscrape', FascardUserIngestor.ingest)
    FASCARD_USER_SCRAPE_INSTRUCTION.add_parameter_instruction('laundrygroupid',  ParameterType.INTEGER, 'laundry_group_id')

    FASCARD_API_USER_SCRAPE_INSTRUCTION = QueueJobInstruction('fascardAPIuserscrape', FascardUserAccountSync.run_as_job)
    FASCARD_API_USER_SCRAPE_INSTRUCTION.add_parameter_instruction('laundrygroupid',  ParameterType.INTEGER, 'laundry_group_id')

    API_TRANSACTION_INGEST = QueueJobInstruction('fascardAPItransactioningest', FascardTransactionSync.run_as_job)
    API_TRANSACTION_INGEST.add_parameter_instruction('laundrygroupid',  ParameterType.INTEGER, 'laundry_group_id')

    LAUNDRY_ROOM_SYNC_INSTRUCTION = QueueJobInstruction('laundryroomsync', LaundryRoomSync.run)
    LAUNDRY_ROOM_SYNC_INSTRUCTION.add_parameter_instruction('laundrygroupid',  ParameterType.INTEGER, 'laundry_group_id')

    REVENUE_MATCH_INSTRUCTION =  QueueJobInstruction('revenuematch', WebBasedMatcherAdaptor.process)
    REVENUE_MATCH_INSTRUCTION.add_parameter_instruction('laundrytransactionid', ParameterType.INTEGER, 'laundry_transaction_id')

    PRICING_HISTORY_SCRAPE_INSTRUCTION = QueueJobInstruction('pricinghistoryscrape', PriceScraperManager.scrape)
    PRICING_HISTORY_SCRAPE_INSTRUCTION.add_parameter_instruction('laundryroomid',  ParameterType.INTEGER, 'laundry_room_id')

    PRICING_REPORT_CREATION = QueueJobInstruction('pricinghistoryreport', PricingReportJobProcessor.generate_report)
    PRICING_REPORT_CREATION.add_parameter_instruction('reportjobinfo', ParameterType.INTEGER, 'report_info_id')

    PRICING_REPORT_JOBS_TRACKER = QueueJobInstruction('pricingreportjobstracker', PricingJobsTrackerJobProcessor.process_all_jobs)
    PRICING_REPORT_JOBS_TRACKER.add_parameter_instruction('jobstracker', ParameterType.INTEGER, 'jobs_tracker_id')

    PRICING_DATA_FETCH = QueueJobInstruction('pricingdatafetch', PricingDataFetchJobProcessor.fetch_data)
    PRICING_DATA_FETCH.add_parameter_instruction('laundrygroupid', ParameterType.INTEGER, 'laundry_group_id')

    CLIENT_REVENUE_REPORT = QueueJobInstruction('clientrevenuereport', ClientRevenueReportJobProcessor.run_as_job)
    CLIENT_REVENUE_REPORT.add_parameter_instruction('reportjobinfo', ParameterType.INTEGER, 'report_job_info')

    CLIENT_REVENUE_JOBS_TRACKER = QueueJobInstruction('clientrevenuejobstracker', ClientRevenueJobsTrackerProcessor.run_as_job)
    CLIENT_REVENUE_JOBS_TRACKER.add_parameter_instruction('reportjobstracker', ParameterType.INTEGER, 'report_jobs_tracker')

    CLIENT_REVENUE_FULL_REPORT =  QueueJobInstruction('clientrevenuefullreport', ClientRevenueFullReportJobProcessor.run_as_job)
    CLIENT_REVENUE_FULL_REPORT.add_parameter_instruction('fullreportjobinfo', ParameterType.INTEGER, 'report_job_info')

    CLIENT_REVENUE_FULL_JOBS_TRACKER =  QueueJobInstruction('clientrevenuefulljobtracker', ClientRevenueFullJobsTrackerProcessor.run_as_job)
    CLIENT_REVENUE_FULL_JOBS_TRACKER.add_parameter_instruction('fullreportjobstracker', ParameterType.INTEGER, 'report_jobs_tracker')

    TIMESHEETS_REPORT =  QueueJobInstruction('timesheetsreport', TimeSheetsReportJobProcessor.run_as_job)
    TIMESHEETS_REPORT.add_parameter_instruction('timesheetsjobinfo', ParameterType.INTEGER, 'report_job_info')

    TIMESHEETS_REPORT_TRACKER =  QueueJobInstruction('timesheetsjobtracker', TimeSheetsJobsTrackerProcessor.run_as_job)
    TIMESHEETS_REPORT_TRACKER.add_parameter_instruction('timesheetsreportjobstracker', ParameterType.INTEGER, 'report_jobs_tracker')

    PROB_BASED_ANOMALY =  QueueJobInstruction('probbasedanomaly', AnomalyDetectionJobProcessor.run_as_job)
    PROB_BASED_ANOMALY.add_parameter_instruction('probbasedanomalyjobinfo', ParameterType.INTEGER, 'report_job_info')

    PROB_BASED_ANOMALY_TRACKER =  QueueJobInstruction('probbasedanomalytracker', AnomalyDetectionJobTrackerProcessor.run_as_job)
    PROB_BASED_ANOMALY_TRACKER.add_parameter_instruction('probbasedanomalyjobtracker', ParameterType.INTEGER, 'job_tracker_id')

    METRICS_CREATION = QueueJobInstruction('metricscreation',  MetricsJobProcessor.create_metric)
    METRICS_CREATION.add_parameter_instruction('startdate', ParameterType.DATE, 'start_date')
    METRICS_CREATION.add_parameter_instruction('enddate', ParameterType.DATE, 'end_date')
    METRICS_CREATION.add_parameter_instruction('locationlevel', ParameterType.STRING, 'location_level')
    METRICS_CREATION.add_parameter_instruction('locationid', ParameterType.INTEGER, 'location_id')
    METRICS_CREATION.add_parameter_instruction('durationtype', ParameterType.STRING, 'duration_type')

    #Batch syncing
    SYNC_UPKEEP_ASSET_METERS = QueueJobInstruction('upkeepassetmetersync', BaseUpkeepAssetManager.sync_asset_meters)
    SYNC_UPKEEP_ASSET_METERS.add_parameter_instruction('assetmeterid', ParameterType.INTEGER, 'asset_meter_id')
    SYNC_UPKEEP_ASSET_METERS.add_parameter_instruction('assettype', ParameterType.STRING, 'asset_type')

    SYNC_MAINTAINX_ASSET_METERS = QueueJobInstruction('maintainxassetmetersync', MaintainxAssetManager.sync_asset_meters)
    SYNC_MAINTAINX_ASSET_METERS.add_parameter_instruction('assetmeterid', ParameterType.INTEGER, 'asset_meter_id')
    SYNC_MAINTAINX_ASSET_METERS.add_parameter_instruction('assettype', ParameterType.STRING, 'asset_type')

    SYNC_MAINTAINX_METER_SINGLE_JOB =  QueueJobInstruction('maintainxmeterscentraljob', MaintainxSync.sync_asset_meters_centralized)

    SYNC_MAINTAINX_ASSETS_CENTRALIZED = QueueJobInstruction('maintainxassetsupdate', MaintainxSync.sync_assets_centralized)
    
    SYNC_UPKEEP_ROOM_METERS = QueueJobInstruction('upkeeproommetersync', BaseUpkeepAssetManager.sync_room_meters)
    SYNC_UPKEEP_ROOM_METERS.add_parameter_instruction('roommeterid', ParameterType.INTEGER, 'room_meter_id')

    SYNC_MAINTAINX_ROOM_METERS = QueueJobInstruction('maintainxroommetersync', MaintainxAssetManager.sync_room_meters)
    SYNC_MAINTAINX_ROOM_METERS.add_parameter_instruction('roommeterid', ParameterType.INTEGER, 'room_meter_id')
    
    #individual syncing
    SYNC_UPKEEP_ASSET = QueueJobInstruction('upkeepassetsync', UpkeepAssetSyncJob.run_job)
    SYNC_UPKEEP_ASSET.add_parameter_instruction('assetid', ParameterType.INTEGER, 'asset_id')
    SYNC_UPKEEP_ASSET.add_parameter_instruction('assettype', ParameterType.STRING, 'asset_type')

    AUTORENEW_LEASE_SYNCER = QueueJobInstruction('autorenewleases',  AutoRenewLeases.auto_renew)

    WORK_ORDERS_FETCHER = QueueJobInstruction('workordersfetch',  WorkOrderFetcher.run_as_job)

    MAINTAINX_WORK_ORDERS_FETCHER = QueueJobInstruction('maintainxworkordersfetch',  MaintainxWorkOrderManager.run_fetch_as_job)

    TIME_USAGE_REPORT = QueueJobInstruction('timeusagereport', TimeUsageReport.run_job)
    TIME_USAGE_REPORT.add_parameter_instruction('sendto', ParameterType.STRING, 'send_to')
    TIME_USAGE_REPORT.add_parameter_instruction('days', ParameterType.INTEGER, 'days')
    TIME_USAGE_REPORT.add_parameter_instruction('months', ParameterType.INTEGER, 'months')

    REFUND_QUEUED_AUTHORIZE = QueueJobInstruction('refundqueuedauthorize', CompleteAuthorizeRefunds.run)
    
    PROCESS_REFUND_REQUEST = QueueJobInstruction('processrefundrequest', CompleteEnqueuedCreditCardRefund.run)
    PROCESS_REFUND_REQUEST.add_parameter_instruction('requestid', ParameterType.INTEGER, 'request_id')

    CLEAN_SLOTSTATE_TABLE = QueueJobInstruction('cleanslotstatetable', CleanSlotStateTable.run)

    UPLOAD_ASSET_ATTACHMENTS = QueueJobInstruction('uploadassetattachments', UploadAssetAttachments.run)
    UPLOAD_ASSET_ATTACHMENTS.add_parameter_instruction('assetid', ParameterType.INTEGER, 'asset_id')

    EMPLOYEE_SCANS_ANALYSIS = QueueJobInstruction('employeescansanalysis', EmployeeScanAnalysis.run_as_job)

    VOLATILITY_BASED_ANOMALY_DETECTION = QueueJobInstruction('volatilityanomalydetection', VolatilityAnomalyDetector.run_as_single_job)
    #VOLATILITY_BASED_ANOMALY_DETECTION_SINGLE_ROOM = QueueJobInstruction('volatilityanomalydetection', AnomalyDetector.run_as_single_job)
    #TIED_RUN = QueueJobInstruction('tiedrun', TiedRunManager.run)
    #TIED_RUN.add_parameter_instruction('steps', ParameterType.STRING, 'steps')


 #   SLOTMACHINE_PAIRING_JOB = QueueJobInstruction('slotmachinepairing',  MetricsJobProcessor.create_metric)
 #   SLOTMACHINE_PAIRING_JOB.add_parameter_instruction('submissionid', ParameterType.STRING, 'submission_id')
 #   SLOTMACHINE_PAIRING_JOB.add_parameter_instruction('codereadrusername', ParameterType.STRING, 'tech_username')
 #   SLOTMACHINE_PAIRING_JOB.add_parameter_instruction('fascardreader', ParameterType.STRING, 'fascard_reader')
 #   SLOTMACHINE_PAIRING_JOB.add_parameter_instruction('assettag', ParameterType.STRING, 'asset_tag')
 #   SLOTMACHINE_PAIRING_JOB.add_parameter_instruction('datamatrixstring', ParameterType.STRING, 'data_matrix_string')


    INSTRUCTIONS = {
                    DEBUG_INSTRUCTION.job_name: DEBUG_INSTRUCTION,
                    SLOT_FINDER_INSTRUCTION.job_name: SLOT_FINDER_INSTRUCTION,
                    SLOT_STATE_FINDER_INSTRUCTION.job_name: SLOT_STATE_FINDER_INSTRUCTION,
                    OUT_OF_ORDER_SEND.job_name: OUT_OF_ORDER_SEND,
                    UPKEEP_REPORT_SEND.job_name: UPKEEP_REPORT_SEND,
                    REVENUE_SCRAPE_INSTRUCTION.job_name: REVENUE_SCRAPE_INSTRUCTION,
                    FASCARD_USER_SCRAPE_INSTRUCTION.job_name: FASCARD_USER_SCRAPE_INSTRUCTION,
                    REVENUE_MATCH_INSTRUCTION.job_name: REVENUE_MATCH_INSTRUCTION,
                    METRICS_CREATION.job_name: METRICS_CREATION,
                    PRICING_HISTORY_SCRAPE_INSTRUCTION.job_name: PRICING_HISTORY_SCRAPE_INSTRUCTION,
                    EQUIPMENT_FINDER_INSTRUCITON.job_name: EQUIPMENT_FINDER_INSTRUCITON,
                    PRICING_REPORT_CREATION.job_name: PRICING_REPORT_CREATION,
                    PRICING_REPORT_JOBS_TRACKER.job_name: PRICING_REPORT_JOBS_TRACKER,
                    PRICING_DATA_FETCH.job_name: PRICING_DATA_FETCH,
                    CLIENT_REVENUE_REPORT.job_name : CLIENT_REVENUE_REPORT,
                    CLIENT_REVENUE_JOBS_TRACKER.job_name : CLIENT_REVENUE_JOBS_TRACKER,
                    CLIENT_REVENUE_FULL_REPORT.job_name: CLIENT_REVENUE_FULL_REPORT,
                    CLIENT_REVENUE_FULL_JOBS_TRACKER.job_name : CLIENT_REVENUE_FULL_JOBS_TRACKER,
                    TIMESHEETS_REPORT.job_name : TIMESHEETS_REPORT,
                    TIMESHEETS_REPORT_TRACKER.job_name : TIMESHEETS_REPORT_TRACKER,
                    PROB_BASED_ANOMALY.job_name: PROB_BASED_ANOMALY,
                    PROB_BASED_ANOMALY_TRACKER.job_name: PROB_BASED_ANOMALY_TRACKER,
                    LAUNDRY_ROOM_STATUS_FINDER.job_name: LAUNDRY_ROOM_STATUS_FINDER,
                    FASCARD_API_USER_SCRAPE_INSTRUCTION.job_name: FASCARD_API_USER_SCRAPE_INSTRUCTION,
                    LAUNDRY_ROOM_SYNC_INSTRUCTION.job_name: LAUNDRY_ROOM_SYNC_INSTRUCTION,
                    API_TRANSACTION_INGEST.job_name: API_TRANSACTION_INGEST,
                    UPDATE_TRANSACTIONS.job_name: UPDATE_TRANSACTIONS,
                    SYNC_UPKEEP_ASSET.job_name: SYNC_UPKEEP_ASSET,
                    SYNC_UPKEEP_ASSET_METERS.job_name: SYNC_UPKEEP_ASSET_METERS,
                    SYNC_UPKEEP_ROOM_METERS.job_name : SYNC_UPKEEP_ROOM_METERS,
                    SYNC_MAINTAINX_ASSET_METERS.job_name: SYNC_MAINTAINX_ASSET_METERS,
                    SYNC_MAINTAINX_ROOM_METERS.job_name: SYNC_MAINTAINX_ROOM_METERS,
                    SYNC_MAINTAINX_METER_SINGLE_JOB.job_name: SYNC_MAINTAINX_METER_SINGLE_JOB,
                    SYNC_MAINTAINX_ASSETS_CENTRALIZED.job_name: SYNC_MAINTAINX_ASSETS_CENTRALIZED,
                    AUTORENEW_LEASE_SYNCER.job_name : AUTORENEW_LEASE_SYNCER,
                    WORK_ORDERS_FETCHER.job_name : WORK_ORDERS_FETCHER,
                    MAINTAINX_WORK_ORDERS_FETCHER.job_name: MAINTAINX_WORK_ORDERS_FETCHER,
                    BILLING_GROUP_STATUS_FINDER.job_name : BILLING_GROUP_STATUS_FINDER,
                    TIME_USAGE_REPORT.job_name : TIME_USAGE_REPORT,
                    REFUND_QUEUED_AUTHORIZE.job_name : REFUND_QUEUED_AUTHORIZE,
                    PROCESS_REFUND_REQUEST.job_name : PROCESS_REFUND_REQUEST,
                    CLEAN_SLOTSTATE_TABLE.job_name: CLEAN_SLOTSTATE_TABLE,
                    UPLOAD_ASSET_ATTACHMENTS.job_name: UPLOAD_ASSET_ATTACHMENTS,
                    EMPLOYEE_SCANS_ANALYSIS.job_name: EMPLOYEE_SCANS_ANALYSIS,
                    VOLATILITY_BASED_ANOMALY_DETECTION.job_name: VOLATILITY_BASED_ANOMALY_DETECTION,
                    #TIED_RUN.job_name : TIED_RUN,
#                    SLOTMACHINE_PAIRING_JOB.job_name: SLOTMACHINE_PAIRING_JOB,
                    }

class QueueConfig(object):
    PRODUCTION_QUEUE_NAME = settings.QUEUE_CREDENTIALS['PRODUCTION_QUEUE_NAME']
    TEST_QUEUE_NAME = settings.QUEUE_CREDENTIALS['TEST_QUEUE_NAME']
    NIGHTLY_RUN_PROCESSING_QUEUE = settings.QUEUE_CREDENTIALS['NIGHTLY_RUN_PROCESSING_QUEUE']
    NIGHTLY_RUN_PROCESSING_QUEUE_DEAD = settings.QUEUE_CREDENTIALS['NIGHTLY_RUN_PROCESSING_QUEUE_DEAD']
    MAINTAINX_METER_UPDATE_QUEUE = settings.QUEUE_CREDENTIALS['MAINTAINX_QUEUE_NAME']
    MAINTAINX_METER_DEADLETTER = settings.QUEUE_CREDENTIALS['MAINTAINX_DEADLETTER_QUEUE_NAME']
    PRODUCTION_DEADLETTER_QUEUE_NAME = settings.QUEUE_CREDENTIALS['PRODUCTION_DEADLETTER_QUEUE_NAME']
    TEST_DEADLETTER_QUEUE_NAME = settings.QUEUE_CREDENTIALS['TEST_DEADLETTER_QUEUE_NAME']