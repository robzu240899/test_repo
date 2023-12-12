import pytz
from dateutil.parser import parse
from cmmsproviders.base import AbstractWorkOrderManager

class WorkOrderManager(AbstractWorkOrderManager):

    def __init__(self):
        self.API = self.API_CLASS()

    def clean_date(cls, date_record, convert_from=None, convert_to=None):
        if convert_from is None: convert_from = cls.CONVERT_FROM
        if convert_to is None: convert_to = cls.CONVERT_TO
        ingest_time = pytz.timezone(convert_from).localize(date_record)
        local_time_zone = pytz.timezone(convert_to)
        local_time = ingest_time.astimezone(local_time_zone)
        return local_time.replace(tzinfo=None)
    
    def transform_record(self, obj_payload, fieldmap):
        d = {}
        for old,new in fieldmap.items():
            val = obj_payload.get(old, None)
            if isinstance(val, list):
                val = ','.join(val)
            if val and new in self.DATE_FIELDS:
                val = parse(val).replace(tzinfo=None)
                val = self.clean_date(val)
            d[new] = val
        return d

    def update_record(self, provider_record):
        transformed_record = self.transform_record(provider_record, self.WORK_ORDER_FIELD_MAP)
        q = {self.provider_id_attr : transformed_record.get(self.provider_id_attr)}
        try:
            record = self.model.objects.get(**q)
            self.model.objects.filter(**q).update(**transformed_record)
        except self.model.DoesNotExist:
            work_order = self.model.objects.create(**transformed_record)
        return True