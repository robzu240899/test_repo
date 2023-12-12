import csv
import copy
from revenue.models import LaundryTransaction

from django.db import transaction
from roommanager.enums import MachineType
from roommanager.models import CardReaderAsset, HardwareBundle, LaundryRoom, Machine, Slot
from typing import List
from datetime import datetime, date, timedelta
from dateutil.parser import parse
from .api import *


def initial_setup(self):
    """
    Uses manually created map to match current locations in reporting server
    with current locations in Upkeep
    """

    with open('locationsmap.csv', newline='') as csvfile:
        content = csv.reader(csvfile)
        for row in content:
            print ("Row: {}".format(row))

class UpkeepNongeneratedManager():

    def __init__(self):
        self.api = UpkeepAPI()

    def _get_work_orders(self, upkeep_id):
        from roommanager.models import WorkOrderRecord
        return WorkOrderRecord.objects.filter(asset_upkeep_id=upkeep_id)       

    def get_nongenerated_assets(self, ids_only=True):
        """
        Retrieves a list of assets in Upkeep that were not automatically created by our system
        """
        from roommanager.models import Machine, CardReaderAsset
        response = self.api.get_all_assets(limit=10000)
        response_dict = {}
        for asset in response:
            response_dict[asset.get('id')] = asset
        all_assets_ids = list(response_dict.keys())
        machine_ids = Machine.objects.filter(upkeep_id__isnull=False).values_list('upkeep_id', flat=True)
        machine_ids = list(machine_ids)
        card_reader_ids = CardReaderAsset.objects.filter(upkeep_id__isnull=False).values_list('upkeep_id', flat=True)
        card_reader_ids = list(card_reader_ids)
        system_generated_ids = machine_ids + card_reader_ids
        non_generated_ids = set(all_assets_ids) - set(system_generated_ids)
        non_generated_ids = list(non_generated_ids)
        if ids_only:
            return non_generated_ids
        non_generated_assets = []
        for n_id in non_generated_ids:
            asset_dict = response_dict.get(n_id)
            image_url = asset_dict['image']['url'] if 'image' in asset_dict else None
            non_generated_assets.append({
                'name' : asset_dict.get('name'),
                'upkeep_id': n_id,
                'image' : image_url,
                'work_orders' : self._get_work_orders(n_id)
            })   
        return non_generated_assets
        #return list(non_generated_ids)

    def get_nongenerated_locations(self):
        from roommanager.models import LaundryRoom
        upkeep_locations = self.api.get_all_locations()
        upkeep_locations_ids = set([loc.get('id') for loc in upkeep_locations])
        laundry_rooms = LaundryRoom.objects.filter(upkeep_code__isnull=False).values_list('upkeep_code', flat=True)
        laundry_rooms = set(list(laundry_rooms))
        non_generated_ids = upkeep_locations_ids - laundry_rooms
        return list(non_generated_ids)

    def get_nongenerated_meters(self):
        from roommanager.models import MachineMeter, CardReaderMeter
        all_meters = self.api.get_all_meters(limit=10000)
        all_meter_ids = [meter['id'] for meter in all_meters]
        machine_meters = MachineMeter.objects.filter(upkeep_id__isnull=False).values_list('upkeep_id', flat=True)
        machine_meters_ids = list(machine_meters)
        card_reader_meters = CardReaderMeter.objects.filter(upkeep_id__isnull=False).values_list('upkeep_id', flat=True)
        card_reader_meters_ids = list(card_reader_meters)
        system_generated_ids = machine_meters_ids + card_reader_meters_ids
        return list(set(all_meter_ids) - set(system_generated_ids))
    
    def delete(self, delete_choice):
        response = [0, 0] #Pos0: #of deleted. Pos1: #of non-deleted
        if delete_choice == 'assets':
            ids = self.get_nongenerated_assets()
        elif delete_choice == 'assets_no_extra':
            delete_choice = 'assets'
            assets = self.get_nongenerated_assets(ids_only=False)
            ids = []
            for asset in assets:
                if not asset.get('image') and not asset.get('work_orders'):
                    ids.append(asset.get('upkeep_id'))
        elif delete_choice == 'locations':
            ids = self.get_nongenerated_locations()
        elif delete_choice == 'meters':
            ids = self.get_nongenerated_meters()
        for upkeep_id in ids:
            r = self.api.delete(delete_choice, upkeep_id, silent_fail=True)
            if r['success']: response[0] = response[0] + 1
            else: response[1] = response[1] + 1
        return response


class AssetPicturesMap():
    base_machine_url = 'https://system.aceslaundry.com/admin/roommanager/machine/{}/change/'

    fields_map = {
        'asset_picture' : {
                'title' : 'Attach Asset Picture',
                'description' : 'Asset Picture: {}.',
            },
        'asset_serial_picture' : {
                'title' :  'Attach Serial Picture',
                'description' : 'Asset Serial Picture: {}.',
            }
    }

    def parse_description(self,f):
        assert hasattr(self, 'machine')
        description = self.fields_map.get(f).get('description')
        return description.format(getattr(self.machine, f))

    def parse_work_order(self, machine, fields):
        assert all([f in self.fields_map for f in fields])
        self.machine = machine
        self.title = ' | '.join([self.fields_map.get(f).get('title') for f in fields])
        self.title += '. Or Delete Links from Admin'
        self.description = '\n'.join([self.parse_description(f) for f in fields])
        self.description += ' Machine Link: {}'.format(self.base_machine_url.format(self.machine.id))
        #self.data = copy.deepcopy(self.fields_map.get(field))
        #description = self.data['description']
        #val = getattr(machine, field)
        #self.data['description'] = description.format(val, self.base_machine_url.format(machine.id))


class MeterFixer():

    def _fix_machine_meters(self, assets):
        for asset in assets:
            meter = getattr(asset, 'meter')
            if not meter: continue
            meter.transactions_counter = asset.laundrytransaction_set.filter(transaction_type=100).count()
            meter.save()

    def _fix_card_reader_meters(self, slots):
        for slot in slots:
            hbs = HardwareBundle.objects.filter(slot=slot)
            for hb in hbs:
                cr = hb.card_reader
                if not cr.upkeep_id: continue
                meter = getattr(cr, 'meter')
                q = LaundryTransaction.objects.filter(
                    slot = slot,
                    assigned_local_transaction_time__gte = hb.start_time,
                    transaction_type = 100
                )
                if hb.end_time: q = q.filter(assigned_local_transaction_time__lte = hb.end_time)
                meter.transactions_counter = q.count()
                meter.save()

    def fix_asset_meters(self, assets: List=None):
        if assets:
            self._fix_asset_meters(assets)
        else:
            self._fix_machine_meters(Machine.objects.filter(upkeep_id__isnull=False))
            self._fix_card_reader_meters(Slot.objects.all())            

    def fix_room_meters(self):
        for room in LaundryRoom.objects.filter(upkeep_code__isnull=False):
            meter = getattr(room, 'meter')
            meter.dryers_start_counter = room.laundrytransaction_set.filter(machine__machine_type=MachineType.DRYER, transaction_type=100).counter()
            meter.save()
