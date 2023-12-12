'''
Created on Apr 18, 2017

@author: Thomas
'''
import os
import logging
import pickle
import random
import time
import sys
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from hashlib import sha1
from io import BytesIO
from zipfile import ZipFile
from django.db import transaction
from django.db.models import Q
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.db.models import F
from django.template import defaultfilters
from django.template.loader import get_template
from queuehandler.utils import Aurora
from reporting.models import PricingReportJobInfo, PricingReportJobsTracker
from reporting.finance.internal.pricing_report import CustomPricingHistoryReport
from reporting.finance.internal.tasks import PricingHistoryWorker
from reporting.helpers import S3Upload
from reporting.models import MetricsCache, BillingGroup, CustomPriceHistory, MetricsComputationWatcher, MeterRaise
from revenue.models import LaundryTransaction
from roommanager.models import LaundryRoom, Machine
from .calculate import CacheFramework
from ..enums import MetricType, DurationType, LocationLevel

logger = logging.getLogger(__name__)


from functools import wraps

def close_db_connection(ExceptionToCheck=Exception, raise_exception=False, notify=False):
    """Close the database connection when we're finished, django will have to get a new one..."""
    def deco_wrap(f):
        @wraps(f)
        def f_wrap(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception as e:
                raise e
            finally:
                from django.db import connection; 
                connection.close();
        return f_wrap
    return deco_wrap


class MetricsJobProcessor(object):
    required_fields = (
        'start_date', 
        'end_date', 
        'location_level', 
        'location_id',
    )

    @classmethod
    @close_db_connection()
    def calculate_and_cache(cls, **kwargs):
        """
            If there is not an existing MetricsCache record for the metric that
            is about to be computed, the function creates a new MetricsCache record
            with needs_processing set to True by default. Then, it invokes
            CacheFramework.calculate_and_cache method in order to compute the metric's result.
            If the method computes the metric result successfuly, the MetricsCache's needs_processing
            attribute is set to False
        """
        queryset = kwargs.pop('queryset')
        try:
            try:
                metric_record = MetricsCache.objects.get(**kwargs)
            except MetricsCache.DoesNotExist:
                metric_record = False
            if not metric_record:
                metric_data = kwargs.copy()
                metric_data['needs_processing'] = True
                metric_record = MetricsCache.objects.create(**metric_data)
            kwargs['queryset'] = queryset
            kwargs['metric_record'] = metric_record
            calculated_metric = CacheFramework.calculate_and_cache(**kwargs)
            #logger.info("Result: {}".format(calculated_metric.result))
        except Exception as e:
            duration = kwargs.get('duration')
            location_level = kwargs.get('location_level')
            location_id = kwargs.get('location_id')
            err_str = 'Failed calcuting metric {} in {} with id {}. Exception: {}'.format(
                    duration, location_level, location_id, e)
            logger.info(err_str)
            logger.error(e)
        return True

    # @classmethod
    # @transaction.atomic
    # def _save_placeholders(cls, **kwargs):
    #     """
    #         Atomic transaction to save MetricsCache Placeholder models for later processing
    #     """
    #     model_dict = {
    #         LaundryRoom: LocationLevel.LAUNDRY_ROOM,
    #         BillingGroup: LocationLevel.BILLING_GROUP,
    #         Machine: LocationLevel.MACHINE
    #     }

    #     to_be_created = []
    #     for model, location_level in model_dict.items():
    #         for obj in model.objects.all():
    #             for metric_type, _ in MetricType.CHOICES:
    #                 metric_record = MetricsCache(
    #                     location_level = location_level,
    #                     location_id = obj.id,
    #                     metric_type = metric_type,
    #                     **kwargs,
    #                 )
    #                 to_be_created.append(metric_record)
    #     MetricsCache.objects.bulk_create(to_be_created)

    # @classmethod
    # def schedule_extra_metrics(cls):
    #     """
    #         Create MetricsCache placeholder models for monthly and annual metrics
    #     """
    #     today = date.today()
    #     month_ago = today - relativedelta(months=1)
    #     previous_month_start = date(month_ago.year, month_ago.month, 1)
    #     year_ago = today - relativedelta(years=1)
    #     previous_year_start = date(year_ago.year, 1, 1)
    #     start_dates_data = [
    #         (previous_month_start, {"months" : 1}, [DurationType.MONTH, DurationType.BEFORE]),
    #         (previous_year_start, {"years" : 1}, [DurationType.YEAR])
    #     ]

    #     for start_date, delta_data, duration_types in start_dates_data:
    #         query = MetricsCache.objects.filter(start_date=start_date)
    #         for duration_type in duration_types:
    #             query = query.filter(duration = duration_type)
    #             logger.info(f"Trying to schedule metrics for start_date: {start_date} and duration: {duration_type}")
    #             if query.count() == 0:
    #                 data = {
    #                     'start_date' : start_date,
    #                     'duration' : duration_type,
    #                     'needs_processing': True,
    #                     'ripe_date': start_date + relativedelta(**delta_data)
    #                 }
    #                 cls._save_placeholders(**data)
    #             else:
    #                 logger.info("Skipping scheduling. Query count of existing metrics is more than 0")

    @classmethod
    @transaction.atomic
    def _save_placeholders(cls, payload: dict, ids: list):
        to_create = []
        for loc_id in ids:
            metric = MetricsCache(location_id=loc_id, **payload)
            to_create.append(metric)
        MetricsCache.objects.bulk_create(to_create)

    @classmethod
    def _get_metrics_watcher(cls, metrics_watcher_payload, location_ids):
        """
        The expected attribute of the watcher object is calculated multiplyng by the amount
        of existing metric types since we don't store metric type granularity on the watcher
        """
        payload = metrics_watcher_payload.copy()
        try:
            metrics_watcher = MetricsComputationWatcher.objects.get(**payload)
        except MetricsComputationWatcher.DoesNotExist:
            total_metrics = len(MetricType.CHOICES)
            if payload.get('duration') != DurationType.MONTH:
                total_metrics = total_metrics - 1 #REFUNDS are not included 
            if payload.get('duration') == DurationType.BEFORE:
                if payload.get('location_level') != LocationLevel.MACHINE:
                    total_metrics = total_metrics - 2 #REVENUE_NUM_NO_DATA_DAYS and REVENUE_NUM_ZERO_DOLLAR_TRANSACTIONS not included
                else:
                    total_metrics = 0
            if total_metrics < 0: total_metrics = 0
            payload['expected'] = location_ids.count() * total_metrics
            metrics_watcher = MetricsComputationWatcher.objects.create(**payload)
            metrics_watcher.save()
        return metrics_watcher

    
    @classmethod
    def schedule_extra_metrics(cls, start_from_date=None):
        if not start_from_date: today = date.today()
        month_ago = today - relativedelta(months=1)
        previous_month_start = date(month_ago.year, month_ago.month, 1)
        logger.info(f"Calling scheduled extra metrics with start_from_date: {start_from_date} and previous_month_start: {previous_month_start}")
        year_ago = today - relativedelta(years=1)
        previous_year_start = date(year_ago.year, 1, 1)
        start_dates_data = [
            (previous_month_start, {"months" : 1}, [DurationType.MONTH, DurationType.BEFORE]),
            (previous_year_start, {"years" : 1}, [DurationType.YEAR])
        ]

        obj_map = {
            LocationLevel.MACHINE : Machine,
            LocationLevel.LAUNDRY_ROOM : LaundryRoom,
            LocationLevel.BILLING_GROUP : BillingGroup
        }

        for start_date, delta_data, duration_types in start_dates_data:
            for location_level, location_obj in obj_map.items():
                base_query = MetricsCache.objects.filter(start_date=start_date, location_level=location_level)
                # TODO: Should we naively include all location objects or should we filter out
                # consistently by location's creation date (location being either a Machine, Room or BG)      
                locations_ids = location_obj.objects.all().values_list('id', flat=True).distinct()
                for duration_type in duration_types:
                    metrics_watcher_payload = {
                        "location_level" : location_level,
                        "start_date" : start_date,
                        "duration" : duration_type
                    }
                    metrics_watcher = cls._get_metrics_watcher(metrics_watcher_payload.copy(), locations_ids)
                    if metrics_watcher.expected <= metrics_watcher.scheduled:
                        continue
                    total_already_scheduled = 0
                    for metric_type, _ in MetricType.CHOICES:
                        if duration_type != DurationType.MONTH and metric_type == MetricType.REFUNDS: continue
                        if duration_type == DurationType.BEFORE:
                            if metric_type in [MetricType.REVENUE_NUM_NO_DATA_DAYS,MetricType.REVENUE_NUM_ZERO_DOLLAR_TRANSACTIONS]:
                                continue
                            if location_level == LocationLevel.MACHINE: continue
                        query = base_query.filter(
                            duration=duration_type,
                            metric_type=metric_type
                        )
                        already_scheduled_ids = query.values_list('location_id', flat=True)
                        total_already_scheduled += already_scheduled_ids.count()
                        missing_ids = set(locations_ids) - set(already_scheduled_ids)
                        metrics_payload = metrics_watcher_payload.copy()
                        metrics_payload['metric_type'] = metric_type
                        metrics_payload['needs_processing'] = True
                        metrics_payload['ripe_date'] = start_date + relativedelta(**delta_data)
                        cls._save_placeholders(metrics_payload, missing_ids)
                    metrics_watcher.scheduled = total_already_scheduled
                    metrics_watcher.save()

    @classmethod
    def get_extrametrics_queryset(cls):
        today = date.today()
        q = MetricsCache.objects.filter(
            Q(needs_processing=True, ripe_date__lte=today) | Q(needs_processing=True)
        )
        if today.month != 1 and today.day !=1: q = q.exclude(duration=DurationType.YEAR)        
        return q

    @classmethod
    def create_metric(cls, **kwargs):
        #See cls.required_fields for a list of expected arguments in the kwargs payload
        assert all([field in kwargs.keys() for field in cls.required_fields]) is True
        counter = 0
        start_date = kwargs.get('start_date')
        end_date = kwargs.pop('end_date')
        if kwargs.get('metric_type') is not None:
            metric_types = [
                (kwargs.get('metric_type'), kwargs.get('metric_type'))
            ]
        else:
            metric_types = MetricType.CHOICES
        if kwargs.get('duration_type') == 'daily-basis' or kwargs.get('duration_type') is None:
            duration_types = DurationType.DAILY_BASIS
        else:
            duration_types = [
                (kwargs.get('duration_type'), kwargs.get('duration_type'))
            ]
        kwargs.pop('duration_type')

        #NOTE:
        #Include transactions completed by employees only if credit_card_amount ig > 0
        #this most likely means that a person did a top-off after the employee started the machine.
        queryset = LaundryTransaction.objects.filter(
            Q(fascard_user__is_employee=True, credit_card_amount__gt=0) | Q(fascard_user__is_employee=False) | Q(fascard_user=None)
        )
        for offset in range((end_date - start_date).days):
            dt = start_date + timedelta(days=offset)
            for metric_type, _ in metric_types:
                for duration, _ in duration_types:
                    if duration == DurationType.BEFORE and metric_type in [MetricType.REVENUE_NUM_NO_DATA_DAYS, MetricType.REVENUE_NUM_ZERO_DOLLAR_TRANSACTIONS]:
                        continue
                    elif duration == DurationType.MONTH and dt.day != 1:
                        continue
                    elif duration not in [DurationType.MONTH, DurationType.YEAR] and kwargs.get('location_level') == LocationLevel.MACHINE:
                        continue
                    elif duration == DurationType.YEAR and dt.day != 1 and dt.month != 1:
                        continue
                    elif duration != DurationType.MONTH and metric_type == MetricType.REFUNDS:
                        continue
                    else:
                        kwargs['metric_type'] = metric_type
                        kwargs['duration'] = duration
                        kwargs['queryset'] = queryset
                        cls.calculate_and_cache(**kwargs)
        location_level = kwargs.get('location_level')
        location_id = kwargs.get('location_id')
        logger.info('Finished calculating metrics for {} with id {}'.format(location_level, location_id))
        return True

# class PricingReportJobProcessor():
#     called_from_queue = True

#     @classmethod
#     def generate_report(cls, report_info_id):
#         try:
#             report_info = PricingReportJobInfo.objects.get(pk=report_info_id)
#         except Exception as e:
#             raise Exception(
#                 'The pricing report generation job failed with: {}'.format(e))
#         laundry_room_ids = [x.id for x in report_info.laundry_rooms.all()]
#         logger.info("Started  PricingReportJobProcessor with PricingReportJobInfo ID: {}".format(
#             report_info.pk))
#         start_report = time.time()
#         report_data = CustomPricingHistoryReport(
#             laundry_rooms=laundry_room_ids,
#             rolling_mean_periods=report_info.rolling_mean_periods,
#             called_from_queue=cls.called_from_queue
#         ).generate_response()
#         end_report = time.time()

#         logger.info("Finished Executing generate_response function of the job. Took: {}".format(
#             end_report - start_report))
#         context = {'queryset': report_data,
#                    'called_from_queue': cls.called_from_queue}
        # html_start = time.time()
        # template = get_template('pricing_history_report_queued.html')
        # html_response = template.render(context).encode(encoding='UTF-8')
        # html_binary_data = BytesIO(html_response)
        # html_end = time.time()
        # logger.info("Finished Executing HTML Render of the job. Took: {}".format(
        #     html_end - html_start))

        # if len(report_info.user_requested_email) == 0 or report_info.user_requested_email is None:
        #     user_email = settings.PRICING_REPORT_DEFAULT_EMAIL_TO
        # else:
        #     user_email = report_info.user_requested_email

        # logger.info("Going to try to upload HTML data to S3")
        # file_name = 'Pricing-Changes-Report-{}-{}.html'.format(
        #     report_info.timestamp.strftime("%Y-%m-%d"),
        #     sha1(str(random.random()).encode('utf-8')).hexdigest()[:5]
        # )
        # bucket_name = 'pricing-change-reports'
        # s3_handler = S3Upload(html_binary_data, bucket_name , file_name)
        # file_uploaded = s3_handler.upload()
        # if file_uploaded:
        #     logger.info("File Uploaded with no errors. Filename: {}".format(file_name))
        #     #file_link = s3_handler.get_file_link()
        #     email_start = time.time()
        #     message = EmailMessage(
        #         subject = 'Pricing Report Attached',
        #         body = 'Find attached the on-demand pricing report you solicited on {}. Or, find it in S3 under the bucket: {} with the filename: {}'.format(
        #             report_info.timestamp,
        #             bucket_name,
        #             file_name
        #         ),
        #         to = [user_email],
        #     )
        #     message.attach('pricing-report.html', html_response)
        #     message.send(fail_silently=False)
        #     email_end = time.time()
        #     logger.info("Finished Executing Email Send of the job. Took: {}".format(email_end - email_start))
        #     return True

class PricingReportJobProcessor():
    called_from_queue = True

    @classmethod
    def generate_report(cls, report_info_id):
        try:
            report_info = PricingReportJobInfo.objects.get(pk=report_info_id)
        except Exception as e:
            raise Exception('The pricing report generation job failed with: {}'.format(e))

        laundry_room = report_info.laundry_room
        assert laundry_room, "No Laundry Room related to Job info with ID: {}".format(report_info.id)
        
        logger.info("Started  PricingReportJobProcessor with PricingReportJobInfo ID: {}".format(
            report_info.pk))

        start_report = time.time()
        report = CustomPricingHistoryReport(
            laundry_room_id=laundry_room.id,
            called_from_queue=cls.called_from_queue,
            months = report_info.months,
        )
        report_data = report.generate_response()
        end_report = time.time()

        #write into binary data. Pickle File
        # pickle_db = {}
        # pickle_db[laundry_room] = report_data[laundry_room]
        # pickle_content = pickle.dumps(pickle_db)
        # file_name = 'Pricing-Changes-Pickle-{}-{}-{}.pkl'.format(
        #     laundry_room,
        #     report_info.timestamp.strftime("%Y-%m-%d"),
        #     sha1(str(random.random()).encode("utf-8")).hexdigest()[:5])

        final_queryset = {
            laundry_room : report_data[laundry_room]
        }
        bg_name = laundry_room.get_billing_group()
        pricing_changes_data = report.get_pricing_data(laundry_room)
        if not bg_name:
            bg_name = 'None-BillingGroup'
        file_name = "{}/{}-{}.html".format(
            defaultfilters.slugify(bg_name),
            defaultfilters.slugify(laundry_room),
            sha1(str(random.random()).encode("utf-8")).hexdigest()[:5]
        )
        #Save the report as an individual HTML file
        context = {
            'queryset': final_queryset,
            'called_from_queue': cls.called_from_queue,
            'use_colors' : report_info.colors,
            'room_pricing_changes_history': pricing_changes_data
        }
        template = get_template('pricing_history_report_queued.html')
        html_response = template.render(context).encode(encoding='UTF-8')
        #html_bytes_like = str.encode(html_response)
        #html_binary_data = BytesIO(html_response)

        try:
            #report_info.report_pickle_file.save(file_name, ContentFile(pickle_content))
            report_info.report_html_file.save(file_name, ContentFile(html_response))
        except Exception as e:
            raise Exception("Failed saving file. Exception: {}".format(e))

        job_tracker_id = report_info.job_tracker.id
        if report_data:
            logger.info(
                'CustomPricingHistoryReport Job execution was successful. Pricing report for room: {}'.format(
                    report_info.laundry_room
                )
            )
            job_tracker = PricingReportJobsTracker.objects.get(pk=job_tracker_id)
            logger.info("Starting Jobs Processed: {}".format(job_tracker.jobs_processed))
            if job_tracker.jobs_processed < job_tracker.jobs_being_tracked.all().count():
                job_tracker.jobs_processed = F('jobs_processed') + 1
                job_tracker.save()
            logger.info("Finishing Jobs Processed: {}".format(job_tracker.jobs_processed))
        else:
            logger.info('CustomPricingHistoryReport response was not successful')
        return True


class PricingJobsTrackerJobProcessor():
    called_from_queue = True
    upload_bucket_name = 'pricing-change-reports'

    @classmethod
    def generate_index_table(cls, jobs_tracker):

        laundry_rooms = [job_info.laundry_room for job_info in jobs_tracker.jobs_being_tracked.all()]
        index_table_data = {}

        for job_info in jobs_tracker.jobs_being_tracked.all():
            room = job_info.laundry_room
            bg_name = room.get_billing_group()
            if not bg_name:
                bg_name = 'None-BillingGroup'
            bg_name_slug = defaultfilters.slugify(bg_name)
            if not bg_name_slug in index_table_data:
                today = date.today()
                billing_group = room.get_billing_group()
                if billing_group: meter_raises = MeterRaise.objects.filter(billing_group=billing_group)
                else: meter_raises = []
                index_table_data[bg_name_slug] = {"full_name":bg_name, "rooms":{}, 'scheduled_meter_raises': meter_raises, 'max_meter_raises': billing_group.max_meter_raises}
            try: last_pricing_change = CustomPriceHistory.objects.filter(laundry_room=room).order_by('detection_date').last().detection_date
            except: last_pricing_change = 'Unknown'
            try: last_pricing_period_start = room.pricing_periods.all().last().start_date
            except: last_pricing_period_start = 'Unknown'
            #Scheduled meter raises
            index_table_data[bg_name_slug]["rooms"].update(
                {
                    room.id:(
                        job_info.report_html_file.name,
                        room.display_name,
                        last_pricing_change,
                        last_pricing_period_start,
                    )
                }
            )

        context_dict = {
            "table_data" : index_table_data
        }
        template = get_template('pricing_report_index_table.html')
        html_response = template.render(context_dict).encode(encoding='UTF-8')
        return html_response  

    @classmethod
    def generate_zip_file(cls, jobs_tracker):
        s = BytesIO()
        zf = ZipFile(s, "w")
        logger.info('Creating Zip File')
        for pricing_report in jobs_tracker.jobs_being_tracked.all():
            s3_path = pricing_report.report_html_file.name.split("/")
            fname = s3_path[len(s3_path)-1]
            billing_group = pricing_report.laundry_room.get_billing_group() or "None-BillingGroup"
            subdir = defaultfilters.slugify(billing_group.__str__())
            zip_path = os.path.join(subdir, fname)
            zf.writestr(zip_path, pricing_report.report_html_file.read())
        index_table = cls.generate_index_table(jobs_tracker)
        zf.writestr("index.html", index_table)
        logger.info('Succesfully created Zip File')
        for file in zf.filelist:
            file.create_system = 0
        zf.close()
        file_content = s.getvalue()
        return file_content

    @classmethod
    def upload_file_to_s3(cls, file_name, file_binary_content):
        s3_handler = S3Upload(file_binary_content, cls.upload_bucket_name , file_name)
        file_uploaded = s3_handler.upload()
        return file_uploaded

    @classmethod
    def get_s3_url(cls, file_name):
        s3_handler = S3Upload(None, cls.upload_bucket_name , file_name)
        return s3_handler.get_file_link()

    @classmethod
    #def send_email_message(cls, file_name, to_email, html_response, jobs_tracker):
    def send_email_message(cls, file_name, to_email, jobs_tracker):
        logger.info("File Uploaded with no errors. Filename: {}".format(file_name))
        #file_link = s3_handler.get_file_link()
        email_start = time.time()
        message = EmailMessage(
            subject = 'Pricing Report Completed',
            body = 'On-demand pricing report you solicited on {}. \
                S3 Link: {}'.format(
                    jobs_tracker.timestamp,
                    cls.get_s3_url(file_name),
                ),
            to = to_email.split(','),
        )
        #if html_response:
        #    message.attach('pricing-report.html', html_response)
        message.send(fail_silently=False)
        email_end = time.time()
        logger.info("Finished Executing Email Send of the job. Took: {}".format(email_end - email_start))
        return True      

    @classmethod
    def process_all_jobs(cls, jobs_tracker_id):
        logger.info('Started executing ClientRevenueReport JobsTracker processor.')
        try:
            jobs_tracker = PricingReportJobsTracker.objects.get(pk=jobs_tracker_id)
        except Exception as e:
            raise Exception(
                'Could not find PricingReportJobsTracker model with id: {}. Failed with exception: {}'.format(
                    jobs_tracker_id,
                    e)
                )

        while True:
            jobs_tracker = PricingReportJobsTracker.objects.get(pk=jobs_tracker_id)
            time.sleep(10)
            if jobs_tracker.jobs_being_tracked.all().count() == jobs_tracker.jobs_processed:
                logger.info('All jobs wered processed succesfully. Proceding to gather files for delivery')
                break

        #final_queryset = {}
        #for pricing_report in jobs_tracker.jobs_being_tracked.all():
        #    pricing_report.report_pickle_file.open()
        #    file_content = pricing_report.report_pickle_file.read()
        #    pickle_data = pickle.loads(file_content)
        #    for keys in pickle_data:
        #        final_queryset[keys] = pickle_data[keys]

        #context = {
        #    'queryset': final_queryset,
        #    'called_from_queue': cls.called_from_queue
        #}
        #template = get_template('pricing_history_report_queued.html')
        #html_response = template.render(context).encode(encoding='UTF-8')
        #html_binary_data = BytesIO(html_response)
        
        file_name = 'Pricing-Changes-Report-{}-{}.zip'.format(
            jobs_tracker.timestamp.strftime("%Y-%m-%d"),
            sha1(str(random.random()).encode("utf-8")).hexdigest()[:5]
        )
        file_content = cls.generate_zip_file(jobs_tracker)

        if not jobs_tracker.user_requested_email:
            user_email = settings.PRICING_REPORT_DEFAULT_EMAIL_TO
        else:
            user_email = jobs_tracker.user_requested_email
        logger.info("Going to try to upload HTML data to S3")
        #cls.upload_file_to_s3(file_name, html_binary_data)
        cls.upload_file_to_s3(file_name, file_content)
        logger.info("Uploaded file to S3")
        file_size = sys.getsizeof(file_content) / (1024 ** 2.0) #mb size
        if file_size >= 9:
            html_response = None
        #cls.send_email_message(file_name, user_email, html_response, jobs_tracker)
        cls.send_email_message(file_name, user_email, jobs_tracker)
        #Aurora min capacity was previously increased in the thread that enqueues the jobs
        Aurora.modify_aurora_cluster_min_capacity(min_capacity=1, sleep_time=60)
        return True


class PricingDataFetchJobProcessor():

    @classmethod
    def fetch_data(cls, laundry_group_id):
        phworker = PricingHistoryWorker(laundry_group_id)
        phworker.job()
