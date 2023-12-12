import csv
import calendar
import io
import logging
from datetime import datetime, date
from django.db.models import query
from outoforder.models import CleanSlotStateTableLog, SlotState
from reporting.helpers import S3Upload
from dateutil.relativedelta import relativedelta
from roommanager.models import Slot 
from .ingest import SlotStateIngestor, APISlotStateIngestor, APILastRunTimeIngestor, LastRunTimeIngestor
from .endtime import EndTimeFixer
from .errormarker import ErrorMarkerManager


logger = logging.getLogger(__name__)


class SlotStateJobManager(object):
    
    @classmethod
    def run(cls,laundry_room_id):
        APISlotStateIngestor(laundry_room_id).ingest_states()
        APILastRunTimeIngestor().ingest(laundry_room_id)
        for slot in Slot.objects.filter(laundry_room_id=laundry_room_id):
            EndTimeFixer.fix_endtimes(slot)
        ErrorMarkerManager.mark_all(laundry_room_id)


class CleanSlotStateTable():
    s3_bucket_name = 'slotstates-data'

    @classmethod
    def _get_filename(cls, log):
        try:
            return f"{log.start_date.year}/{log.start_date.year}-{log.end_date.month}.csv"
        except Exception as e:
            logger.error(e, exc_info=True)
            return f"{log.id}.csv"

    @classmethod
    def convert_queryset_to_file(cls, queryset):
        field_names = [field.name for field in queryset.model._meta.fields]
        buff = io.StringIO()
        csv_writer = csv.writer(buff)
        csv_writer.writerow(field_names)
        for row in queryset.values_list(*field_names): csv_writer.writerow(row)
        return io.BytesIO(buff.getvalue().encode())

    @classmethod
    def run(cls, start_from_date=None):
        logger.info("Running clean slotstates table job")
        if not start_from_date: start_from_date = datetime.today()
        today = start_from_date
        logs_to_process = list(CleanSlotStateTableLog.objects.filter(success=False))
        if today.day == 1:
            #we keep only the last 3 months of records
            start_date = today - relativedelta(months=4)
            end_date = date(start_date.year, start_date.month,
                calendar.monthrange(*tuple([start_date.year, start_date.month,]))[1])
            logs_to_process.append(
                CleanSlotStateTableLog.objects.create(start_date = start_date, end_date = end_date))
        for log in logs_to_process:
            logger.info(f"Processing log with start: {log.start_date} and end: {log.end_date}")
            queryset = SlotState.objects.filter(
                local_start_time__date__gte = log.start_date,
                local_start_time__date__lte = log.end_date
            )
            file_obj = cls.convert_queryset_to_file(queryset)
            successful_upload = False
            try:
                successful_upload = S3Upload(file_obj, cls.s3_bucket_name, cls._get_filename(log)).upload()
            except Exception as e:
                logger.error(f"Failed uploading slotstates data to S3: {e}", exc_info=True)
                pass
            log.success = successful_upload
            log.save()
            if successful_upload: queryset.delete()
        return True