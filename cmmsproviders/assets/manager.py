import logging
import time
from typing import Dict, List, Tuple, Sequence, TypeVar
from cmmsproviders.base import AbstractAssetManagerClass
from main.decorators import ProductionCheck
from roommanager.enums import HardwareType
from roommanager.models import LaundryRoom, HardwareBundle, HardwareBundleRequirement, Slot, CardReaderAsset, Machine, AssetMapOut, \
CardReaderMeter, MachineMeter, LaundryRoomMeter

logger = logging.getLogger(__name__)

AssetType = TypeVar("AssetType", CardReaderAsset, Machine)


class BaseAssetManager(AbstractAssetManagerClass):

    def __init__(self):
        self.api = self.API_CLASS()

    def _dict_as_string(self, d) -> str:
        return '--\n'.join([f'{k}: {v}' for k,v in d.items()]) 

    @classmethod
    def _get_hardware_bundles(cls, asset: AssetType):
        p = {cls.field_name_in_hardwarebundle : asset}
        q = HardwareBundle.objects.filter(**p)
        return q

    @classmethod
    def get_related_data(cls, asset: AssetType):
        hardware_bundles = cls._get_hardware_bundles(asset)
        active_bundles = hardware_bundles.filter(is_active = True)
        related_slots = [] #Only one if bundle is Single or two if bundle is Stacked
        if active_bundles:
            for bundle in active_bundles:
                related_slots.append(bundle.slot)
        elif hardware_bundles:
            last_known = hardware_bundles.order_by('-start_time').first()
            hardware_bundles = [last_known]
            related_slots.append(last_known.slot)
        return related_slots, hardware_bundles, active_bundles


    @classmethod
    def _build_asset_name(cls, asset: AssetType, related_slots: Sequence[Slot],
        location: LaundryRoom) -> Tuple[str, str]:
        """
        If there is an outstanding HardwareBundleRequirement the asset is considered orphane
        and the string ORPH is appended. Otherwise, it checks whether the machine is warehoused or
        part of a bundle and construcs its Upkeep equivalent name string.

        Params:
        asset : either a Machine or a CardReader
            Object instance
        related slots: list
            List of object instances of the slots the machine is associated with.
        location : LaundryRoom
            Object instance
        """
        hbr = HardwareBundleRequirement.objects.filter(
            done=False, 
            hardware_id=asset.id,
            hardware_type=cls.hardware_type,
        ).count()
        payload = {cls.field_name_in_hardwarebundle : asset, 'is_active' : True}
        hb = HardwareBundle.objects.filter(**payload).last()
        if hbr:
            status = '-ORPH'
        else:
            if hb and hb.warehouse:
                status = 'WARHS'
            else:
                status = 'BUNDL'

        if status in ['BUNDL', '-ORPH']:
            web_display_names = []
            for slot in related_slots:
                web_display_names.append(getattr(slot, 'web_display_name', ''))
            name_list = [
                '&'.join(web_display_names), 
                getattr(asset, cls.asset_code_field_name, 'UnknownTag'),
                asset.get_asset_model(),
                str(status),
            ]
            location_name = getattr(location, 'display_name', None) or 'UnknownLocation'
            name =  "{}--#".format(location_name)
            name = name + '--'.join(name_list)
        else:
            make_model = asset.get_asset_model()
            asset_code = getattr(asset, cls.asset_code_field_name)
            first_four = asset_code[:4] if asset_code else ''
            name = '--'.join([make_model, first_four, status])
        if isinstance(asset, CardReaderAsset): name = "CardReader: " + name
        return name, status


    #@ProductionCheck
    def create_asset_meter(self, asset: AssetType, asset_payload: Dict) -> None:
        meter_payload = self.build_meter_payload(asset, asset_payload)
        meter_response = self.api.create_asset_meter(meter_payload)
        if 'id' in meter_response:
            meter_obj = getattr(asset, 'meter') #TODO: implement related_name
            setattr(meter_obj, self.provider_meter_id_attr, meter_response.get('id'))
            meter_obj.save()
        else:
            logger.error('Failed Creating Meter for Asset {}. Response" {}'.format(
                asset,
                meter_response
            ))

    def _get_custom_fields_payload(self) -> dict:
        """
        Get an API-ready payload of the custom provider fields associated with the asset.
        """
        raise NotImplementedError

    #@ProductionCheck
    def create_or_update_meter(self, asset: AssetType, asset_payload: dict):
        print ("Trying to update asset's meter")
        print (f"using asset payload: {asset_payload}")
        meter_obj = getattr(asset, 'meter')
        if meter_obj and getattr(meter_obj, self.provider_meter_id_attr):
            print ("asset meter already exists")
            meter_payload = self.build_meter_payload(asset, asset_payload)
            print (f"Updating meter with meter payload: {meter_payload}")
            meter_obj.refresh_from_db()
            meter_response = self.api.update_asset_meter(
                getattr(meter_obj, self.provider_meter_id_attr),
                meter_payload
            )
        else:
            print ("creating asset meter")
            self.create_asset_meter(asset, asset_payload)

    def get_mapout_status(self, asset: AssetType) -> AssetMapOut:
        return AssetMapOut.objects.filter(
            active=True,
            asset_type = self.hardware_type,
            asset_id = asset.id            
        ).order_by('-timestamp').first()

    #@ProductionCheck
    def create_or_update(self, asset: AssetType) -> bool:
        """
        If there is an existing  meter associated with the asset, updates
        the meter. Otherwise, creates a new  meter and associates it with the asset

        The method gets called from signals processors in roommanager.signals

        Params:
        asset: Machine or CardReaderAsset
        """
        print ("maintainx create or update. CMMSPROVIDERS")
        if isinstance(asset, Machine) and getattr(asset, "placeholder", False):
            return False
        print ("GOT ASSET PAYLOAD")
        asset_payload = self.build_asset_payload(asset)
        local_custom_fields = self._get_custom_fields_payload(asset)
        assert asset_payload
        created = False
        asset_payload = self._handle_extra_fields(asset, asset_payload, local_custom_fields)
        if getattr(asset, self.provider_id_attr) is None:
            response = self.api.create_asset(asset_payload)
            if 'id' in response:
                setattr(asset, self.provider_id_attr, response['id'])
                asset.save()
            self.create_or_update_meter(asset, asset_payload)
            #attach images work orders
            if isinstance(asset, Machine):
                self._post_process_machine_creation(asset)
            created = True
        else:
            response = self.api.update_asset(getattr(asset, self.provider_id_attr), asset_payload)
            self.create_or_update_meter(asset, asset_payload)
            #asset pictures updates are handled in save method of Machine Model
        self.post_process(asset)
        return created

    def _fetch_extra_fields(self, asset: AssetType, asset_payload: dict, local_custom_fields: list):
        if getattr(asset, self.provider_meter_id_attr):
            provider_custom_fields = self.api.get_asset(
                getattr(asset, self.provider_meter_id_attr)
            ).get(self.extra_fields_params_name)
            provider_custom_fields = self._format_provider_custom_fields(provider_custom_fields)
        else:
            provider_custom_fields = []
        update_fields = []
        new_fields = []
        if provider_custom_fields:
            provider_fields_db = {}
            for provider_custom_field in provider_custom_fields:
                provider_fields_db[provider_custom_field.get('name')] = provider_custom_field
            for local_custom_field in local_custom_fields:
                if local_custom_field.get('name') in provider_fields_db.keys():
                    field_name = local_custom_field.get('name')
                    provider_field = provider_fields_db.get(field_name)
                    if local_custom_field.get('value') and local_custom_field.get('value') != provider_field.get('value'):
                        field_payload = {
                            'provider_id' : provider_field.get('id'),
                            'local_field' : local_custom_field
                        }
                        update_fields.append(field_payload)
                else:
                    if local_custom_field.get('value'): new_fields.append(local_custom_field)
        else:
            new_fields = local_custom_fields
        return update_fields, new_fields

    @classmethod
    def sync_asset_meters(cls, asset_meter_id: int, asset_type: str) -> None:
        """
        Syncs all upkeep meters associated with either a Machine or CardReader
        """
        api = cls.API_CLASS()
        try:
            if asset_type == HardwareType.MACHINE:
                meter = MachineMeter.objects.get(id=asset_meter_id)
            elif asset_type == HardwareType.CARD_READER:
                meter = CardReaderMeter.objects.get(id=asset_meter_id)
            else:
                return
            api.update_asset_meter_reading(meter, 'transactions_counter', silent_fail=True)
        except Exception as e:
            logger.info("Failed updating meter for {} with id {}. {}".format(asset_type, asset_meter_id,e))

    def post_process(self, asset):
        pass

    @classmethod
    def sync_asset_meters_centralized(cls) -> None:
        """
        Syncs all upkeep meters associated with either a Machine or CardReader using a 60 request per minute
        buffer so we can comply with Maintainx's API rate limit
        """
        api = cls.API_CLASS()
        #get list of both machines and card readers to be updated
        #for/while to process 60 per minute.
        meters = list(MachineMeter.objects.all())
        meters.extend(CardReaderMeter.objects.all())
        start = time.time()
        global_count = 0
        count = 0
        for meter in meters:
            try:
                api.update_asset_meter_reading(meter, 'transactions_counter', silent_fail=True)
            except Exception as e:
                logger.info("Failed updating meter for {} with id {}. {}".format(type(meter), meter.id, e))
            count +=1
            if count == 60:
                logger.info("Hit 60 api calls")
                delta = (time.time() - start)
                if delta < 60:
                    logger.info(f"delta: {delta}")
                    logger.info(f"sleeping for: {65 - delta} seconds")
                    time.sleep(65 - delta)
                    start = time.time()
                count = 0
                logger.info("restarted counters")
            global_count +=1
        logger.info(f"Finished syncing all meters. Global count: {global_count}")

    @classmethod
    def sync_assets_centralized(cls, machines=[], card_readers=[]) -> None:
        """
        Syncs all upkeep meters associated with either a Machine or CardReader using a 60 request per minute
        buffer so we can comply with Maintainx's API rate limit
        """
        #get list of both machines and card readers to be updated
        #for/while to process 60 per minute.
        if not machines: machines = Machine.objects.filter(maintainx_id__isnull=False)
        if not card_readers: card_readers = CardReaderAsset.objects.filter(maintainx_id__isnull=False)
        assets = list(machines)
        assets.extend(card_readers)
        start = time.time()
        global_count = 0
        count = 0
        for asset in assets:
            try:
                cls.create_or_update(asset)
            except Exception as e:
                logger.info("Failed updating asset {}. {}".format(asset, e))
            count +=1
            if count == 60:
                logger.info("Hit 60 api calls")
                delta = (time.time() - start)
                if delta < 60:
                    logger.info(f"delta: {delta}")
                    logger.info(f"sleeping for: {65 - delta} seconds")
                    time.sleep(65 - delta)
                    start = time.time()
                count = 0
                logger.info("restarted counters")
            global_count +=1
        logger.info(f"Finished syncing all assets. Global count: {global_count}")

    @classmethod
    def sync_room_meters(cls, room_meter_id: int) -> None:
        "Syncs all upkeep meters associated with a LaundryRoom"
        api = cls.API_CLASS()
        try:
            meter = LaundryRoomMeter.objects.get(id=room_meter_id)
            api.update_asset_meter_reading(meter, 'dryers_start_counter', silent_fail=True)
        except Exception as e:
            logger.info("Failed updating laundry room meter with id: {}. {}".format(room_meter_id, e))

    @classmethod
    def _build_machine_description(cls, machine: Machine, related_slots: Sequence[Slot], 
        active_bundles: Sequence[HardwareBundle] = None) -> str:
        """
        Builds the description for a Machine's associated asset record in Upkeep

        Params:
        machine : Machine
            Object instance
        related slots: list
            List of object instances of slots the machine is associated with.
        active_bundles:
            List of active HardwareBundle objects that the machine is associated with.
        """
        slots_fascard_ids = []
        slots_fascard_urls = []
        slots_fascard_history_urls = []
        for slot in related_slots:
            if slot:
                slots_fascard_ids.append(slot.slot_fascard_id)
                slots_fascard_urls.append(
                    f"https://admin.fascard.com/86/machine?locid={slot.laundry_room.fascard_code}&machid={slot.slot_fascard_id}"
                )
                slots_fascard_history_urls.append(
                    f"https://admin.fascard.com/86/MachineHist?locationID={slot.laundry_room.fascard_code}&machID={slot.slot_fascard_id}"
                )
        slots_fascard_ids = ', '.join(slots_fascard_ids)
        slots_fascard_urls = ', '.join(slots_fascard_urls)
        slots_fascard_history_urls = ', '.join(slots_fascard_history_urls)
        description = """
            * Fascard Slot(s) ID(s): {}.\n
            * Fascard Slot(s) URL(s): {} \n
            * Slot(s) Status History URL(s): {}\n
            * Machine Admin URL: {} \n""".format(
            slots_fascard_ids,
            slots_fascard_urls,
            slots_fascard_history_urls,
            cls.base_machine_url.format(machine.id)
        )
        if machine.machine_description: description += f"* Machine Description: {machine.machine_description} \n"
        if active_bundles:
            associated_assets_ulrs = list()
            slot_notes = 'Slot Notes: '
            for bundle in active_bundles:
                card_reader = getattr(bundle, 'card_reader', None)
                if card_reader:
                    associated_assets_ulrs.append(cls.get_asset_provider_url(card_reader))
                if getattr(bundle.slot, 'custom_description'):
                    slot_notes += f'Slot ({bundle.slot.slot_fascard_id}): {bundle.slot.custom_description}'
            assets_str = ". ".join(list(map(lambda x: f"\n Associated Asset: {x}", associated_assets_ulrs)))
            description = ". ".join([description, assets_str, slot_notes]) 
        if machine.machine_description:
            description = description + f" Machine Description: {machine.machine_description}"
        return description

    @classmethod
    def get_asset_provider_url(self, asset: AssetType) -> str:
        if getattr(asset, self.provider_id_attr):
            return self.asset_provider_base_url.format(getattr(asset, self.provider_id_attr))
        else:
            return ''