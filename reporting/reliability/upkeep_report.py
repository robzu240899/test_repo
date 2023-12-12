import os
from datetime import datetime
from django.conf import settings
from roommanager.enums import HardwareType
from roommanager.models import Machine, CardReaderAsset, HardwareBundlePairing, Slot, AssetMapOut
from upkeep.manager import UpkeepAssetManager, UpkeepCardReaderManager
from .enums import UPKEEP_SYNCING_HEADERS, UNBUNBLED_SLOTS_HEADERS
from .outoforder_report import NewBaseReport, OOOReportManager

class UpkeepMissingPicsReport(NewBaseReport):
    dataset_headers = UPKEEP_SYNCING_HEADERS
    dataset_title = 'Upkeep Missing Pics'
    expected_fields = (
        'asset_picture',
        'asset_serial_picture'
    )

    def run(self):
        for machine in Machine.objects.filter(upkeep_id__isnull=False):
            if not all([True if getattr(machine, f, None) else False for f in self.expected_fields]
            ):
                msm = machine.machineslotmap_set.all().order_by('-start_time').first()
                hardware_bundles = UpkeepAssetManager._get_hardware_bundles(machine)
                related_slots = list()
                if hardware_bundles:
                    for bundle in hardware_bundles:
                        related_slots.append(bundle.slot)
                scans = HardwareBundlePairing.objects.filter(
                    asset_code=getattr(machine, 'asset_code')
                ).order_by('-timestamp')
                scans_string = '\n'.join([f"{scan.codereadr_username} - {scan.timestamp}" for scan in scans])
                row = [
                    msm.slot.laundry_room.display_name,
                    UpkeepAssetManager._build_asset_name(
                        machine,
                        related_slots,
                        msm.slot.laundry_room
                    )[0],
                    machine.asset_code,
                    scans_string,
                    machine.get_upkeep_asset_url(),
                    machine.get_maintainx_asset_url()
                ]
                self.dataset.append(row)


class OrphaneAssetsReport(NewBaseReport):
    dataset_title = "Orphane Assets"
    basic_headers = (
        'name',
        'category',
        'serial',
        'model',
        'description',
    )
    extra_headers = (
        'upkeep_url',
        'maintainx_url',
    )
    dataset_headers = basic_headers + extra_headers
    required_fields = basic_headers

    def __init__(self):
        self.assets = list()
        self.initialize_dataset()

    def as_row(self, asset):
        row = []
        if isinstance(asset, Machine):
            upkeep_manager = UpkeepAssetManager()
        elif isinstance(asset, CardReaderAsset):
            upkeep_manager = UpkeepCardReaderManager()
        fields = self.required_fields
        payload = upkeep_manager.build_asset_payload(asset)        
        for field in fields:
            row.append(payload.get(field, ''))
        upkeep_url = asset.get_upkeep_asset_url() or ''
        maintainx_url = asset.get_maintainx_asset_url() or ''
        row.append(upkeep_url)
        row.append(maintainx_url)
        return row

    def check_asset(self, asset):
        if asset.hardwarebundle_set.filter(is_active=True).count() < 1:
                self.assets.append(asset)

    def run(self):
        card_readers_query = CardReaderAsset.objects.filter(
            card_reader_tag__isnull=False
        )
        machines_query = Machine.objects.filter(
            asset_code__isnull=False
        )        
        for card_reader in card_readers_query:
            self.check_asset(card_reader)
        for machine in machines_query:
            self.check_asset(machine)

        for asset in self.assets:
            row_result = self.as_row(asset)            
            self.dataset.append(row_result)
        
        return self.dataset


class UnbundledSlotsReport(NewBaseReport):
    dataset_headers = UNBUNBLED_SLOTS_HEADERS
    dataset_title = 'Unbundled or Orphane Slots'
    bundle_url = '/admin/roommanager/hardwarebundle/{}/change/'

    def run(self):
        for slot in Slot.objects.filter(is_active=True, laundry_room__is_active=True):
            base_query = slot.hardwarebundle_set.all()
            if base_query.filter(is_active=True).count() < 1:
                row_result = [str(slot)]
                latest_bundled = base_query.order_by('-start_time').first()
                if latest_bundled:
                    url = settings.MAIN_DOMAIN + self.bundle_url.format(latest_bundled.id)
                    row_result.append(url)
                else:
                    row_result.append("Never scanned")
                self.dataset.append(row_result)
        return self.dataset


class MappedOutAssetsReport(NewBaseReport):
    dataset_headers = (
        'Asset Type',
        'Asset ID',
        'Asset Tag',
        'status',
        'timestamp'
    )
    fields = (
        'asset_type',
        'asset_id',
        'status',
        'timestamp'
    )
    dataset_title = 'Machines on the move'

    def run(self):
        queryset = AssetMapOut.objects.filter(active=True, needs_rescanning=True)
        for record in queryset:
            if record.asset_type == HardwareType.MACHINE:
                asset = Machine.objects.get(pk=record.asset_id)
                tag_code = asset.asset_code
            elif record.asset_type == HardwareType.CARD_READER:
                asset = CardReaderAsset.objects.get(pk=record.asset_id)
                tag_code = asset.card_reader_tag
            row = [getattr(record, field, None) for field in self.fields]
            row.insert(2, tag_code)
            self.dataset.append(row)
        return self.dataset


class UpkeepReportManager(OOOReportManager):
    reports_managers = [
        UpkeepMissingPicsReport,
        OrphaneAssetsReport,
        UnbundledSlotsReport,
        MappedOutAssetsReport
    ]

    def set_file_name(self):
        tm = datetime.now()
        tm = tm.strftime('%Y_%m_%d_%H_%M_%S')
        self.file_name = os.path.join(settings.BASE_DIR,'CMMSReport_%s.xls' % tm)

    def _generate_body_and_title(self):
        self.body = 'Please see attached daily Upkeep Report'
        self.title = 'Daily CMMS Report on %s'
        self.title = self.title % settings.ENV_TYPE

    def generate(self):
        for report in self.reports_managers:
            ins = report()
            ins.run()
            self.databook.add_sheet(ins.dataset)
        self.set_file_name()
        self.to_xls()
        self._generate_body_and_title()
        self.email_report()