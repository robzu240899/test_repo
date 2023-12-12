import time
import logging
from datetime import datetime, timedelta
from django.conf import settings
from django.core.mail import EmailMessage
from django.forms.models import model_to_dict
from django.template.loader import render_to_string
from reporting.models import CustomPriceHistory, PricingPeriod
from roommanager.enums import MachineType
from roommanager.job import LaundryRoomSync
from roommanager.models import LaundryGroup, LaundryRoom, EquipmentType, EquipmentTypeSchedule
from fascard.api import PricingHistoryAPI
from fascard.utils import TimeHelper
from queuehandler.utils import Aurora

logger = logging.getLogger(__name__)

class PricingHistoryWorker():
    """
    FasCard's location is equivalent to our LaundryRoom object

    location['ID'] is saved to database as fascard_code

    :param job_retries: How many times should the job be executed in case FasCard data is not in sync with local database data

    """
    CYCLE_FIELDS = (
            "laundry_room",
            "equipment_type",
            "detection_date",
            "cycle_type",
        )

    def __init__(self, laundry_group_id, job_retries=None):
        self.laundry_group_id = laundry_group_id
        self.FasCardAPIHandler = PricingHistoryAPI(laundry_group_id)
        if job_retries:
            self.job_retries = job_retries
        elif getattr(settings, 'PRICINGHISTORY_JOB_RETRIES', None):
            self.job_retries = settings.PRICINGHISTORY_JOB_RETRIES
        else:
            self.job_retries = 0
        self.cycle_changes = {}


    # def _get_fascard_locations(self):
    #     return self.FasCardAPIHandler.get_available_locations()

    def _get_formatted_time(self, laundry_room):
        record_time = datetime.utcnow()
        if not laundry_room.time_zone:
            lr_timezone=settings.DEFAULT_LAUNDRYROOM_TIMEZONE
        else:
            lr_timezone = laundry_room.time_zone
        formatted_time = TimeHelper().convert_to_local(record_time, lr_timezone)
        return formatted_time.date()

    def _get_equipment_types(self, location_id):
        return self.FasCardAPIHandler.get_equipment_types(location_id)

    def _get_equipment_pricing(self, equipment_id, location_id):
        return self.FasCardAPIHandler.get_equipment_pricing(equipment_id, location_id)

    def _validate_equipment_type(self, equipment):
        try:
            equipment_class = equipment['EquipClass']
            if equipment_class == 1:
                machine_type = MachineType.WASHER
            elif equipment_class == 2:
                machine_type = MachineType.DRYER
            else:
                machine_type = MachineType.UNKNOWN
            try:
                obj = EquipmentType.objects.get(
                    fascard_id=equipment['ID'],
                    laundry_group=self.laundry_group_id
                )
            except EquipmentType.DoesNotExist:
                data = {
                    'laundry_group_id':self.laundry_group_id,
                    'fascard_id':equipment['ID'],
                    'machine_type':machine_type
                }
                obj = EquipmentType.objects.create(**data)
            if obj.machine_text != equipment['EquipName']:
                obj.machine_text = equipment['EquipName']
                obj.save()
        except Exception as e:
            raise Exception(e)

    def cycle_change_notification(self):
        if len(self.cycle_changes) < 1:
            return
        # formatted_changes = list()
        # for new_cycle, old_cycle in self.cycle_changes:
        #     payload = {}
        #     for f in self.CYCLE_FIELDS:
        #         payload[f] = getattr(new_cycle, f, None)

        #     payload['new_price'] = new_cycle.get_price()
        #     payload['old_price'] = old_cycle.get_price()
        #     formatted_changes.append(payload)
        
        rendered = render_to_string(
            'pricing_change_email_notification.html',
            {
                "formatted_changes" : self.cycle_changes,
            }
        )
        
        message = EmailMessage(
            subject = 'New Cycle Pricing Change',
            body = rendered,
            to = settings.PRICING_CHANGES_EMAIL_LIST,
        )
        message.content_subtype = "html"
        message.send(fail_silently=False) 

    def get_locations(self):
        """
        Fetches the locations list from FasCard API, Sync the locations
        and returns ORM objects of those locations.
        """
        # available_fascard_locations = self._get_fascard_locations(self.laundry_group_id)
        # self._validate_locations(available_fascard_locations, self.laundry_group_id)
        # available_fascard_locations_ids = [location['ID']
        #                                    for location in available_fascard_locations]
        locations = LaundryRoomSync.run(self.laundry_group_id, return_locations=True)
        return locations
        

    def get_location_equipment_types(self, fascard_location_id):
        fascard_equipment_list = self._get_equipment_types(fascard_location_id)
        #self._validate_equipment_types(fascard_equipment_list)
        list(map(self._validate_equipment_type, fascard_equipment_list))
        queryset = EquipmentType.objects.filter(
            fascard_id__in=[equipment['ID'] for equipment in fascard_equipment_list],
            laundry_group=self.laundry_group_id
        )
        return (len(fascard_equipment_list), queryset)

    def save_equipment_pricing(self, pricing_data, equipment_fascard_id, laundry_room, formatted_time):
        cycles_list = pricing_data['Schedule'][0]['Prices']
        pricing_changed = False
        saved = False
        equipment_type = EquipmentType.objects.get(
            fascard_id=equipment_fascard_id,
            laundry_group=self.laundry_group_id
        )
        for cycle in cycles_list:
            cycle_data = {
                'laundry_room' : laundry_room,
                'equipment_type' : equipment_type,
                'cycle_type' : cycle['Name'],
            }
            last_price_history = CustomPriceHistory.objects.filter(**cycle_data).last()
            cycle_data.update({'price' : cycle['OptionPrice']})
            if not last_price_history or last_price_history.price != cycle_data['price']:
                try:
                    cycle_data.update({'detection_date': formatted_time})
                    new_price_history = CustomPriceHistory.objects.create(**cycle_data)
                    pricing_changed = True
                    saved = True
                except Exception as e:
                    raise Exception(e)
                
                try:
                    if last_price_history:
                        if not laundry_room in self.cycle_changes:
                            self.cycle_changes[laundry_room] = {}
                        if not equipment_type in self.cycle_changes[laundry_room]:
                            self.cycle_changes[laundry_room][equipment_type] = []
                        change = (
                            cycle_data['cycle_type'],
                            last_price_history.get_price(),
                            new_price_history.get_price(),
                            #cycle_data['detection_date']                            
                        )
                        self.cycle_changes[laundry_room][equipment_type].append(change)
                        #self.cycle_change_notification(new_price_history, last_price_history)
                except Exception as e:
                    logger.error(
                        f"Failed sending cycle pricing change email notificaton for cycle id: {new_price_history.id} \
                         and exception: {e}"
                    )
        return (saved, pricing_changed)

    @classmethod
    def save_equipment_schedule_pricing(cls, schedule_data, equipment, laundry_room):
        schedules = schedule_data['Schedule']
        for schedule in schedules:
            active = None
            for feature in schedule.get('Features'):
                if feature.get('Name') == 'MachineStart':
                    active = feature.get('Value')
                    break
            assert active is not None
            payload = {
                'start_from' : schedule.get('StartTime'),
                'end_at' : schedule.get('EndTime'),
                'active' : active,
                'equipment_type_id' : equipment.id,
                'laundry_room_id' : laundry_room.id
            }
            obj, created = EquipmentTypeSchedule.objects.get_or_create(**payload)

    def save_pricing_period(self, laundry_room, formatted_time, reason):
        try:
            previous = PricingPeriod.objects.filter(
                laundry_room=laundry_room,
            ).last()
            if previous:
                if previous.start_date <= formatted_time:
                    previous.end_date=formatted_time
                    previous.save()
                else:
                    raise Exception("Dates Inconsistency. Starting date can't be older than ending date")
        except Exception as e:
            raise Exception(e)
        PricingPeriod.objects.create(
            laundry_room=laundry_room,
            start_date=formatted_time,
            reason = reason
        )

    def job(self):
        logger.info("Processing PricingFetch job")
        start_job = time.time()
        try:
            current_aurora_capacity = Aurora.get_aurora_capacity()
            if current_aurora_capacity and current_aurora_capacity < 4:
                Aurora.increase_aurora_capacity(2, sleep_time=120)
        except Exception as e:
            logger.error("Failed increasing aurora capacity for pricing history worker: {}".format(e))
        start_get_locs = time.time()
        laundry_rooms = self.get_locations()
        end_get_locs = time.time()
        logger.info(f"Got locations in PricingFetch job in {end_get_locs - start_get_locs} seconds")
        for laundry_room in laundry_rooms:
            start_get_equip = time.time()
            fascard_equipment_total, laundry_room_equipment_types = self.get_location_equipment_types(laundry_room.fascard_code)
            end_get_equip = time.time()
            logger.info(f"Got equips for room {laundry_room} in PricingFetch job in {end_get_equip - start_get_equip} seconds")
            formatted_time = self._get_formatted_time(laundry_room)
            equipments_changed = []
            start_equip_analysis = time.time()
            for equipment_type in laundry_room_equipment_types:
                pricing_response = self._get_equipment_pricing(
                    equipment_id=equipment_type.fascard_id,
                    location_id=laundry_room.fascard_code
                )
                if pricing_response is None:
                    continue
                saved, pricing_changed = self.save_equipment_pricing(
                    pricing_response,
                    equipment_type.fascard_id,
                    laundry_room,
                    formatted_time
                )
                #TODO: Add self.save_equipment_schedule_pricing
                try:
                    self.save_equipment_schedule_pricing(
                        pricing_response,
                        equipment_type,
                        laundry_room,
                    )
                except:
                    pass
                if pricing_changed: equipments_changed.append(equipment_type)
            end_equip_analysis = time.time()
            logger.info(f"Analyzed equips for room {laundry_room} in PricingFetch job in {end_equip_analysis - start_equip_analysis} seconds")
            if any(equipments_changed):
                equipments_string = ' | | '.join([str(e) for e in equipments_changed])
                self.save_pricing_period(
                    laundry_room,
                    formatted_time,
                    f'Cycle Prices Changed for Equipment Types: {equipments_string}'
                )
        start_notification = time.time()
        self.cycle_change_notification()
        end_notification = time.time()
        logger.info(f"Send PricingFetch notification  in {end_notification - start_notification} seconds")
        end_job = time.time()
        logger.info(f"Executed PricingFetch job in {(start_job-end_job)/60.0} minutes")