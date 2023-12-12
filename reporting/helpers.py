'''
Created on Apr 21, 2017

@author: Thomas
'''
import boto3
from datetime import date
from dateutil.relativedelta import relativedelta
from django.db.models import Count
from fascard.api import FascardApi
from roommanager.enums import MachineType, SlotType
from roommanager.models import LaundryRoom, Machine, MachineSlotMap, EquipmentType
from reporting.models import MetricsCache
from reporting.enums import LocationLevel, DurationType, RevenueSplitScheduleType


class Helpers():
    extension_fields = (
        'building_type',
        'legal_structure',
        'has_elevator',
        'is_outdoors',
        'laundry_in_unit'
    )

    @classmethod
    def get_number_machines(cls,laundry_room,machine_type=None):
        qry = MachineSlotMap.objects.filter(is_active=True,slot__laundry_room=laundry_room)
        if machine_type is not None:
            qry=qry.filter(machine__machine_type=machine_type)
        qry = qry.aggregate(num_machiens = Count('machine__id',distinct=True))
        return qry['num_machiens']

    @classmethod
    def get_number_of_pockets(cls, laundry_room, qry=None):
        """
        Specially designed for Internal Revenue Report.

        It counts a double barrel as 2 pockets and a single dryer as 1 pocket


        Daniel's docs:
        double barrels === 1x slot for 2x pockets.  for reporting purposes, it's 2x dryers

        stacked dryers ==== 2x slots,  1x machine, 2x pockets. 2 dryers.

        combostack ===== 2x slots (washer + dryer), 1x machine, 2x pockets (a washer + a dryer)
        for reporting purposes it's  1x washer + 1x dryer

        284 washington.
        """
        if not qry:
            qry = MachineSlotMap.objects.filter(is_active=True,slot__laundry_room=laundry_room)
        washers = 0
        dryers = 0
        machine_memory = []
        for msm in qry:
            if msm.slot.slot_type == SlotType.DOUBLE:
                dryers += 2
                continue
            if msm.machine.machine_type == MachineType.WASHER:
                washers += 1
            elif msm.machine.machine_type == MachineType.DRYER:
                dryers +=1
            elif msm.machine.machine_type == MachineType.COMBO_STACK:
                if not msm.machine.id in machine_memory:
                    dryers +=1
                    washers += 1
                    machine_memory.append(msm.machine.id)
            else:
                continue
        return (washers, dryers)

    @classmethod
    def get_billing_group_concatenated_data(cls, billing_group):
        bg_data = [0,0,0,[],[],[],[],[]]
        extensions = billing_group.laundryroomextension_set.filter(laundry_room__is_active=True)
        for ext in extensions:
            room = ext.laundry_room
            units = getattr(ext,'num_units')
            if units is None: units = 0
            bg_data[0] = bg_data[0] + units
            washers, dryers = cls.get_number_of_pockets(room)
            bg_data[1] = bg_data[1] + washers
            bg_data[2] = bg_data[2] + dryers
            for i, field in enumerate(cls.extension_fields, 3):
                v = getattr(ext, field, 'Unknown')
                if isinstance(v, bool):
                    if v: v = 'Yes'
                    else: v = 'No'
                elif hasattr(v, '__str__'):
                    v = v.__str__()
                if not v in bg_data[i]: bg_data[i].append(v)
        return bg_data

    @classmethod
    def get_billinggroup_extra_headers(cls):
        return ['Units Count', 'Washer Count', 'Dryer Count'] + list(cls.extension_fields)

    @classmethod
    def bg_extra_checks(cls, bg, cleaned_data, query=None):
        """
        Checks whether the required information for producing a report for a billing group
        is complete.
        """
        errors = []
        if not bg.laundryroomextension_set.all():
            errors.append(f"The Billing group {bg} has no laundry room extensions.")
        if not bg.revenuesplitrule_set.all():
            errors.append(f"The Billing group {bg} has no revenue split rules.")
        start_date = date(
            int(cleaned_data.get('start_year')),
            int(cleaned_data.get('start_month')),
            1
        )
        end_date = date(
            int(cleaned_data.get('end_year')),
            int(cleaned_data.get('end_month')),
            1
        )
        if bg.schedule_type != RevenueSplitScheduleType.GROSS_REVENUE: return errors
        if not query: query = MetricsCache.objects.filter(duration = DurationType.BEFORE)
        while start_date <= end_date:
            before_metrics = query.filter(
                location_id = bg.id,
                location_level = LocationLevel.BILLING_GROUP,
                start_date = start_date,
            )
            if not before_metrics:
                errors.append(
                    f"The Billing group {bg} has no complete BEFORE metrics for start_date {start_date}"
                )
            start_date = start_date = start_date + relativedelta(months=1)
        return errors


class MachineCountMismatchs():

    def __init__(self):
        self.api = FascardApi(laundry_group_id = 1)

    def find(self):
        issues = []
        rooms = LaundryRoom.objects.filter(is_active=True)
        for room in rooms:
            api_washers = 0
            api_dryers = 0
            try:
                api_slots = self.api.get_machines(fascard_location_id=room.fascard_code)
            except:
                issues.append((room, '', ''))
                continue
            for slot in api_slots:
                try:
                    equipment = EquipmentType.objects.filter(fascard_id = slot.get('EquipID')).last()
                except:
                    continue
                if equipment.machine_type == 0:
                    api_washers += 1
                elif equipment.machine_type == 1:
                    api_dryers += 1
            local_washers, local_dryers = Helpers.get_number_of_pockets(room)
            if local_washers!= api_washers or local_dryers != api_dryers:
                issues.append(
                    (
                        room,
                        f'Local Washers: {local_washers} vs API Washers: {api_washers}', 
                        f'Local Dryers: {local_dryers} vs API Dryers: {api_dryers}'
                    )
                )
        return issues


class S3Upload(object):
    def __init__(self, file_data, bucket, s3_filename):
        self.s3 = boto3.client('s3')
        self.file_data = file_data
        self.bucket = bucket
        self.s3_filename = s3_filename
        self.url_expiration = 36000

    def upload(self):
        try:
            self.s3.put_object(
                Body=self.file_data,
                Bucket=self.bucket,
                Key=self.s3_filename
            )
            return True
        except Exception as e:
            raise (e)

    def get_file_link(self):
        constructed_url = self.s3.generate_presigned_url(
            'get_object',
            Params = {
                'Bucket': self.bucket,
                'Key': self.s3_filename
            },
            ExpiresIn = self.url_expiration
        )
        return constructed_url
