import logging
import time
from io import BytesIO
from datetime import datetime, date
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.template.loader import render_to_string
from main.threads import EmailThread
from reporting.reliability.outoforder_report import OOOReport, OOOReportManager
from reporting.reliability.upkeep_report import UpkeepReportManager
from reporting.reliability.anomaly_detection import AnomalyDetection
from reporting.models import BillingGroup, AutoRenewHistory, AnomalyDetectionJobInfo, AnomalyDetectionJobTracker
from reporting.finance.clientreport.job import ClientReportProcessor
from roommanager.models import LaundryRoom


logger = logging.getLogger(__name__)


class ReporterJobs(object):
    
    @classmethod
    def out_of_order(cls):
        #OOOReport().run_report()
        OOOReportManager().generate()

    @classmethod
    def upkeep_report(cls):
        UpkeepReportManager().generate()


class AutoRenewLeases:

    @classmethod
    def _build_payload(cls, bg):
        payload = {
            'billing_group' : bg,
            'lease_start_date' : bg.lease_term_start,
            'lease_end_date' : bg.lease_term_end,
            'original' : True
        }
        return payload


    #make transaction atomic
    @classmethod
    def auto_renew(cls):
        today = date.today()
        bgs = BillingGroup.objects.filter(lease_term_end=today, lease_term_auto_renew=True)
        
        for bg in bgs:
            with transaction.atomic():
                if bg.autorenew_history.all().count() == 0:
                    payload = cls._build_payload(bg)
                    AutoRenewHistory.objects.create(**payload)
                bg.lease_term_start = today
                bg.lease_term_duration_months = bg.lease_term_auto_renew_length
                bg.lease_term_duration_days = 0
                bg.save()
                bg.refresh_from_db()
                payload = cls._build_payload(bg)
                payload['original'] = False
                AutoRenewHistory.objects.create(**payload)


class BillingGroupStatusFinder:

    @classmethod
    def run_analysis(cls):
        for bg in BillingGroup.objects.all():
            statuses = list()
            for room_extension in bg.laundryroomextension_set.all():
                statuses.append(room_extension.laundry_room.is_active)
            if bg.is_active:
                if not any(statuses):
                    bg.is_active = False
            else:
                if all(statuses):
                    bg.is_active = True
            bg.save()


    #Wanna call Full Low Level Report
    #Client Batches report
    #Rent Paid to Client Report - All Choices

class AnomalyDetectionJobTrackerProcessor():
    template_name = 'prob_based_anomaly_detection_email.html'

    @classmethod
    def report_anomalies_centralized(cls, anomalies):
        email = EmailMessage(
            'Probability-Based Anomalies Report',
            'Please see attached',
            settings.DEFAULT_FROM_EMAIL,
            settings.IT_EMAIL_LIST
        )
        rendered_response = render_to_string(cls.template_name,{'anomalies': anomalies})
        email.attach('probability_based_anomalies_report.html', rendered_response, 'text/html')
        email.send(fail_silently=False)
        return True

    @classmethod
    def run_as_job(cls, job_tracker_id, retries=360):
        job_tracker = AnomalyDetectionJobTracker.objects.get(id=job_tracker_id)
        counter = 0
        success = False
        while True:
            if counter == retries:
                logger.info("Anomaly detection jobs tracker timedout")
                break
            time.sleep(10)
            job_tracker.refresh_from_db()
            if job_tracker.jobs_being_tracked.all().count() == job_tracker.jobs_processed:
                success = True
                logger.info('All jobs wered processed succesfully. Proceding to gather messages for delivery')
                break
            counter += 1        
        if success:
            job_tracker.refresh_from_db()
            anomalies = job_tracker.jobs_being_tracked.filter(anomaly_detected=True)
            cls.report_anomalies_centralized(anomalies)
        return True


class AnomalyDetectionJobProcessor(ClientReportProcessor):
    job_info_model = AnomalyDetectionJobInfo
    job_tracker_model = AnomalyDetectionJobTracker
    report_processor = AnomalyDetection
    tracked_model_name = 'machine'

    def generate_report(self, report_job_info):
        self.report_info = self.get_report_info(report_job_info)
        payload = {
            "report_job_info" : report_job_info,
            "jobs_tracker" : self.report_info.job_tracker
        }
        logger.info(f"Calling create_report for machine {self.report_info.machine}")
        start = datetime.now()
        self.create_report(payload)
        end = datetime.now()
        logger.info(f"Done creating report for machine {self.report_info.machine}")
        logger.info(f"Detecting anomalies on Machine {self.report_info.machine} took {(end-start).seconds}")
        self.update_tracker()
        return True

    @classmethod
    def run_as_job(cls, report_job_info):
        ins = AnomalyDetectionJobProcessor()
        logger.info(f"Calling AnomalyDetectionJobProcessor.generate_report for report_job_info {report_job_info}")
        try:
            ins.generate_report(report_job_info)
        except Exception as e:
            #body_str = f'An exception ocurred while processing a full low-level report: {e}'
            #instead of rising an exception we save the error as a txt file
            raise (e)
        return True