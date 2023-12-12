from __future__ import unicode_literals
import logging
from datetime import datetime, timedelta
from django.dispatch import receiver
from django.db import transaction
from django.db import models
from django.contrib.auth.models import User, UserManager
from django.core.exceptions import ValidationError
from django.db.models import Q
from fascard.api import FascardApi
from maintainx.api import MaintainxAPI
from roommanager import enums
from revenue import enums as revenue_enums


logger = logging.getLogger(__name__)


'''Represents a group of buildings for scraping purposes'''
class LaundryGroup(models.Model):
    id = models.AutoField(primary_key=True)
    display_name = models.CharField(max_length=200,unique=True)
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=8000)

    class Meta:
        managed = True
        db_table = 'laundry_group'
        ordering = ['display_name']

    def __str__(self):
            return self.display_name

class MaintainxZipCodeRoom(models.Model):
    """
        Used to associate laundry rooms in Maintainx with a Zip code so that employees
        can have an easy time filtering all the buildings in a given part of the city.
    """
    maintainx_id = models.CharField(max_length=20, blank=True, null=True, unique=True)
    display_name = models.CharField(max_length=50, blank=True, null=True)

    def save(self, *args, **kwargs):
        sync_to_maintainx = False
        if not self.pk: sync_to_maintainx = True
        super(MaintainxZipCodeRoom, self).save(*args, **kwargs)
        if sync_to_maintainx:
            ins = MaintainxZipCodeRoom.objects.get(id=self.pk)
            ins.refresh_from_db()
            api = MaintainxAPI()
            response = api.create_location(ins)
            ins.maintainx_id = response.get('id')
            ins.save()

    def __str__(self) -> str:
        return self.display_name


class LaundryRoom(models.Model):
    id = models.AutoField(primary_key=True)
    laundry_group = models.ForeignKey(LaundryGroup, on_delete=models.SET_NULL, blank=True, null=True)
    display_name = models.CharField(max_length=200,unique=True)
    fascard_code = models.IntegerField()
    room_zip_code = models.CharField(max_length=10, blank=True, null=True)
    address = models.CharField(max_length=200, blank=True, null=True)
    latitude = models.CharField(max_length=200, blank=True, null=True)
    longitude = models.CharField(max_length=200, blank=True, null=True)
    upkeep_code = models.CharField(max_length=20, blank=True, null=True)
    maintainx_id = models.CharField(max_length=20, blank=True, null=True)
    maintainx_zipcode_location_parent = models.ForeignKey(MaintainxZipCodeRoom, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    time_zone = models.CharField(max_length=255,choices=enums.TimeZoneType.CHOICES, default=enums.TimeZoneType.EASTERN)
    creation_date = models.DateField(auto_now_add=True, blank=True, null=True)
    test_location = models.BooleanField(default=False)

    class Meta:
        managed = True
        db_table = 'laundry_room'
        unique_together = [('laundry_group','fascard_code')]
        ordering = ['display_name']


    def get_number_machines(self,machine_type=None):
        if machine_type is None:
            return self.slot_set.filter(is_active=True).count()
        else:
            slots = self.slot_set.filter(is_active=True)
            count = 0
            for slot in slots:
                maps = slot.machineslotmap_set.filter(is_active=True,machine__machine_type=machine_type)
                if maps.count()>=1:
                    count += 1
            return count

    @classmethod
    def get_active_rooms(cls, laundry_group_id):
        if laundry_group_id is None:
            return LaundryRoom.objects.filter(is_active=True)
        else:
            return LaundryRoom.objects.filter(is_active=True,laundry_group_id=laundry_group_id)

    def get_billing_group(self):
        extension = self.laundryroomextension_set.all().first()
        return getattr(extension, 'billing_group', None)

    def get_extension(self):
        return self.laundryroomextension_set.all().first()

    def get_units(self):
        ext = self.get_extension()
        return getattr(ext,'num_units',0)

    def get_dryer_starts_count(self):
        return self.laundrytransaction_set.filter(
            machine__machine_type=enums.MachineType.DRYER,
            transaction_type=revenue_enums.TransactionType.VEND
            ).count()

    def save(self, *args, **kwargs):
        new = False
        updated_zip_code = False
        sync_to_maintainx = False
        if self.pk:
            ins = LaundryRoom.objects.get(id=self.pk)
            if self.room_zip_code != ins.room_zip_code: updated_zip_code = True
        else:
            new = True
            if self.room_zip_code: updated_zip_code = True
        if updated_zip_code:
            zip_code_room, created = MaintainxZipCodeRoom.objects.get_or_create(display_name = self.room_zip_code)
            self.maintainx_zipcode_location_parent = zip_code_room
            sync_to_maintainx = True
        super(LaundryRoom, self).save(*args, **kwargs)
        if new:
            try:
                meter = LaundryRoomMeter.objects.create(laundry_room_id=self.pk)
            except Exception as e:
                logger.error(
                    "Could not create room meter for room with id: {}. Exception: {}".format(
                        self.pk,
                        e
                    )
                )
            ins = LaundryRoom.objects.get(id=self.pk)
            fascardapi = FascardApi()
            room_data = fascardapi.get_room(ins.fascard_code)
            ins.address = room_data['Address']
            ins.room_zip_code = room_data['ZipCode']
            ins.latitude = room_data['Latitude']
            ins.longitude = room_data['Longitude']
            ins.save()
        if sync_to_maintainx:
            ins = LaundryRoom.objects.get(id=self.pk)
            payload = {
                'parentId': int(ins.maintainx_zipcode_location_parent.maintainx_id),
                'address' : ins.address
            }
            api = MaintainxAPI()
            api.update_location(ins, **payload)

    def __str__(self):
        return self.display_name


class LaundryRoomMeter(models.Model):
    laundry_room= models.OneToOneField(
        LaundryRoom, 
        on_delete=models.CASCADE, 
        blank=True, 
        null=True, 
        related_name="meter")
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True,blank=True)
    upkeep_id = models.CharField(max_length=50, null=True, blank=True)
    maintainx_id = models.CharField(max_length=50, null=True, blank=True)
    dryers_start_counter = models.PositiveIntegerField(default=0)


class DefaultRoom(models.Model):
    """
        Record used to determine what is the default location to which
        card readers scanned at the office are assigned to by default
    """
    laundry_room = models.ForeignKey(LaundryRoom, on_delete=models.CASCADE, help_text='Default location for card readers')

    def __str__(self):
        return self.laundry_room.display_name


class EquipmentType(models.Model):
    '''Represents the Equipment Object from Fascard'''
    id = models.AutoField(primary_key = True)
    fascard_id = models.IntegerField()
    laundry_group = models.ForeignKey(LaundryGroup, on_delete=models.SET_NULL, blank=True, null=True)
    machine_text = models.TextField()
    machine_type  = models.IntegerField(choices=enums.MachineType.CHOICES)
    equipment_start_check_method = models.CharField(max_length=100,default=enums.SlotType.STANDARD,choices=enums.SlotType.CHOICES)

    def __str__(self):
        return self.machine_text

    def _update_related_slots(self, just_created):
        """
        The equipment_start_check_method is a redundant field equal to slot_type in Slot Model.
        We decided to create it in order to avoid a data migration and big changes to logic.

        This function takes the value from equipment_start_check_method and saves that value
        to all the slots related to this equipment type through the MachineSlotMap.

        """

        equipment_type = EquipmentType.objects.get(id=self.pk)
        machine_slots_map = MachineSlotMap.objects.filter(
            machine__equipment_type=equipment_type
        )
        slots = [machine_slot_map.slot for machine_slot_map in machine_slots_map]
        for slot in slots:
            slot.slot_type = equipment_type.equipment_start_check_method
            slot.save()

    def save(self, *args, **kwargs):
        just_created = self.pk is None
        super(EquipmentType, self).save(*args, **kwargs)
        if not just_created:
            self._update_related_slots(just_created)

    class Meta:
        managed = True
        db_table = 'equipment_type'
        unique_together = [('fascard_id', 'laundry_group')]


class EquipmentTypeSchedule(models.Model):
    laundry_room = models.ForeignKey(LaundryRoom, on_delete=models.SET_NULL, blank=True, null=True, related_name='schedules')
    equipment_type = models.ForeignKey(EquipmentType, on_delete=models.SET_NULL, null=True)
    start_from = models.IntegerField() #Minutes from Sunday midnight
    end_at = models.IntegerField()
    active = models.BooleanField()
    

'''Represents a washer or drier'''
class Machine(models.Model):
    id = models.AutoField(primary_key=True)
    machine_type  = models.IntegerField(choices=enums.MachineType.CHOICES)
    purchase_date = models.DateField(null=True, blank=True)
    make = models.CharField(max_length=200, null=True, blank=True)
    machine_text = models.CharField(max_length=200, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    machine_description = models.CharField(max_length=1000, null=True, blank=True, help_text='This field is synced to Upkeep')
    asset_code = models.CharField(max_length=50, unique=True, null=True, blank=True, help_text='This field is synced to Upkeep and Fascard')
    asset_picture = models.CharField(max_length=1000, null=True, blank=True)
    asset_serial_picture = models.CharField(max_length=1000, null=True, blank=True)
    asset_serial_number = models.CharField(max_length=40, null=True, blank=True, help_text='This field is synced to Upkeep and Fascard')
    asset_factory_model = models.CharField(max_length=40, null=True, blank=True)
    upkeep_id = models.CharField(max_length=50, null=True, blank=True)
    maintainx_id = models.CharField(max_length=50, null=True, blank=True)
    equipment_type = models.ForeignKey(EquipmentType, on_delete=models.SET_NULL, related_name='machine', null=True, blank=True)
    equipment_types = models.ManyToManyField(EquipmentType, related_name='machines_m2m', null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    placeholder = models.BooleanField(default=True)

    class Meta:
        managed = True
        db_table = 'machine'

    def __str__(self):
        if self.machine_text:
            string = self.machine_text
        else:
            string = self.get_basic_name()
            # bundles = self.get_current_bundles()
            # slots = sorted([int(bundle.slot.web_display_name) for bundle in bundles if bundle.slot])
            # slots = [str(slot) for slot in slots]
            # slot_name = "&".join(slots)
            # str_list = [
            #     str(self.get_location()),
            #     str(self.get_machine_type_display()),
            #     str(self.asset_code)
            # ]
            # if slot_name: str_list.insert(1, slot_name)
            # string = '--'.join(str_list)
            #string = f"{self.get_location()} -- {slot} -- {self.get_machine_type_display()}. {self.asset_code}"
        return string

    def get_basic_name(self):
        str_list = [
            str(self.get_location()),
            str(self.get_machine_type_display()),
            str(self.asset_code)
        ]
        string = '--'.join(str_list)
        return '--'.join(str_list)

    def save(self, *args, **kwargs):
        logger.info("Inside Machine's save method")
        # needs_syncing = False
        upload_attachments = False
        if not self.pk:
            new = True
            if any([getattr(self, field) for field in ('asset_picture', 'asset_serial_picture')]): 
                upload_attachments = True
        else:
            logger.info("Machine is not new")
            new = False
            update_pic_fields = list()
            current_instance = Machine.objects.get(pk=self.pk)
            for field in ['asset_picture', 'asset_serial_picture']:
                logger.info(f"Checking field {field} for changes")
                if getattr(current_instance, field) != getattr(self, field):
                    logger.info(f"Field {field} changed")
                    upload_attachments = True
                    if current_instance.upkeep_id: update_pic_fields.append(field)
        super(Machine, self).save(*args, **kwargs)
        if new:
            try:
                meter = MachineMeter.objects.create(machine_id=self.pk)
            except Exception as e:
                logger.error("Could not create machine meter for machine with id: {}. Exception: {}".format(self.pk,e))
        else:
            if len(update_pic_fields) > 0:
                from upkeep.manager import UpkeepAssetManager
                manager = UpkeepAssetManager()
                manager.attach_images_work_oders(self, update_pic_fields)
        self.refresh_from_db()
        if upload_attachments:
            logger.info(f"Trying to upload attachment pics for machine with id: {self.pk}")
            from queuehandler.job_creator import UploadAssetAttachmentsEnqueuer
            UploadAssetAttachmentsEnqueuer.enqueue_job(self.pk)

    def get_full_name(self) -> str:
        self.make_str = self.model_str = self.remaining_str = None
        str_list = ['make_str', 'model_str', 'remaining_str']
        current_bundles = self.get_current_bundles()
        equipment_types = []
        for bundle in current_bundles:
            if bundle.slot and bundle.slot.equipment_type:
                equipment_types.append(bundle.slot.equipment_type)
        for equipment_type in equipment_types:
            machine_text = equipment_type.machine_text.split('--')
            for i, string_name in enumerate(str_list[:len(machine_text)]):
                if getattr(self, string_name) is None:
                    setattr(self, string_name, machine_text[i])
                if str(getattr(self, string_name)).lower() != str(machine_text[i]).lower():
                    current_val = getattr(self, string_name)
                    new_val = '/'.join([current_val, machine_text[i]])
                    setattr(self, string_name, new_val)
        valid_strings = [getattr(self, string) for string in str_list if getattr(self, string) is not None]
        if any(valid_strings):
            if self.machine_type == enums.MachineType.COMBO_STACK:
                valid_strings.append('(ComboStack)')
            return '--'.join(valid_strings)
        else: return ''

    def get_asset_model(self) -> str:
        full_name = self.get_full_name()
        if full_name: return '--'.join(full_name.split('--')[:2])
        else: return ''

    def get_upkeep_asset_url(self):
        asset_base_url = 'https://app.onupkeep.com/#/app/assets/view/{}'
        if self.upkeep_id:
            final_url = asset_base_url.format(self.upkeep_id)
        else:
            final_url = None
        return final_url

    def get_maintainx_asset_url(self):
        asset_base_url = 'https://app.getmaintainx.com/assets/{}'
        if self.maintainx_id:
            final_url = asset_base_url.format(self.maintainx_id)
        else:
            final_url = None
        return final_url

    def get_location(self):
        bundle = self.hardwarebundle_set.all().order_by('-start_time').first()
        if bundle:
            return bundle.location
        else:
            default_room = DefaultRoom.objects.last()
            if default_room: return default_room.laundry_room
            else: return None

    def get_current_bundles(self):
        bundles = self.hardwarebundle_set.filter(is_active=True).order_by('-start_time')
        return bundles

    def get_equipment_types(self):
        bundles = self.get_current_bundles()
        return [bundle.slot.equipment_type for bundle in bundles if bundle.slot and bundle.slot.equipment_type]

    @property
    def current_location(self):
        return self.get_location()


class MachineMeter(models.Model):
    machine= models.OneToOneField(
        Machine, 
        on_delete=models.CASCADE, 
        blank=True, 
        null=True, 
        related_name="meter")
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True,blank=True)
    upkeep_id = models.CharField(max_length=50, null=True, blank=True)
    maintainx_id = models.CharField(max_length=50, null=True, blank=True)
    transactions_counter = models.PositiveIntegerField(default=0)


class MachineMeterReading(models.Model):
    machine = models.ForeignKey(Machine, related_name='meter_readings', on_delete=models.CASCADE)
    current_reading = models.IntegerField()
    picture = models.ImageField(upload_to='meter_readings')
    approved = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)

    @transaction.atomic
    def _update_meter(self, machine, reading):
        meter = machine.meter
        meter.transactions_counter = reading
        meter.save()
        return True

    def save(self, *args, **kwargs):
        updated = False
        if self.pk:
            ins = MachineMeterReading.objects.get(id=self.pk)
            if self.approved and not ins.approved: updated = self._update_meter(self.machine, self.current_reading)
        super(MachineMeterReading, self).save(*args, **kwargs)
        if updated:
            ins = MachineMeterReading.objects.get(id=self.pk)
            ins.refresh_from_db()
            api = MaintainxAPI()
            response = api.update_asset_meter_reading(ins.machine.meter, 'transactions_counter', silent_fail=True)

    def __str__(self):
        return f"{self.machine}. Reading: {self.current_reading}. Timestamp: {self.timestamp}"


class Slot(models.Model):
    """
    Slot.STANDARD:
        Looks at slot history to find LastStart
    Slot.DOUBLE:
        Looks at LastStart attribute to ascertain previous start time for OOO report

    notes: A StackedDryer is not neccesarily a double barrel
    """
    id = models.AutoField(primary_key=True)
    laundry_room = models.ForeignKey(LaundryRoom, on_delete=models.SET_NULL, null=True)
    slot_fascard_id = models.CharField(max_length=100)
    web_display_name = models.CharField(max_length=100)
    clean_web_display_name = models.CharField(max_length=100,default='xxxx')
    idle_cutoff_seconds = models.FloatField(null=True,blank=True)
    is_active = models.BooleanField(default=True)
    last_run_time = models.DateTimeField(null=True,blank=True)
    slot_type = models.CharField(max_length=100,default=enums.SlotType.STANDARD,choices=enums.SlotType.CHOICES)
    custom_description = models.CharField(max_length=100, blank=True, null=True)
    equipment_type = models.ForeignKey(EquipmentType, on_delete=models.SET_NULL, blank=True, null=True)

    def __str__(self):
        if self.laundry_room:
            return '%s: %s: %s' % (self.laundry_room.display_name, self.web_display_name, self.slot_fascard_id)
        else:
            return '%s: %s: ' % (self.web_display_name, self.slot_fascard_id)

    @property
    def verbose_name(self):
        return self.__str__()

    @classmethod
    def get_current_machine(cls,slot):
        if type(slot) is int:
            machine_slot_map = MachineSlotMap.objects.filter(slot_id=slot).order_by('-start_time').first()
        else:
            machine_slot_map = MachineSlotMap.objects.filter(slot=slot).order_by('-start_time').first()
        return machine_slot_map.machine if machine_slot_map else None

    def get_current_card_reader(self):
        hb = HardwareBundle.objects.filter(
            slot=self, is_active=True).order_by('-start_time').first()
        return getattr(hb, "card_reader", None)

    def get_bundle_status(self) -> str:
        hb = HardwareBundle.objects.filter(slot=self, is_active=True).order_by('-start_time').first()
        if hb and hb.warehouse:
            status = 'WARHS'
        elif hb:
            status = 'BUNDL'
        else:
            status = 'ORPH'
        return status

    def get_equipment_type(self,fascard_equipment_id, location):
        try:
            equipment_type = EquipmentType.objects.get(
                fascard_id = fascard_equipment_id,
                laundry_group_id = location.laundry_group_id
            )
            return equipment_type
        except Exception as e:
            raise Exception(
                'Failed to load EquipmentType instance with fascard id: {}. Laundry Room: {}({}). Exception: {}'.format(
                    fascard_equipment_id,
                    location,
                    location.fascard_code,
                    e
                )
            )
    
    def get_current_equipment_type(self):
        location = self.laundry_room
        if not location: return None
        fascard_api = FascardApi(1)
        try:
            slot_response = fascard_api.get_machine(self.slot_fascard_id)
        except:
            return None
        assert 'EquipID' in slot_response
        equipment_id = slot_response['EquipID']
        equipment = self.get_equipment_type(
                equipment_id,
                location
        )
        return equipment


    class Meta:
        managed = True
        unique_together = [('laundry_room','slot_fascard_id')]
        db_table = 'slot'
        ordering = ['laundry_room__display_name','web_display_name']

class SlotView(Slot):
    class Meta:
        proxy = True
        verbose_name = "Slot (With no MachineSlotMap History)"
        verbose_name_plural = "Slots (With no MachineSlotMap History)"


class MachineSlotMap(models.Model):
    id = models.AutoField(primary_key=True)
    slot = models.ForeignKey(Slot, on_delete=models.SET_NULL, null=True)
    machine = models.ForeignKey(Machine, on_delete=models.SET_NULL, null=True)
    is_active = models.BooleanField(default=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True,blank=True)

    class Meta:
        managed = True
        db_table = 'machine_slot_map'

    @transaction.atomic
    def save(self,*args,**kwargs):
        if not self.pk:
            previous = MachineSlotMap.objects.select_for_update().filter(slot=self.slot,is_active=True).exclude(id=self.id)
            previous.update(is_active=False)
        else:
            effectuation_update = kwargs.get('effectuation_update', None)
            if effectuation_update:
                self.effectuation_date_update()
            
        super(MachineSlotMap, self).save(*args, **kwargs)
        # #Automatically create Meter for new Machine in Slot
        # try:
        #     MachineMeter.objects.create(
        #         machine_slot_map_id = self.pk,
        #         start_time = self.start_time,
        #         end_time = self.end_time,
        #     )
        # except Exception as e:
        #     raise (e)

    def __str__(self):
        return '%s (%s) at %s ' % (str(self.machine), getattr(self.slot, 'web_display_name', ''), str(getattr(self.slot, 'laundry_room', '')))


class CardReaderAsset(models.Model):
    condition = models.CharField(
        blank=True,
        null=True,
        choices= enums.CardReaderCondition.CHOICES,
        default = enums.CardReaderCondition.UNKNOWN,
        max_length=20)
    model = models.CharField(blank=True, null=True, max_length=30)
    serial = models.CharField(blank=True, null=True, max_length=50)
    status = models.CharField(
        blank=True, 
        null=True, 
        choices= enums.CardReaderStatus.CHOICES, 
        default=enums.CardReaderStatus.AVAILABLE,
        max_length=20
    )
    card_reader_tag = models.CharField(max_length=50, unique=True)
    first_scan_time = models.DateTimeField(auto_now_add=True)
    last_scan_time = models.DateTimeField(auto_now=True)
    upkeep_id = models.CharField(max_length=50, null=True, blank=True)
    maintainx_id = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return "{}. (Model: {})".format(self.card_reader_tag, self.model)

    def get_location(self):
        bundle = self.hardwarebundle_set.all().order_by('-start_time').first()
        if bundle:
            return bundle.location
        else:
            return DefaultRoom.objects.last().laundry_room

    def get_current_bundle(self):
        bundle = self.hardwarebundle_set.filter(is_active=True).order_by('-start_time').first()
        return bundle

    def get_asset_model(self, *args, **kwargs):
        return self.model or 'Unknown Model'

    def save(self, *args, **kwargs):
        if not self.pk:
            new = True
        else:
            new = False
        super(CardReaderAsset, self).save(*args, **kwargs)
        if new:
            try:
                meter = CardReaderMeter.objects.create(
                    card_reader_id=self.pk
                )
            except Exception as e:
                logger.error(
                    "Could not create cardreader meter for asset with id: {}. Exception: {}".format(
                        self.pk,
                        e
                    )
                )

    def get_upkeep_asset_url(self):
        asset_base_url = 'https://app.onupkeep.com/#/app/assets/view/{}'
        if self.upkeep_id:
            final_url = asset_base_url.format(self.upkeep_id)
        else:
            final_url = None
        return final_url

    def get_maintainx_asset_url(self):
        asset_base_url = 'https://app.getmaintainx.com/assets/{}'
        if self.maintainx_id:
            final_url = asset_base_url.format(self.maintainx_id)
        else:
            final_url = None
        return final_url


class CardReaderMeter(models.Model):
    card_reader = models.OneToOneField(
        CardReaderAsset, on_delete=models.CASCADE, blank=True, null=True, related_name='meter')
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True,blank=True)
    upkeep_id = models.CharField(max_length=50, null=True, blank=True)
    maintainx_id = models.CharField(max_length=50, null=True, blank=True)
    transactions_counter = models.PositiveIntegerField(default=0)


# class CardReaderMeter(models.Model):
#     card_reader = models.OneToOneField(
#         CardReaderAsset,
#         on_delete=models.CASCADE,
#         blank=True,
#         null=True,
#         related_name='meter')
#     start_time = models.DateTimeField(auto_now_add=True)
#     end_time = models.DateTimeField(null=True,blank=True)
#     upkeep_id = models.CharField(max_length=50, null=True, blank=True)
#     transactions_counter = models.PositiveIntegerField(default=0)

class MachineAttachmentTracker(models.Model):
    attachment_maintainx_url = models.CharField(max_length=300)
    machine = models.ForeignKey(Machine, on_delete=models.SET_NULL, null=True, blank=True)
    url = models.CharField(max_length=1000, null=True, blank=True)
    decision = models.CharField(choices=enums.AssetPicturesChoice.CHOICES, default=enums.AssetPicturesChoice.NON_APPLICABLE, max_length=20, blank=True, null=True)
    #TODO:  This may help keep track of the updates


class TechnicianEmployeeProfile(models.Model):
    full_name = models.CharField(max_length=200)
    fascard_user = models.ForeignKey('revenue.FascardUser', on_delete=models.SET_NULL, blank=True, null=True, limit_choices_to={'is_employee': True})
    codereadr_username = models.CharField(max_length=50)
    upkeep_id = models.CharField(max_length=50, blank=True, null=True)
    maintainx_id = models.CharField(max_length=50, blank=True, null=True)
    maintainx_user = models.ForeignKey('roommanager.MaintainxUser', on_delete=models.SET_NULL, blank=True, null=True)
    language = models.CharField(max_length=20, choices=enums.LanguageChoices.CHOICES, default=enums.LanguageChoices.ENGLISH)
    notifications_email = models.EmailField()

    def __str__(self):
        return self.full_name + ': ' + self.notifications_email


class HardwareBundlePairing(models.Model):
    """
    Represents the attempt to pair a hardware bundle and saves information related to the scan
    """
    tech_employee = models.ForeignKey(
        TechnicianEmployeeProfile,
        on_delete=models.SET_NULL,
        blank=True,
        null=True)
    codereadr_username = models.CharField(max_length=60, blank=True, null=True) #In case no tech userprofile was found
    submission_id = models.CharField(max_length=60, blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    card_reader_code = models.CharField(max_length=100, blank=True, null=True) #Representation of Slot
    slot = models.ForeignKey(Slot, on_delete=models.SET_NULL, blank=True, null=True)
    asset_code = models.CharField(max_length=100) #Representation of a Machine
    asset_picture = models.CharField(max_length=1000, null=True, blank=True)
    asset_picture_decision = models.CharField(choices=enums.AssetPicturesChoice.CHOICES, default=enums.AssetPicturesChoice.NON_APPLICABLE, max_length=20, blank=True, null=True)
    asset_serial_picture = models.CharField(max_length=1000, null=True, blank=True)
    asset_serial_picture_decision = models.CharField(choices=enums.AssetPicturesChoice.CHOICES, default=enums.AssetPicturesChoice.NON_APPLICABLE, max_length=20, blank=True, null=True)
    data_matrix_string = models.CharField(max_length=40, null=True, blank=True)
    asset_serial_number = models.CharField(max_length=40, null=True, blank=True)
    asset_factory_model = models.CharField(max_length=40, null=True, blank=True)
    machine_description = models.TextField(max_length=200, null=True, blank=True)
    valid = models.BooleanField(default=False) 
    location = models.ForeignKey(LaundryRoom, on_delete=models.SET_NULL, blank=True, null=True)
    scan_type = models.CharField(max_length=40, choices=enums.BundleType.CHOICES, blank=True, null=True)
    file_transfer_type = models.CharField(max_length=20, blank=True, null=True)
    file_transfer_upload_path = models.CharField(max_length=20, blank=True, null=True)
    warehouse = models.ForeignKey(LaundryRoom, on_delete=models.SET_NULL, blank=True, null=True, related_name='pairing_warehouse')
    combostack = models.BooleanField(default=False)
    dual_pocket_new_bundle = models.BooleanField(default=False)
    slot_being_replaced = models.CharField(max_length=20, blank=True, null=True)
    err_msg = models.CharField(max_length=200, blank=True, null=True)
    notify = models.BooleanField(default=False)
    notification_sent = models.BooleanField(default=False)

    def format_new_bundle(self):
        """
        Retrieves bundle members (Slot, Machine, Card Reader) in a data structure suitable
        for representation on HTML template report of Outstanding Bundle Changes
        """
        return [
           {
               'name' : 'Machine',
               'obj' : self.asset_code,
               'associated_change_type' : 'MACHINE_CHANGE',
               'asset_type' : enums.HardwareType.MACHINE
            },
           {
               'name' : 'Card Reader',
               'obj' : self.card_reader_code,
               'associated_change_type' : 'CARD_READER_CHANGE',
               'asset_type' : enums.HardwareType.CARD_READER
            },
            {
                'name' : 'Slot',
                'obj' : self.slot,
                'associated_change_type' : 'SLOT_CHANGE',
                'asset_type' : enums.HardwareType.SLOT
            }
        ]


class HardwareBundleRequirement(models.Model):
    """
    Records all the triple-scans that techs need to do after a machine, slot or card reader
    has became orphane
    """
    message = models.TextField()
    hardware_type = models.CharField(max_length=100,choices=enums.HardwareType.CHOICES)
    hardware_id = models.IntegerField()
    done = models.BooleanField(default=False)
    assigned_technician = models.ForeignKey(TechnicianEmployeeProfile, on_delete=models.SET_NULL, blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    def save(self, *args, **kwargs):
        new = False
        if not self.pk: new=True
        super(HardwareBundleRequirement, self).save(*args, **kwargs)
        if new:
            OrphanedPieceRequiredAnswer.objects.create(hbr=self)


class OrphanedPieceRequiredAnswer(models.Model):
    hbr = models.ForeignKey(HardwareBundleRequirement, on_delete=models.SET_NULL, null=True)
    answer = models.CharField(
        max_length=50,
        choices=enums.OrphanedPieceAnswerChoices.CHOICES,
        blank=True,
        null=True
    )


class HardwareBundle(models.Model):
    """
    Represent the actual relationship between three pieces of hardware:

    -Slot, Machine and CardReader
    """
    slot = models.ForeignKey(Slot, on_delete=models.SET_NULL, blank=True, null=True)
    machine = models.ForeignKey(Machine, on_delete=models.SET_NULL, blank=True, null=True)
    card_reader = models.ForeignKey(CardReaderAsset, on_delete=models.SET_NULL, blank=True, null=True)
    location = models.ForeignKey(LaundryRoom, on_delete=models.SET_NULL, blank=True, null=True)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    warehouse = models.ForeignKey(LaundryRoom, on_delete=models.SET_NULL, blank=True, null=True, related_name='warehouse')
    bundle_type = models.CharField(
        max_length=40,
        choices=enums.BundleType.CHOICES,
        default=enums.BundleType.SINGLE, 
        blank=True,
        null=True
    )

    def format_bundle(self):
        return [
           {
               'name' : 'Machine',
               'obj' : getattr(self.machine, 'asset_code', None),
               'associated_change_type' : 'MACHINE_CHANGE',
               'asset_type' : enums.HardwareType.MACHINE
            },
           {
               'name' : 'Card Reader',
               'obj' : getattr(self.card_reader, 'card_reader_tag', None),
               'associated_change_type' : 'CARD_READER_CHANGE',
               'asset_type' : enums.HardwareType.CARD_READER
            },
            {
                'name' : 'Slot',
                'obj' : self.slot,
                'associated_change_type' : 'SLOT_CHANGE',
                'asset_type' : enums.HardwareType.SLOT
            }
        ]
        

    def save(self, *args, **kwargs):
        if not self.pk:
            creation = True
        else:
            creation = False
        super(HardwareBundle, self).save(*args,**kwargs)
        hardware_type_map = (
            ('slot', enums.HardwareType.SLOT),
            ('machine', enums.HardwareType.MACHINE),
            ('card_reader', enums.HardwareType.CARD_READER),

        )
        if creation:
            for piece in hardware_type_map:
                piece_instance = getattr(self, piece[0])
                if piece_instance:
                    hbr = HardwareBundleRequirement.objects.filter(
                        done=False, 
                        hardware_id=piece_instance.id,
                        hardware_type=piece[1]
                    ).first()
                    if hbr:
                        hbr.done = True
                        hbr.save()


class HardwareBundleChangesLog(models.Model):
    hardware_type = models.CharField(
        max_length = 30,
        choices=enums.HardwareType.CHOICES,
        blank=True,
        null=True)
    old_piece_hardware_id = models.IntegerField(blank=True, null=True)
    new_piece_hardware_id = models.IntegerField(blank=True, null=True)
    old_bundle = models.ForeignKey(HardwareBundle, on_delete=models.SET_NULL, null=True, related_name='old_bundle')
    new_bundle = models.ForeignKey(HardwareBundle, on_delete=models.SET_NULL, null=True, related_name='new_bundle')
    technician = models.ForeignKey(TechnicianEmployeeProfile, on_delete=models.SET_NULL, blank=True, null=True)
    location = models.ForeignKey(LaundryRoom, on_delete=models.SET_NULL, related_name="hardware_bundle_changes", blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    change_type = models.CharField(max_length=30, choices=enums.ChangeType.CHOICES)

    def __get_hardware_piece(self, id: int):
        hardware_piece = None
        if self.hardware_type == enums.HardwareType.SLOT:
            try:
                hardware_piece = Slot.objects.get(id=id)
            except:
                pass
        elif self.hardware_type == enums.HardwareType.CARD_READER:
            try:
                hardware_piece = CardReaderAsset.objects.get(id=id)
            except:
                pass
        elif self.hardware_type == enums.HardwareType.MACHINE:
            try:
                hardware_piece = Machine.objects.get(id=id)
            except:
                pass
        return hardware_piece        

    def get_old_piece(self):
        if not self.old_piece_hardware_id: return None
        return self.__get_hardware_piece(self.old_piece_hardware_id)

    def get_new_piece(self):
        if not self.new_piece_hardware_id: return None
        return self.__get_hardware_piece(self.new_piece_hardware_id)


class BaseApproval(models.Model):
    approved = models.BooleanField(default=False)
    rejected = models.BooleanField(default=False)
    rejected_timestamp = models.DateTimeField(blank=True, null=True)
    approved_timestamp = models.DateTimeField(blank=True, null=True)
    asset_picture_decision = models.CharField(choices=enums.AssetPicturesChoice.CHOICES, default=enums.AssetPicturesChoice.NON_APPLICABLE, max_length=20, blank=True, null=True)
    asset_serial_picture_decision = models.CharField(choices=enums.AssetPicturesChoice.CHOICES, default=enums.AssetPicturesChoice.NON_APPLICABLE, max_length=20, blank=True, null=True)
    machine_description = models.CharField(max_length=200, null=True, blank=True)
    serial_number_not_available = models.BooleanField(default=False, help_text='Check if Serial # NOT Available')
    decision_maker = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,blank=True)
    superseded_by = models.ForeignKey('self', on_delete=models.SET_NULL, blank=True, null=True)
    scan_pairing = models.ForeignKey(HardwareBundlePairing, on_delete=models.SET_NULL, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    associated_work_order_maintainx_id = models.CharField(max_length=20, null=True, blank=True)

    class Meta:
        abstract = True
    
    def get_current_machine(self):
        try:
            machine = Machine.objects.get(asset_code=self.scan_pairing.asset_code)
        except Machine.DoesNotExist:
            machine = None
        return machine


class BundleChangeApproval(BaseApproval):
    previous_bundle = models.ForeignKey(HardwareBundle, on_delete=models.SET_NULL, blank=True, null=True)
    change_type = models.CharField(max_length=50, choices=enums.ChangeType.CHOICES, blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.pk:
            ins = BundleChangeApproval.objects.get(id=self.pk)
            if not ins.approved and self.approved:
                self.approved_timestamp = datetime.now()
            if not ins.rejected and self.rejected:
                self.rejected_timestamp = datetime.now()
        super(BundleChangeApproval, self).save(*args, **kwargs)


class AssetUpdateApproval(BaseApproval):
    bundle = models.ForeignKey(HardwareBundle, on_delete=models.SET_NULL, blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.pk:
            ins = AssetUpdateApproval.objects.get(id=self.pk)
            if not ins.approved and self.approved:
                self.approved_timestamp = datetime.now()
            if not ins.rejected and self.rejected:
                self.rejected_timestamp = datetime.now()
        super(AssetUpdateApproval, self).save(*args, **kwargs)


class ValidTag(models.Model):
    tag_string = models.CharField(max_length=50, unique=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['tag_string',]),
        ]

    def __str__(self):
        return self.tag_string


class AssetMapOut(models.Model):
    asset_type = models.CharField(max_length=100, choices=enums.HardwareType.CHOICES)
    asset_id = models.IntegerField()
    status = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)
    approved = models.BooleanField(default=False)
    assigned_technician = models.ForeignKey(TechnicianEmployeeProfile, on_delete=models.SET_NULL, blank=True, null=True)
    assigned_user = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)
    current_asset_bundle = models.ForeignKey(HardwareBundle, on_delete=models.SET_NULL, blank=True, null=True)
    scan_asset_tag = models.TextField(blank=True, null=True)
    needs_rescanning = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.asset_type}. Id: {self.asset_id}. Status: {self.status}"


class WorkOrderPart(models.Model):
    upkeep_id = models.CharField(max_length=30, blank=True, null=True)
    serial = models.CharField(max_length=30, blank=True, null=True)
    details = models.CharField(max_length=200, blank=True, null=True)
    quantity = models.IntegerField(default=0)
    name = models.CharField(max_length=30, blank=True, null=True)
    area = models.CharField(max_length=30, blank=True, null=True)
    created_by_upkeep_id = models.CharField(max_length=30, blank=True, null=True)
    created_date = models.DateTimeField(blank=True, null=True)
    updated_date = models.DateTimeField(blank=True, null=True)


class BaseUser(models.Model):
    first_name = models.CharField(max_length=30, blank=True, null=True)
    last_name = models.CharField(max_length=30, blank=True, null=True)
    role = models.CharField(max_length=30, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)

    class Meta:
        abstract = True


class MaintainxUser(BaseUser):
    maintainx_id = models.CharField(max_length=20, blank=True, null=True)
    removed_from_organization = models.BooleanField(default=False)

    def __str__(self): return " ".join([self.first_name, self.last_name])


class UpkeepUser(BaseUser):
    upkeep_id = models.CharField(max_length=20, blank=True, null=True)


class BaseWorkOrderRecord(models.Model):
    category = models.CharField(max_length=50, blank=True, null=True)
    completed_date = models.DateTimeField(blank=True, null=True)
    created_date = models.DateTimeField(blank=True, null=True)
    description = models.TextField(max_length=2000, blank=True, null=True)
    status = models.CharField(max_length=30, blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    title = models.CharField(max_length=500, blank=True, null=True)
    updated_date = models.DateTimeField(blank=True, null=True)
    duedate = models.DateTimeField(blank=True, null=True)

    class Meta:
        abstract = True

#Upkeep
class WorkOrderRecord(BaseWorkOrderRecord):
    asset_upkeep_id = models.CharField(max_length=30, blank=True, null=True)
    assigned_by_upkeep_id = models.CharField(max_length=30, blank=True, null=True)
    assigned_by_upkeep_username = models.CharField(max_length=30, blank=True, null=True)
    assigned_to_upkeep_id = models.CharField(max_length=30, blank=True, null=True)
    assigned_to_upkeep_username = models.CharField(max_length=30, blank=True, null=True)
    completed_by_upkeep_id = models.CharField(max_length=30, blank=True, null=True)
    completed_by_upkeep_username = models.CharField(max_length=30, blank=True, null=True)
    location_upkeep_id = models.CharField(max_length=30, blank=True, null=True)
    priority_level = models.IntegerField(blank=True, null=True)
    upkeep_id = models.CharField(max_length=30, unique=True)
    work_order_no = models.CharField(max_length=10, blank=True, null=True)
    parts = models.ManyToManyField(WorkOrderPart)
    available_in_api = models.BooleanField(default=True)
    associated_maintainx_id = models.CharField(max_length=30, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['asset_upkeep_id']),
        ]

    def __str__(self):
        return f"{self.title} - {self.upkeep_id}"


class MaintainxWorkOrderPart(models.Model):
    maintainx_id = models.CharField(max_length=30, blank=True, null=True)
    name = models.CharField(max_length=100, blank=True, null=True)
    area = models.CharField(max_length=100, blank=True, null=True)
    description = models.CharField(max_length=200, blank=True, null=True)
    available_quantity = models.IntegerField(blank=True, null=True)
    barcode = models.CharField(max_length=30, blank=True, null=True)
    copy_on_recurring = models.CharField(max_length=30, blank=True, null=True)
    minimum_quantity = models.CharField(max_length=30, blank=True, null=True)
    unit_cost = models.IntegerField(blank=True, null=True)
    start_date = models.DateTimeField(blank=True, null=True)


class MaintainxWorkOrderRecord(BaseWorkOrderRecord):
    """
    assigneds_ids stores a list of ids as a string
    category stores a list of ids as a string
    """
    asset_maintainx_id = models.CharField(max_length=30, blank=True, null=True)
    assigned_by_id = models.CharField(max_length=30, blank=True, null=True)
    assignees_ids = models.CharField(max_length=30, blank=True, null=True)
    assignees = models.ManyToManyField(MaintainxUser)
    completed_by_id = models.CharField(max_length=30, blank=True, null=True)
    location_maintainx_id = models.CharField(max_length=30, blank=True, null=True)
    priority_level = models.CharField(max_length=50, blank=True, null=True)
    maintainx_id = models.CharField(max_length=30, unique=True)
    parts = models.ManyToManyField(MaintainxWorkOrderPart)
    associated_upkeep_wo = models.ForeignKey(WorkOrderRecord, on_delete=models.SET_NULL, null=True) 


class SwapTagLog(models.Model):
    current_tag = models.CharField(max_length=50)
    new_tag = models.CharField(max_length=50)
    tech_username = models.CharField(max_length=50, blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    approved = models.BooleanField(default=False)
    approved_timestamp = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return "{} -> {}".format(self.current_tag, self.new_tag)

    def save(self, *args, **kwargs):
        if self.pk:
            ins = SwapTagLog.objects.get(id=self.pk)
            if not ins.approved and self.approved:
                self.approved_timestamp = datetime.now()
        super(SwapTagLog, self).save(*args, **kwargs)

    def get_obj(self, *args, **kwargs):
        card_reader = CardReaderAsset.objects.filter(card_reader_tag=self.current_tag).first()
        machine = Machine.objects.filter(asset_code=self.current_tag).first()
        return card_reader if card_reader else machine

    def get_obj_type(self, *args, **kwargs):
        return type(self.get_obj()).__name__

# class FailedSlotMachinePairing():
#     submission_id = models.CharField(blank=True, max_length=60, null=True)
#     err_msg = models.CharField(blank=True, max_length=200, null=True)
#     notification_sent = models.BooleanField(default=False)
#     timestamp = models.DateTimeField(auto_now_add=True)
#     notification_sent = models.BooleanField(default=False)
#     tech_employee = models.ForeignKey(TechnicianEmployeeProfile, blank=True, null=True, on_delete=models.SET_NULL)

#     def __str__(self):
#         return 'Date: {}. SubmissionID: {}'.format(self.timestamp, self.submission_id)

#     def notify_tech(self):
#         if self.tech_employee:
#             #to_list = settings.OUT_OF_ORDER_TO_LIST + [self.tech_employee.notifications_email]
#             to_list = [self.tech_employee.notifications_email]
#             to_name = self.tech_employee.full_name
#             from_email = settings.DEFAULT_FROM_EMAIL
#             subject = 'Slot-Machine Failed Pairing'
#             body = 'An slot-machine pairing process failed with error: {}.\n SubmissionID: {}.\n Date: {}'.format(
#                 self.err_msg,
#                 self.submission_id,
#                 self.timestamp
#             )
#             email = EmailMessage(subject, body, from_email, to_list)
#             email.send(fail_silently=False)
#             self.notification_sent = True
#             self.save()

#     def save(self, *args, **kwargs):
#         super(FailedSlotMachinePairing, self).save(*args, **kwargs)
#         if not self.notification_sent:
#             self.notify_tech()

# # class Person(models.Model):
#     id = models.AutoField(primary_key=True)
#     laundry_room = models.ForeignKey(LaundryRoom)
#     first_name = models.CharField(max_length=80,null=True,blank=True)
#     last_name = models.CharField(max_length=80,null=True,blank=True)
#
#     class Meta:
#         managed = True
#         unique_together = [['laundry_room','first_name','last_name']]
#         db_table = 'person'
#
#
#     def __unicode__(self):
#         return '%s, %s' % (self.last_name, self.first_name)
#
#
# class PersonAlias(models.Model):
#     id = models.AutoField(primary_key=True)
#     laundry_room = models.ForeignKey(LaundryRoom,null=True,blank=True)
#     person = models.ForeignKey(Person,null=True,blank=True)
#     score = models.FloatField(null=True,blank=True)
#     first_name = models.CharField(max_length=80,null=True,blank=True)
#     last_name = models.CharField(max_length=80,null=True,blank=True)
#     last_four = models.CharField(max_length=20,null=True,blank=True)
#     source = models.CharField(max_length=20,choices=enums.PersonAliasSource.CHOICES)
#
#     class Meta:
#         managed = True
#         unique_together = [['laundry_room','first_name','last_name','last_four']]
#         db_table = 'person_alias'
#
#

class InDbConfigType(models.Model):
    id = models.AutoField(primary_key=True)
    display_name = models.CharField(max_length=200,unique=True)

    class Meta:
        managed = True
        db_table = 'in_db_config_type'



class InDbConfig(models.Model):
    id = models.AutoField(primary_key=True)
    in_db_config_type = models.ForeignKey(InDbConfigType, on_delete=models.CASCADE, unique=True)
    integer_value = models.IntegerField(null=True,blank=True)
    float_value = models.FloatField(null=True,blank=True)
    boolean_value = models.NullBooleanField()
    string_field = models.CharField(max_length=200,null=True,blank=True)

    class Meta:
        managed = True
        db_table = 'in_db_config'



    def clean(self):
        num_filled_in = 0
        if self.integer_value is not None:
            num_filled_in += 1
        if self.float_value  is not None:
            num_filled_in += 1
        if self.boolean_value is not None:
            num_filled_in += 1
        if self.string_field  is not None:
            num_filled_in += 1
        if num_filled_in != 1:
            raise ValidationError(("Exactly one value field (int,float,boolean,string) must be filled in."))

    def save(self,*args,**kwargs):
        self.clean()
        super(InDbConfig,self).save(*args,**kwargs)


    @classmethod
    def get_value(cls,display_name):
        cfg = InDbConfig.objects.get(in_db_config_type__display_name=display_name)
        if cfg.integer_value is not None:
            return cfg.integer_value
        elif cfg.float_value is not None:
            return cfg.float_value
        elif cfg.boolean_value is not None:
            return cfg.boolean_value
        elif cfg.string_field is not None:
            return cfg.string_field
        else:
            raise Exception("No value field filled in for InDbConfig object")