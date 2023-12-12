import logging
from typing import List
from datetime import datetime
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from maintainx.api import MaintainxAPI
from upkeep.api import UpkeepAPI
from fascard.api import FascardApi
from main.decorators import ProductionCheck
from .enums import HardwareType


logger = logging.getLogger(__name__)


class OrphaneWorkOrder:
    default_maintainx_category = 'Standard Operating Procedure'

    @classmethod
    @ProductionCheck
    def create_work_order(self, hardware_type, hardware_id, assigned_technician):
        from roommanager.models import Slot, Machine, CardReaderAsset
        models_map = {
            HardwareType.SLOT : Slot,
            HardwareType.MACHINE : Machine,
            HardwareType.CARD_READER :  CardReaderAsset
        }
        model = models_map.get(hardware_type)
        asset = model.objects.get(pk=hardware_id)
        if not asset: return
        if isinstance(asset, Machine):
            msm = asset.machineslotmap_set.all().order_by('-start_time').first()
            location = msm.slot.laundry_room
            asset_url_slug = 'machine'
        elif isinstance(asset, CardReaderAsset):
            #last known location
            hb = asset.hardwarebundle_set.all().order_by('-start_time').first()
            location = hb.location
            asset_url_slug = 'cardreaderasset'
        else:
            return
        asset_url = f"https://system.aceslaundry.com/admin/roommanager/{asset_url_slug}/{asset.id}/change/"
        technician_upkeep_id = getattr(assigned_technician, "upkeep_id", None)
        technician_maintainx_id = getattr(assigned_technician, "maintainx_id", None)
        if technician_upkeep_id or technician_maintainx_id:
            category = 'Administrative - Orphaned Assets'
        else:
            category = 'Administrative - Orphaned by non-upkeep user'
        description = f"Triggered by Technician: {assigned_technician}.To see asset's history refer to: {asset_url}"
        upkeep_payload = {
            'title' : 'The asset is orphane',
            'asset' : asset.upkeep_id,
            'description' : description,
            'location' : getattr(location, "upkeep_code"),
            'assignedToUser' : technician_upkeep_id,
            'category' : category,
            'priority' : 2
        }
        maintainx_payload = {
            'title' : 'The asset is orphane',
            'assetId' : int(asset.maintainx_id),
            'description' : description,
            'locationId' : int(getattr(location, "maintainx_id")),
            'categories' : [self.default_maintainx_category],
            'priority' : "MEDIUM"
        }
        if technician_maintainx_id:
            maintainx_payload['assignees'] = [{"type": "USER", "id": int(technician_maintainx_id)}]
        upkeep_api = UpkeepAPI()
        maintainx_api = MaintainxAPI()
        upkeep_api.create_work_order(upkeep_payload)
        maintainx_api.create_work_order(maintainx_payload)


class OrphanePieceNotification():
    """
        Email notification to remind the Technician about providing an answer
        regarding the fate of the newly orphaned hardware piece.
    """
    email_template = 'orphaned_piece_email.html'

    @classmethod
    def notify(cls, instance):
        rendered_response = render_to_string(
            cls.email_template,
            {'obj': instance}
        )
        hbr = instance.hbr #HardwareBundleRequirement
        technician = getattr(hbr, 'assigned_technician')
        technician_email = getattr(technician, 'notifications_email', None)
        if technician_email:
            to_emails = [technician_email]
        else:
            to_emails = settings.DEFAULT_TO_EMAILS
        message = EmailMessage(
            subject = '[URGENT] Action needed on an Orphaned Hardware Piece',
            body = rendered_response,
            to = to_emails,
        )
        message.content_subtype = "html"
        message.send(fail_silently=False)


class BundleChangeApprovalEmail():

    def __init__(self, instance):
        self.template = self.email_template
        self.instance = instance
        self.to = settings.DEFAULT_TO_EMAILS + [self.DEFAULT_EMAIL]
        #self.to = ['juaneljach10@gmail.com']
        self.subject = self.subject or 'Required Action'

    def get_response(self):
        raise NotImplementedError

    def send(self):
        rendered_response = self.get_response()
        message = EmailMessage(
            subject = self.subject,
            body = rendered_response,
            to = self.to,
        )
        message.content_subtype = "html"
        message.send(fail_silently=False)


class AssetMapOutEmailNotification(BundleChangeApprovalEmail):
    """
        Email notification to remind the Technician about providing an answer
        regarding the fate of the an asset that has been scanned through the 
        MapOut Service
    """
    DEFAULT_EMAIL = 'Bundle_change_notifications@AcesLaundry.com'
    email_template = 'asset_mapout_approval_email.html'
    subject = '[URGENT] Action needed on new Asset Mapout Scan'

    def get_response(self) -> dict:
        rendered_response = render_to_string(
            self.template,
            {'obj': self.instance}
        )
        return rendered_response

class SwapTagEmailNotification(BundleChangeApprovalEmail):
    DEFAULT_EMAIL = 'Bundle_change_notifications@AcesLaundry.com'
    email_template = 'swap_tag_approval_email.html'
    subject = '[URGENT] Action needed on new SwapTag Scan'

    def get_response(self) -> dict:
        obj_type = self.instance.get_obj_type()
        rendered_response = render_to_string(
            self.template,
            {'obj': self.instance, 'obj_type': obj_type}
        )
        return rendered_response


class SlotUtils():

    @classmethod
    def fetch_slot_sync_data(cls, slot):
        machine = slot.get_current_machine(slot)
        data = {
            'label' : '',
            'serial_number' : '',
            'factory_model' : '',
            'machine' : machine
        }
        if machine:
            asset_code = getattr(machine, 'asset_code')
            if not asset_code: asset_code = 'Unknown'
            if machine.placeholder:
                asset_code = 'Orphan'
            else:
                data["serial_number"] = machine.asset_serial_number or ''
                data["factory_model"] = machine.asset_factory_model or ''
        else:
            asset_code = ''
        slot_description = getattr(slot, 'custom_description')
        if not slot_description: slot_description = ''
        label = f"#{getattr(slot, 'web_display_name', '')}"
        if asset_code != '':
            label += f" ~{asset_code[:4]}~ "
        if slot_description != '':
            label += f"{slot_description}"
        data['label'] = label
        return data

    @classmethod
    def fascard_name_checker(cls, rooms):
        """
        Checks wheter the slot's fascard label matches the expected name given by our code.
        We have seen cases where fascard slot labels reset automatically to wrong names
        """
        api = FascardApi()
        diff = {}
        logger.info(f"Checking Fascard slot labels for {len(rooms)} rooms")
        for room in rooms:
            logger.info(f"Room: {room}")
            slots = room.slot_set.all()
            for slot in slots:
                expected_label = cls.fetch_slot_sync_data(slot)['label']
                try:
                    fascard_label = api.get_machine(slot.slot_fascard_id)['Label']
                except:
                    continue
                if expected_label != fascard_label:
                    diff[str(slot)] = f'exp: {expected_label} - curr: {fascard_label}'
        logger.info("Finished analysis")
        if diff:
            logger.info("Found mismatches")
            email_body = ''
            for k,v in diff.items():
                email_body += f'Slot: {k}. {v} \n'
            email = EmailMessage(
                'Slots label mismatches',
                email_body,
                settings.DEFAULT_FROM_EMAIL,
                ['suricatadev@gmail.com']
            )
            logger.info("Email body ready")
            email.send(fail_silently=False)
            logger.info("Email sent")