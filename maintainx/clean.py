import time
from typing import List
from datetime import date
from fascard.api import FascardApi
from roommanager.models import CardReaderAsset, HardwareBundleRequirement, LaundryRoom, HardwareBundle, \
Machine, MachineSlotMap, WorkOrderRecord, UpkeepUser, MaintainxUser, MaintainxWorkOrderRecord, MaintainxWorkOrderPart
from roommanager.enums import HardwareType
from roommanager.helpers import UploadAssetAttachments
from upkeep.api import UpkeepAPI
from upkeep.manager import LaundryRoomMeterSetUp
from .api import *


class Cleaner():

    def __init__(self) -> None:
        self.api = MaintainxAPI()

    def delete_assets(self):
        base_url = 'https://api.getmaintainx.com/v1/assets'
        next_page_url = base_url
        next_cursor = -1
        while next_cursor is not None:
            if next_cursor > 0: next_page_url = base_url + f"?cursor={next_cursor}"
            response = self.api._get_response('GET', next_page_url)
            assets = response.get('assets')
            for asset in assets:
                time.sleep(1)
                self.api.delete_asset(asset.get('id'))
            next_cursor = response.get('nextCursor')
            if next_cursor : next_cursor = int(next_cursor)
        print ("done")

    def delete_locations(self):
        base_url = 'https://api.getmaintainx.com/v1/locations'
        next_page_url = base_url
        next_cursor = -1
        while next_cursor is not None:
            if next_cursor > 0: next_page_url = base_url + f"?cursor={next_cursor}"
            response = self.api._get_response('GET', next_page_url)
            locations = response.get('locations')
            for location in locations:
                time.sleep(1)
                self.api.delete_location_by_id(location.get('id'))
            next_cursor = response.get('nextCursor')
            if next_cursor : next_cursor = int(next_cursor)
        print ("done")



class WorkOrderSyncer():
    CATEGORY_MAP = {
        'Damage' : 'Damage',
        'None' : None,
        'Electrical' : 'Electrical',
        'Project' : 'Project',
        'Inspection' : 'Inspection',
        'Safety' : 'Safety',
        'Administrative - Orphaned by non-upkeep user' : 'Standard Operating Procedure',
        'Upgrade' : 'Standard Operating Procedure',
        'Administrative' : 'Standard Operating Procedure',
        'Replace' : 'Standard Operating Procedure',
        'machine map-out — mark for pickup' : 'Standard Operating Procedure',
        'machine map-out — en route to Warehouse' : 'Standard Operating Procedure',
        'Preventative' : 'Preventive'
    }

    PRIORITY_LEVEL_MAP = {
        0: "NONE",
        1: "LOW",
        2: "MEDIUM",
        3: "HIGH"
    }

    email_map = {
        'daniel@aceslaundry.com' : 'maintainx@daniel.beachlane.nyc'
    }

    STATUS_MAP = {
        'complete': 'DONE',
        'Complete': 'DONE',
        'On Hold': 'ON_HOLD',
        'onHold': 'ON_HOLD',
        'open': 'OPEN',
        'inProgress': 'IN_PROGRESS',
    }

    def __init__(self) -> None:
        self.skipped_wos = []
        self.API = MaintainxAPI()

    def _fetch_parts_used(self, parts_used) -> List[MaintainxWorkOrderPart]:
        parts = []
        for part in parts_used:
            if not part.name: continue
            maintainx_part = MaintainxWorkOrderPart.objects.filter(name=part.name).first()
            if maintainx_part: parts.append(maintainx_part)
        return parts

    def _fetch_location(self, upkeep_record:WorkOrderRecord):
        try:
            location = LaundryRoom.objects.get(upkeep_code=upkeep_record.upkeep_id)
            if location.maintainx_id:
                return location
            else:
                print ("Location {} for work order {} is not in Maintainx")
                self.skipped_wos.append({'record': upkeep_record, 'reason': 'Location not in Maintainx'})
                return None
        except LaundryRoom.DoesNotExist:
            return None

    def _fetch_assignee(self, assigned_to_upkeep_id):
        try:
            upkeep_user = UpkeepUser.objects.get(upkeep_id=assigned_to_upkeep_id)
        except Exception as e:
            logger.error(f"failed fetching upkeppuser record for id {assigned_to_upkeep_id}: {e}")
            return None
        if upkeep_user.email:
            email = self.email_map.get(upkeep_user.email)
            if not email: email = upkeep_user.email
            try:
                maintainx_user = MaintainxUser.objects.get(email=email)
            except Exception as e:
                logger.error(f"failed fetching maintainx user record for id {email}: {e}")
                maintainx_user = None
        return maintainx_user

    def _sync_wos(self, records=None):
        self.failed_wos = []
        if not records: records = WorkOrderRecord.objects.all()
        for upkeep_wo in records:
            print(f"Id: {upkeep_wo}")
            already_exists = False
            #if upkeep_wo.associated_maintainx_id: already_exists = True
            if upkeep_wo.associated_maintainx_id: continue
            if "Attach Asset Picture" in upkeep_wo.title: continue
            try:
                api_payload = {}
                if upkeep_wo.asset_upkeep_id:
                    asset = None
                    try: asset = Machine.objects.get(upkeep_id=upkeep_wo.asset_upkeep_id)
                    except: pass
                    try: asset = CardReaderAsset.objects.get(upkeep_id=upkeep_wo.asset_upkeep_id)
                    except: pass
                    if asset and getattr(asset, 'maintainx_id', None): 
                        api_payload['assetId'] = int(getattr(asset, 'maintainx_id'))
                if upkeep_wo.category:
                    print (f"upkeep_wo id: {upkeep_wo.id}")
                    print (f"upkeep category: {upkeep_wo.category}")
                    if upkeep_wo.category == "Administrative - Picture Association": continue
                    maintainx_category = self.CATEGORY_MAP[upkeep_wo.category]
                    if maintainx_category:
                        api_payload['categories'] = [maintainx_category]
                if upkeep_wo.title:
                    api_payload['title'] = upkeep_wo.title
                if upkeep_wo.description:
                    maintainx_description = upkeep_wo.description
                    if upkeep_wo.created_date:
                        maintainx_description = maintainx_description + f"*Creation Date: {upkeep_wo.created_date}"
                    if upkeep_wo.completed_date: 
                        maintainx_description = maintainx_description + f"*Completion Date: {upkeep_wo.completed_date}"
                    if upkeep_wo.completed_by_upkeep_username:
                         maintainx_description = maintainx_description + f"*Completed By: {upkeep_wo.completed_by_upkeep_username}"
                    maintainx_description = maintainx_description + f"*Associated Upkeep Work Order id {upkeep_wo.id}"
                    api_payload['description'] = maintainx_description
                if upkeep_wo.location_upkeep_id:
                    location = self._fetch_location(upkeep_wo)
                    if location: api_payload['locationId'] = int(location.maintainx_id)
                if upkeep_wo.priority_level:
                    maintainx_priority = self.PRIORITY_LEVEL_MAP.get(upkeep_wo.priority_level, "NONE")
                    api_payload['priority'] = maintainx_priority
                if upkeep_wo.duedate and upkeep_wo.created_date:
                    api_payload['startDate'] = upkeep_wo.created_date.isoformat()+"Z"
                    api_payload['dueDate'] = upkeep_wo.duedate.isoformat()+"Z"
                #TODO need a maintainx id before saving
                if upkeep_wo.assigned_to_upkeep_id:
                    maintainx_user = self._fetch_assignee(upkeep_wo.assigned_to_upkeep_id)
                    if maintainx_user:
                        api_payload['assignees'] = [{"type": "USER", "id": maintainx_user.maintainx_id}]
                parts_used = upkeep_wo.parts.all()
                if parts_used:
                    maintainx_parts_used = self._fetch_parts_used(parts_used)
                    api_payload['partsUsed'] = []
                    print (f"Parts used: {maintainx_parts_used}")
                    for part_used in maintainx_parts_used:
                        print (f"part used: {part_used}. Maintainx id: {part_used.maintainx_id}")
                        if part_used.maintainx_id:
                            api_payload['partsUsed'].append(
                                {"partId": int(part_used.maintainx_id), "quantityUsed": 1}
                            )
                try:
                    if already_exists:
                        self.API.update_work_order(api_payload, upkeep_wo.associated_maintainx_id)
                    else:
                        api_wo_id = self.API.create_work_order(api_payload, auto=False)
                        if api_wo_id:
                            upkeep_wo.associated_maintainx_id = api_wo_id.get('id')
                            upkeep_wo.save()
                        if upkeep_wo.associated_maintainx_id:
                            if upkeep_wo.status:
                                status = self.STATUS_MAP.get(upkeep_wo.status)
                                self.API.update_work_order_status({'status': status}, upkeep_wo.associated_maintainx_id)
                    time.sleep(3)
                except Exception as e:
                    api_wo_id = None
                    print (f"Exception creating record on Maintainx via API: {e}")
                    logger.error(f"Exception creating record on Maintainx via API: {e}")
                    self.failed_wos.append({'record': upkeep_wo, 'reason': e})
                    continue
            except Exception as e:
                raise e
                #failed_wos.append({'record': upkeep_wo, 'reason': e})
            for f in self.failed_wos: print(f)
            for s in self.skipped_wos: print(s)



class BundleCountUtil():

    def compare_slots_and_bundles(self):
        """
        Gets the number of existing slots in a laundry room and compares it with the number
        of currently active bundles in our system
        """
        api = FascardApi()
        for room in LaundryRoom.objects.filter(is_active=True):
            fascard_id = getattr(room, 'fascard_code')
            if not fascard_id: continue
            active_slots = api.get_machines(fascard_location_id=fascard_id)
            active_bundles = HardwareBundle.objects.filter(is_active=True, location=room)
            print ("{}".format(room))
            print ("Active Slots: {}".format(len(active_slots)))
            print (f"Active Bundles: {active_bundles.count()}")
            print ("\n")

    def find_if_tag_is_machine_and_cardreader(self, room):
        duplicate_tags = []
        for hb in room.hardwarebundle_set.all():
            machine = hb.machine
            try:
                card_reader_record = CardReaderAsset.objects.get(card_reader_tag=machine.asset_code)
                duplicate_tags.append(machine.asset_code)
            except:
                pass

    def bundle_fixer(self, rooms):
        """
        tries to recover valid bundles that were broken by bug
        """
        api = FascardApi()
        for room in rooms:
            slots = room.slot_set.filter(is_active=True)
            for slot in slots:
                print (f"Slot: {slot}")
                latest_bundle = slot.hardwarebundle_set.all().order_by('-start_time').first()
                if not latest_bundle or latest_bundle.is_active: continue
                if latest_bundle.end_time.date() == date(2021, 9, 8) and not latest_bundle.is_active:
                    print ("Latest Bundle: ")
                    print (f"{latest_bundle.start_time} - {latest_bundle.end_time}. Active: {latest_bundle.is_active}. Id: {latest_bundle.id}")
                    latest_msm = slot.machineslotmap_set.all().order_by('-start_time').first()
                    if latest_msm.is_active: continue
                    if not latest_msm.end_time.date() ==  date(2021, 9, 8): continue
                    print (f"latest msm end time: {latest_msm.end_time.date()}")
                    card_reader_hbr = HardwareBundleRequirement.objects.filter(
                        hardware_type=HardwareType.CARD_READER,
                        hardware_id=latest_bundle.card_reader.id).order_by('-timestamp').first()
                    machine_hbr = HardwareBundleRequirement.objects.filter(
                        hardware_type=HardwareType.MACHINE, 
                        hardware_id=latest_bundle.machine.id).order_by('-timestamp').first()
                    if card_reader_hbr:
                        if card_reader_hbr.timestamp:
                            if card_reader_hbr.timestamp.date() ==  date(2021, 9, 8): card_reader_hbr.delete()
                        else:
                            card_reader_hbr.delete()
                    if machine_hbr:
                        if machine_hbr.timestamp:
                            if machine_hbr.timestamp.date() ==  date(2021, 9, 8): machine_hbr.delete()
                        else:
                            machine_hbr.delete()
                    latest_bundle.end_time = None
                    latest_bundle.is_active = True
                    latest_bundle.save()
                    latest_msm.end_time = None
                    latest_msm.is_active = True
                    latest_msm.save()
                    print (f"Updated: {slot}")
                    print("\n")
                    time.sleep(3)
                    #what about machine slot maps?


class ImageSync():

    def run(self):
        rooms = LaundryRoom.objects.filter(upkeep_code__isnull=False, maintainx_id__isnull=False)
        api = UpkeepAPI()
        assets_not_in_maintainx = []
        for room in rooms:
            #if room.display_name in exclude_rooms: continue
            try:
                assets = api.get_all_assets(**{'location':room.upkeep_code})
            except Exception as e:
                print (f"Failed fetching assets for {room}: {e}")
            for asset in assets:
                if asset.get('category').lower() == "card-reader": continue
                try:
                    asset_record = Machine.objects.get(upkeep_id=asset.get('id'))
                except:
                    continue
                if not asset_record or not getattr(asset_record, 'maintainx_id'):
                    assets_not_in_maintainx.append(asset_record)
                    continue
                asset_image_dict = asset.get('image')
                if not asset_image_dict or not asset_image_dict.get('url'): continue
                binary_data = UploadAssetAttachments._read_picture(asset_image_dict.get('url'))
                UploadAssetAttachments.upload_binary_data(
                    asset_record.maintainx_id,
                    binary_data,
                    asset_image_dict.get('name')
                )

