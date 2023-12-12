import threading
import time
from upkeep.manager import UpkeepAssetManager, UpkeepCardReaderManager
from maintainx.managers.managers import MaintainxMachineManager, MaintainxCardReaderManager
from .models import CardReaderAsset, Machine, LaundryRoom
from .utils import SlotUtils


class AssetSyncingThread(threading.Thread):
    ASSET_TYPE_MANAGER_MAP = {
        Machine: [UpkeepAssetManager, MaintainxMachineManager],
        CardReaderAsset: [UpkeepCardReaderManager, MaintainxCardReaderManager]
    }

    def __init__(self, assets, *args, **kwargs):
        self.assets = assets
        super(UpkeepSyncingThread, self).__init__(**kwargs)

    def sync(self):
        if not self.assets: return
        created_assets = []
        for asset in self.assets:
            managers = self.ASSET_TYPE_MANAGER_MAP.get(type(asset), [])
            for manager_class in managers:
                manager = manager_class()
                created = manager.create_or_update(asset)
                created_assets.append(created)        
        if not any(created_assets): self.assets = []
        self.sync()

    def run(self):
        self.sync()


class AssetSyncingThread(threading.Thread):
    ASSET_TYPE_MANAGERS = {
        'Upkeep': {'machine': UpkeepAssetManager, 'card_reader': UpkeepCardReaderManager},
        'Maintainx': {'machine': MaintainxMachineManager, 'card_reader': MaintainxCardReaderManager}
    }

    def __init__(self, assets, *args, **kwargs):
        self.assets = assets
        super(AssetSyncingThread, self).__init__(**kwargs)

    def sync(self, managers_map:dict):
        if not self.assets:
            return

        created_assets = []
        for asset in self.assets:
            if isinstance(asset, Machine):
                manager = managers_map.get('')
            elif isinstance(asset, CardReaderAsset):
                manager = UpkeepCardReaderManager()
            else:
                raise Exception("Unknown asset type")
            created = manager.create_or_update(asset)
            created_assets.append(created)
        if not any(created_assets):
            self.assets = []
        self.sync()

    def run(self):
        self.sync()

    
class BaseSyncingThread():

    def sync(self, machine_manager=None, card_reader_manager=None):
        time.sleep(3)
        if not self.assets:
            return
        created_assets = []
        for asset in self.assets:
            if isinstance(asset, Machine): manager = machine_manager
            elif isinstance(asset, CardReaderAsset): manager = card_reader_manager
            else: raise Exception("Unknown asset type")
            if manager:
                created = manager.create_or_update(asset)
                created_assets.append(created)
        if not any(created_assets):
            self.assets = []
        self.sync()


class UpkeepSyncingThread(BaseSyncingThread, threading.Thread):

    def __init__(self, assets, *args, **kwargs):
        self.assets = assets
        super(UpkeepSyncingThread, self).__init__(**kwargs)

    def run(self):
        self.sync(machine_manager=UpkeepAssetManager(), card_reader_manager=UpkeepCardReaderManager())


class MaintainxSyncingThread(BaseSyncingThread, threading.Thread):

    def __init__(self, assets, *args, **kwargs):
        self.assets = assets
        super(MaintainxSyncingThread, self).__init__(**kwargs)

    def run(self):
        self.sync(machine_manager=MaintainxMachineManager(), card_reader_manager=MaintainxCardReaderManager())


class SlotLabelCheckThread(threading.Thread):

    def run(self):
        rooms = LaundryRoom.objects.all().select_related()
        SlotUtils.fascard_name_checker(rooms)


# class UpkeepSyncingThread(threading.Thread):

#     def __init__(self, assets, *args, **kwargs):
#         self.assets = assets
#         super(UpkeepSyncingThread, self).__init__(**kwargs)

#     def sync(self):
#         print ("sycing")
#         if not self.assets:
#             return

#         created_assets = []
#         for asset in self.assets:
#             if isinstance(asset, Machine):
#                 upkeep_manager = UpkeepAssetManager()
#             elif isinstance(asset, CardReaderAsset):
#                 upkeep_manager = UpkeepCardReaderManager()
#             else:
#                 raise Exception("Unknown asset type")
#             created = upkeep_manager.create_or_update(asset)
#             created_assets.append(created)
        
#         if not any(created_assets):
#             self.assets = []
#         self.sync()

#     def run(self):
#         print ("ran thread bitch")
#         self.sync()