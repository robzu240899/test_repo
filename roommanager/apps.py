from __future__ import unicode_literals
from roommanager import signals
from django.apps import AppConfig
from django.db.models.signals import post_save

class RoommanagerConfig(AppConfig):
    name = 'roommanager'

    def ready(self):
        post_save.connect(signals.sync_to_upkeep_msm_signal, sender='roommanager.MachineSlotMap')
        post_save.connect(signals.sync_to_upkeep_hb, sender='roommanager.HardwareBundle')
        post_save.connect(signals.sync_to_upkeep_hbr_requirement, sender='roommanager.HardwareBundleRequirement')
        post_save.connect(signals.sync_slot_label, sender='roommanager.SlotView')
        #post_save.connect(signals.room_work_order, sender='roommanager.LaundryRoom')
        post_save.connect(signals.orphane_piece_notification, sender='roommanager.OrphanedPieceRequiredAnswer')
        post_save.connect(signals.asset_mapout_notification, sender='roommanager.AssetMapOut')
        post_save.connect(signals.swaptag_notification, sender='roommanager.SwapTagLog')