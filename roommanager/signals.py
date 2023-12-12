"""
Machine asset syncing is controlled with a signal on MachineSlotMap.
This is done to cover the possible case in which a Machine becomes orphaned
by means different to the scanning app

CardReader asset syncing is controlled with a signal on HardwareBundle

Orphane work orders are created for either type of asset with a signal on HardwareBundleRequirement
"""


import logging
import time
from django.db import transaction
from datetime import datetime
from fascard.api import FascardApi
from upkeep.api import UpkeepAPI
from .enums import HardwareType
from .utils import OrphaneWorkOrder, OrphanePieceNotification, AssetMapOutEmailNotification, SwapTagEmailNotification, SlotUtils


logger = logging.getLogger(__name__)

def process_machine_thread(obj):
    from .threads import UpkeepSyncingThread, MaintainxSyncingThread

    if transaction.get_connection().in_atomic_block:
        transaction.on_commit(lambda: UpkeepSyncingThread(obj).start())
        time.sleep(3)
        transaction.on_commit(lambda: MaintainxSyncingThread(obj).start())
    else:
        UpkeepSyncingThread(obj).start()
        time.sleep(3)
        MaintainxSyncingThread(obj).start()

def update_slot(obj, label, serial_number, factory_model):
    api = FascardApi(1)
    r = api.update_slot_label(obj.slot_fascard_id, label)
    if serial_number is not None:
        api.edit_machine(
            obj.slot_fascard_id,
            {'SerialNumber' : str(serial_number), 'Model': factory_model}
        )
    return True

def process_slot_thread(obj, label, serial_number, factory_model):
    logger.info(f"Changing slot's {obj} label to: {label}")
    if transaction.get_connection().in_atomic_block:
        transaction.on_commit(lambda: update_slot(obj, label, serial_number, factory_model))
    else:
        update_slot(obj, label, serial_number, factory_model)
        
def _sync_slot_label(slot, skip_machine=False):
    slot_data = SlotUtils.fetch_slot_sync_data(slot)
    process_slot_thread(
        slot,
        slot_data.get('label'),
        slot_data.get('serial_number'),
        slot_data.get('factory_model')
    )
    machine = slot_data.get('machine')
    if machine and not skip_machine:
        process_machine_thread([machine])
    return True

def sync_slot_label(sender, instance, created, **kwargs):
    """signal processor"""
    return _sync_slot_label(instance)


def sync_to_upkeep_msm_signal(sender, instance, created, **kwargs):
    """
    If a new MachineSlotMap is created it means that an SlotChange
    or a MachineChange must have happened in the Scanning app.
    Thus, we use this signal to create_or_update the machine associated.
    """
    if not created: return
    #created = upkeep_manager.create_or_update(instance.machine)
    slot = instance.slot
    process_machine_thread([instance.machine])
    _sync_slot_label(slot, skip_machine=True)
    return True


def enqueue_asset(instance):
    # from queuehandler.job_creator import UpkeepAssetSyncEnqueuer
    # UpkeepAssetSyncEnqueuer.enqueue_asset_syncing(
    #     instance.card_reader.id,
    #     HardwareType.CARD_READER
    # )
    from upkeep.manager import UpkeepCardReaderManager
    upkeep_manager = UpkeepCardReaderManager()
    upkeep_manager.create_or_update(instance.card_reader)


def sync_to_upkeep_hb(sender, instance, created, **kwargs):
    """
        If a HardwareBundle was either created or modified we sync
        the related CardReader to upkeep

        If a new HardwareBundle was created and it has the attribute
        warehouse populated, it means there was a warehouse scan. We sync
        to upkeep in such case
    """
    assets = []
    for asset in ['card_reader', 'machine']:
        ins = getattr(instance, asset, None)
        if ins: assets.append(ins)
    if assets: process_machine_thread(assets)
    if created:
        _sync_slot_label(instance.slot, skip_machine=True)

    #Uncomment if SQS processing is desired
    #Card Reader
    # UpkeepAssetSyncEnqueuer.enqueue_asset_syncing(
    #     instance.card_reader.id,
    #     HardwareType.CARD_READER
    # )
    #card_reader = instance.card_reader
    #UpkeepSyncingThread(instance.card_reader).start()

    #if not created or instance.machine.placeholder or not instance.warehouse: #Do not start a new thread unnecesarily if the machine is a placeholder
    #    return False
    #UpkeepSyncingThread(instance.machine).start()
    return True


def orphane_work_order(instance):
    OrphaneWorkOrder.create_work_order(
        instance.hardware_type,
        instance.hardware_id,
        instance.assigned_technician
    )


def sync_to_upkeep_hbr_requirement(sender, instance, created, **kwargs):
    """
    If a new HardwareBundleRequirement is created it means that an asset
    just became orphaned.
    """
    from .models import Machine
    if not created: return
    if instance.hardware_type == HardwareType.MACHINE:
        machine_obj = Machine.objects.get(pk=instance.hardware_id)
        #created = upkeep_manager.create_or_update(machine_obj)
        process_machine_thread([machine_obj])

    if not transaction.get_connection().in_atomic_block:
        orphane_work_order(instance)
    else:
        transaction.on_commit(lambda: orphane_work_order(instance))
    
    return True

def sync_to_upkeep(sender, instance, created, **kwargs):
    """connected to Machine model"""
    if created: return
    process_machine_thread([instance])
    hbs = instance.get_current_bundles()
    for hb in hbs:
        _sync_slot_label(hb.slot, skip_machine=True)
    return True

def orphane_piece_notification(sender, instance, created, **kwargs) -> bool:
    if not created: return
    OrphanePieceNotification.notify(instance)
    return True

def asset_mapout_notification(sender, instance, created, **kwargs) -> bool:
    if not created: return
    if instance.approved: return
    AssetMapOutEmailNotification(instance).send()
    return True

def swaptag_notification(sender, instance, created, **kwargs) -> bool:
    if not created: return
    if instance.approved: return
    SwapTagEmailNotification(instance).send()
    return True