import time
import logging
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from django import forms
from django.db import transaction
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import DetailView, UpdateView, CreateView
from django.views.generic.list import ListView
from rest_framework.response import Response
from rest_framework import permissions, authentication, views, status 
from fascard.api import FascardApi
from queuehandler.config import JobInstructions
from queuehandler.job_creator import RoomManagerCreator, RevenueCreator
from queuehandler.queue import Enqueuer
from main.utils import CustomDateInput
from main.views import DateRangeForm
from maintainx.managers.managers import MaintainxWorkOrderManager
from reporting.enums import LocationLevel, DurationType, MetricType
from reporting.models import MetricsCache
from reporting.reliability.upkeep_report import OrphaneAssetsReport
from reporting.threads import FirstTransactionThreadReport
from roommanager.job import HardwareBundleManager, HardwareBundleJobProcessor, SwapTagManager, MapOutAsset
from roommanager.models import AssetUpdateApproval
from .enums import BundleType, OrphanedPieceAnswerChoices, HardwareType
from .forms import BundleChangeApprovalForm, AssetUpdateApprovalForm, ManualAssetMapoutCreateForm, MachineMeterReadingForm
from .helpers import XMLResponse, MachineSlotMapUpdateManager, EquipmentTypeNameManager, get_equipment_type, MessagesTranslationHelper
from .models import TechnicianEmployeeProfile, MachineSlotMap, LaundryRoom, Machine, \
WorkOrderRecord, HardwareBundle, BundleChangeApproval, OrphanedPieceRequiredAnswer, AssetMapOut, SwapTagLog, MaintainxWorkOrderRecord
from .threads import SlotLabelCheckThread


logger = logging.getLogger(__name__)


class ManualSyncForm(forms.Form):
    manual_sync = forms.BooleanField()


class OnDemandLaundryRoomSync(LoginRequiredMixin, View):
    login_url = "/admin/login/"
    form_class = ManualSyncForm
    processor = RoomManagerCreator.laundry_room_sync
    template_name = 'laundry_room_sync_manual.html'
    success_msg = "Registration Success. Please wait a few minutes for processing"

    def get(self, request, *args, **kwargs):
        form = self.form_class()
        return TemplateResponse(request, self.template_name, {'form': form})

    def post(self, request, *args, **kwargs):
        context = {}
        form = self.form_class(request.POST)
        if form.is_valid():
            do = form.cleaned_data.get('manual_sync')
            if do:
                self.processor()
            msg = self.success_msg
        context['form'] = form
        context['msg'] = msg
        context.update(self.kwargs)
        return TemplateResponse(request, self.template_name, context)


class UpdateMachineSlotMapForm(forms.Form):
    machine_slot_map = forms.ModelChoiceField(
        queryset=MachineSlotMap.objects.filter(is_active=True).order_by('slot__laundry_room__id'), 
        empty_label=None
    )
    new_start_time = forms.DateField(widget=CustomDateInput)
    override_previous = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        location = kwargs.pop('location_id', None)
        super(UpdateMachineSlotMapForm, self).__init__(*args, **kwargs)

        if location:
            self.fields['machine_slot_map'].queryset = MachineSlotMap.objects.filter(
                is_active=True,
                slot__laundry_room_id=location
            ).order_by('slot__laundry_room__id')
    #new_end_time = forms.DateField(widget=CustomDateInput)


class LocationsListView(View):
    template_name = 'locations_list.html'

    def get(self, request, *args, **kwargs):
        context = {'locations' : LaundryRoom.objects.filter(is_active=True)}
        return TemplateResponse(request, self.template_name, context)


class UpdateMachineSlotMap(View):
    form_class = UpdateMachineSlotMapForm
    template_name = 'update_machineslotmap.html'
    equipment_validation_error = "You cannot override a previous MachineSlotMap with different equipment type than that of the current"

    def get(self, request, *args, **kwargs):
        location_id = request.GET.get('location_id', None)
        init_data = {}
        if location_id:
            init_data['location_id'] = location_id
        location_obj = LaundryRoom.objects.get(pk=location_id)
        slots = location_obj.slot_set.all()
        form = self.form_class(**init_data)
        context = {'form':form, 'slots':slots, 'location': location_obj}
        return TemplateResponse(request, self.template_name, context)

    def enqueue_metrics_recalc(self, machine, start_date, end_date=None):
        if end_date is None:
            end_date = date.today()
        start_date = start_date - timedelta(days=30)
        enqueuer = Enqueuer()

        for offset in range((end_date-start_date).days):
            t1 = start_date + timedelta(days=offset)
            t2 = t1 + timedelta(days=1)
            enqueuer.add_message(
                JobInstructions.METRICS_CREATION.job_name,
                {
                    'locationlevel':LocationLevel.MACHINE,
                    'locationid':machine.id,
                    'startdate':start_date,
                    'enddate':end_date
                }
            )

    def post(self, request, *args, **kwargs):
        context = {}
        form = self.form_class(request.POST)
        if form.is_valid():
            new_start = form.cleaned_data.get('new_start_time')
            msm = form.cleaned_data.get('machine_slot_map')


            override_previous = form.cleaned_data.get('override_previous')
            current_equipment = EquipmentTypeNameManager(msm.machine.equipment_type)
            old_start_time = msm.start_time
            previous_msm = MachineSlotMapUpdateManager.get_previous_msm(msm, new_start)
            
            msm_after_new_start = MachineSlotMap.objects.filter(
                slot=msm.slot,
                start_time__gte=new_start,
                end_time__lte=old_start_time,
                is_active=False
            )

            if override_previous:

                if msm_after_new_start.count() > 0:
                    can_delete = list()
                    for overridable_msm in msm_after_new_start:
                        can = True
                        msm_equipment = overridable_msm.machine.equipment_type
                        if msm_equipment is not None:
                            can = current_equipment.equals(msm_equipment)
                        can_delete.append(can)

                    if all(can_delete):
                        for x in msm_after_new_start:
                            #a=x
                            x.delete()
                    else:
                        raise forms.ValidationError(self.equipment_validation_error)

                if previous_msm:    
                    if current_equipment.equals(previous_msm.machine.equipment_type):
                        previous_msm.end_time = new_start
                        previous_msm.save()
                    else:
                        raise forms.ValidationError(self.equipment_validation_error)

                    old_machine = previous_msm.machine
                
            msm.start_time = new_start
            msm.save()

            # RevenueCreator.create_transaction_update_job(
            #     msm.start_time,
            #     msm.end_time,
            #     msm.slot.id,
            #     msm.machine.id
            # )

            #NOTE: Better update transactions in the same HTTP thread. Handling eveything with SQS
            #would be overly complex
            MachineSlotMapUpdateManager.update_transactions(
                msm.start_time, 
                msm.end_time, 
                msm.slot.id, 
                msm.machine.id
            )

            self.enqueue_metrics_recalc(msm.machine, msm.start_time, msm.end_date)
            if old_machine:
                self.enqueue_metrics_recalc(old_machine, msm.start_time, msm.end_date)
            #self.enqueue_metrics_recalc(msm.machine, msm.start_time, msm.end_time)
            msg = 'Update was successful!. Transactions attributions and Metrics recalculation are cooking'
            #TODO Recalculate all metrics on a monthly bases for all months after new start time
            #Find out what metrics need to be re-calculated

        context['form'] = form
        return TemplateResponse(request, self.template_name, context)


class HardwareBundleView(View):
    input_fields = (
        'fascardReader',
        'assetTag',
        'dataMatrix'
    )
    SINGLE_BUNDLE_ID = '1517016'
    testing_single_scanner = '1567304'
    STACK_DRYER_BUNDLE_ID = '1522348'
    testing_stack_dryer = '1569006'
    testing_warehouse_scanner = '1569737'
    WAREHOUSE_SCANNER = '1570718'
    testing_warehouse = '1569737'
    testing_stack_warehouse = '1570188'
    STACK_WAREHOUSE_SCANNER = '1570716'
    SWAP_TAGS_SERVICE = '1582898'
    testing_swap_service = '1638411'
    MAP_OUT_ASSET = '1611598'
    testing_mapout_asset = '1637486'
    modelfieldsmap = {
            'card-reader-tag-A':'card_reader_code',
            'card-reader-tag-B':'card_reader_code',
            'data-matrix-A': 'data_matrix_string',
            'data-matrix-B': 'data_matrix_string',
            'asset-tag': 'asset_code',
            'asset-picture' : 'asset_picture',
            'asset-serial-picture' : 'asset_serial_picture',
    }

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        #NOTE: Jobs will be processed directly by frontend instances from now on.
        #if not settings.IS_BACKEND == True:
        #    exception_string = "Forbidden to access to unless on the backend environment"
        #    logger.error(exception_string)
        #    raise Exception(exception_string)
        return super(HardwareBundleView, self).dispatch(request, *args, **kwargs)

    def parse_job_data(self, payload):
        job_data = {
            'submissionid' : self.submission_id,
            'codereadrusername' : self.tech_username,
            'fascardreader' : payload.get('card_reader_code'),
            'assettag' : payload.get('asset_code'),
            'datamatrixstring' : payload.get('data_matrix_string'),
            'assetpicture' : payload.get('asset_picture'),
            'assetserialpicture' : payload.get('asset_serial_picture'),
            'assetserialnumber' : payload.get('asset_serial_number'),
            'machinedescription' : payload.get('machine_description'),
            'warehouse' : payload.get('warehouse'),
            'combostack' : payload.get('combostack'),
            'filetransfertype' : payload.get('file_transfer_type'),
            'fileuploadpath' : payload.get('file_upload_path')
        }
        return job_data

    def _save_slot_data(self, slot_id, parsed_data):
        if not hasattr(self, 'parsed_jobs_data'): self.parsed_jobs_data = {}
        self.parsed_jobs_data[slot_id] = parsed_data

    def _get_data_matrix_response(self, payload) -> dict:
        temp_ins = HardwareBundleManager(**payload)
        temp_ins.data_matrix_string = temp_ins.parse_data_matrix(temp_ins.data_matrix_string)
        datamatrix_response = temp_ins.get_datamatrix_response(temp_ins.string_to_hex(temp_ins.data_matrix_string))
        if datamatrix_response:
            slot_fascard_id = datamatrix_response.get('MachineID')
            self._save_slot_data(slot_fascard_id, payload)
            room_fascard_code = int(datamatrix_response.get('LocationID'))
            if not temp_ins.valid_slot(slot_fascard_id, room_fascard_code): return None
        else:
            return None
        return datamatrix_response

    def _get_all_matrix_responses(self, parsed_job_data):
        if not hasattr(self, 'data_matrices_responses'): self.data_matrices_responses = []
        for parsed_job_data in parsed_job_data:
            response = self._get_data_matrix_response(parsed_job_data)
            if response: self.data_matrices_responses.append(response)
        return self.data_matrices_responses.copy()

    def _check_equipment_types(self, matrices_responses):
        fascard_api = FascardApi(1)
        last_equipment = None
        if len(matrices_responses) != 2: return False
        for matrix_response in matrices_responses:
            slot_response = fascard_api.get_machine(matrix_response.get('MachineID'))
            location = LaundryRoom.objects.get(fascard_code=int(matrix_response.get('LocationID')))
            if not location: return False
            equipment = get_equipment_type(slot_response['EquipID'], location)
            if not last_equipment:
                last_equipment = equipment
            else:
                if equipment != last_equipment: raise Exception('The StackDryer Bundles being scanned have different equipment types.')
                last_equipment = equipment
        return True

    def _is_dual_pocket(self, parsed_jobs_data):
        data_matrices_responses = getattr(self, 'data_matrices_responses', None)
        if not data_matrices_responses: data_matrices_responses = [self._get_data_matrix_response(parsed_job_data) for parsed_job_data in parsed_jobs_data]
        previous_mac = None
        fascard_api = FascardApi()
        for data_matrix in data_matrices_responses:
            slot_fascard_id = data_matrix.get('MachineID')
            history = fascard_api.get_machine_history(machine_fascard_id=slot_fascard_id, limit=0)
            latest_entry = history[:1]
            if not latest_entry:
                raise Exception(f"The Slot with FascardID {slot_fascard_id} has no machine history. At least one entry is needed to determine if it's a dual pocket")
            latest_entry = latest_entry[0]
            current_mac = latest_entry.get('MACAddr')
            if not previous_mac: previous_mac = current_mac
            if current_mac != previous_mac:
                print (f"MAC addresses are different: {current_mac} - {previous_mac}")
                return False
        return True

    def _decide_slot_replacement(self, slot_fascard_ids, existing_slot_ids):
        replacement_memory = {}
        scanned_slots = slot_fascard_ids.copy()
        existing_slots = existing_slot_ids.copy()
        for slot in slot_fascard_ids:
            if slot in existing_slot_ids:
                scanned_slots.pop(scanned_slots.index(slot))
                existing_slots.pop(existing_slots.index(slot))
        max_loops = min(len(scanned_slots), len(existing_slots))
        for i in range(max_loops):
            replacement_memory[scanned_slots[i]] = existing_slots[i]
        return replacement_memory

    def load_dual_pocket_params(self, scan_type):
        if not hasattr(self, 'parsed_jobs_data'): self._get_all_matrix_responses()
        assert hasattr(self, 'parsed_jobs_data')
        jobs_data = list(self.parsed_jobs_data.values())
        if jobs_data[0].get('assettag') != jobs_data[1].get('assettag'):
            raise Exception("The machine's asset tag in a dual pocket stackdryer must be the same")
        if jobs_data[0].get('fascardreader') != jobs_data[1].get('fascardreader'):
            raise Exception("The card reader's tag in a dual pocket stackdryer must be the same")
        assert jobs_data[0].get('assettag')
        existing_hardware_bundles = HardwareBundle.objects.filter(
            machine__asset_code=jobs_data[0].get('assettag'),
            card_reader__card_reader_tag = jobs_data[0].get('fascardreader')
        )
        new_bundle = False #Represents wheter at least a new bundle should be created when processing
        slot_fascard_ids = self.parsed_jobs_data.keys()
        slot_replacements = self._decide_slot_replacement(
            list(slot_fascard_ids),
            [bundle.slot.slot_fascard_id for bundle in existing_hardware_bundles]
        )
        for slot_fascard_id, job_data in self.parsed_jobs_data.items():
            job_data['scantype'] = scan_type
            if slot_fascard_id in slot_replacements.keys():
                job_data['slot_being_replaced'] = slot_replacements.get(slot_fascard_id)
            else:
                job_data['dual_pocket_new_bundle'] = True
        return self.parsed_jobs_data.values()

        #Summary of code above
        #get existing new bundles
        #If there are none
            #if there are none this is a new bundle, so no slot_replacements
            #two bundles to be created dual_pocket_new_bundles = True
        #If There is one hardware bundle
            #Check if one of the slots being submitted in the scan matches the existing slot
            #If so:
                #No slot-replacement and only one bundle creation. This results in two bundles for the dual
                #pocket and therefore the whole thing is now complete (one bundle for each slot)
            #else:
                #One bundle creation and one slot replacement. Does it matter which slot replaces which?
        #If there are two
            # Check if one of the slots being submitted matches any of the existing slots
            #if so:
                #ignore the ones that match and figure out which replaces which - i.e one slot_replacement only
            #else:
                #it means that both are being changed at the same time. Does it matter which replaces which?

    def _get_parsed_jobs_data(self, cleaned_codes, scan_type):
        if hasattr(self, 'parsed_jobs_data') and self.parsed_jobs_data:
            parsed_jobs_data = self.parsed_jobs_data.values()
        else:
            parsed_jobs_data = []
            for k in cleaned_codes.keys():
                job_data = self.parse_job_data(cleaned_codes.get(k))
                parsed_jobs_data.append(job_data)
        for job_data in parsed_jobs_data:
            job_data['scantype'] = scan_type
        return parsed_jobs_data

    def _check_combostack(self, matrices_responses):
        try: assert len(matrices_responses)
        except AssertionError: raise Exception("At least one slot being scanned is not active")
        combostack = False
        prev_equip_class = None
        fascard_api = FascardApi()
        room_fascard_id = int(matrices_responses[0].get('LocationID'))
        equipments = fascard_api.get_equipment(fascard_location_id=room_fascard_id)
        for response in matrices_responses:
            slot_response = fascard_api.get_machine(response.get('MachineID'))
            equip_id = slot_response['EquipID']
            equip_class = None
            for equipment_response in equipments:
                if equipment_response['ID'] == equip_id: equip_class = equipment_response['EquipClass']
            if not equip_class: raise Exception(f"Couldn't identify the Equipment Class of slot {response.get('MachineID')}")
            if prev_equip_class and prev_equip_class != equip_class: combostack = True
            prev_equip_class = equip_class
        return combostack
    
    def _build_missing_fields_msg(self, missing_fields):
        from roommanager.enums import MissingAssetFieldNotifications
        missing_fields_msg = ''
        for field in missing_fields:
            notification = MissingAssetFieldNotifications.get(field)
            missing_fields_msg = missing_fields_msg + "-{}. \n".format(
                MessagesTranslationHelper.get(notification)
            )
        return missing_fields_msg

    def stacked_processor(self, warehouse=False):
        logger.info("stacked_processor")
        try:
            cleaned_codes = HardwareBundleManager.clean_stackdryer(self.original_request)
            self.data_matrices_responses = []
            if warehouse: scan_type = BundleType.STACKED_WAREHOUSE
            else: scan_type = BundleType.STACK_DRYER
            parsed_jobs_data = self._get_parsed_jobs_data(cleaned_codes, scan_type)
            #Check if both equipment types are the same in case the scan is NOT Combostack
            matrices_responses = self._get_all_matrix_responses(parsed_jobs_data)
            combostack = self._check_combostack(matrices_responses)
            for job_data in parsed_jobs_data: job_data['combostack'] = combostack
            if scan_type == BundleType.STACK_DRYER and not combostack:
                self._check_equipment_types(matrices_responses)
        except Exception as e:
            response = 'Scanning process Failed with Exception: {}'.format(e)
            return response
        # if self._is_dual_pocket(parsed_jobs_data):
        #     scan_type = BundleType.STACK_DRYER_DUAL_POCKET
        #     try:
        #         parsed_jobs_data = self.load_dual_pocket_params(scan_type)
        #     except Exception as e:
        #         return str(e)
        responses = []
        all_missing_fields = []
        for job_data in parsed_jobs_data:
            job_response, missing_fields = HardwareBundleJobProcessor.job_scheduler(job_data)
            if missing_fields: all_missing_fields.extend(missing_fields)
            if isinstance(job_response, str) and job_response is not None:
                responses.append(job_response)
        logger.info(f"responses: {responses}")
        response = '\n'.join(responses)
        if all_missing_fields:
            all_missing_fields = set(all_missing_fields)
            missing_fields_msg = self._build_missing_fields_msg(missing_fields)
            response = response + f"\n. {MessagesTranslationHelper.get('missing_fields')} \n" + missing_fields_msg
        return response

    def single_processor(self, warehouse=False):
        cleaned_codes = HardwareBundleManager.clean_singlebundle(self.original_request, warehouse)
        job_data = self.parse_job_data(cleaned_codes)
        if warehouse: scan_type = BundleType.WAREHOUSE
        else: scan_type = BundleType.SINGLE
        job_data['scantype'] = scan_type
        #Daniel no longer wants the tasks to be processed via SQS
        response, missing_fields = HardwareBundleJobProcessor.job_scheduler(job_data)
        logger.info("executed job_scheduler")
        if missing_fields:
            missing_fields_msg = self._build_missing_fields_msg(missing_fields)
            response = response + f"\n. {MessagesTranslationHelper.get('missing_fields')} \n" + missing_fields_msg
        return response

    def swap_tag_processor(self, warehouse=False):
        response = SwapTagManager(self.original_request, self.tech_username).process()
        return response
    
    def map_out_processor(self):
        response = MapOutAsset(self.original_request, self.tech_username).process()
        return response

    @csrf_exempt
    def post(self,request):
        try:
            query_dict = request.POST.dict()
            self.original_request = query_dict
            self.submission_id = self.original_request.get('Scan ID')
            self.tech_username = self.original_request.get('User Name')
            service_id = query_dict.pop('Service ID')
            if service_id in [self.SWAP_TAGS_SERVICE, self.testing_swap_service]:
                response = self.swap_tag_processor()
            elif service_id in [self.SINGLE_BUNDLE_ID, self.testing_single_scanner]:
                response = self.single_processor()
            elif service_id in [self.WAREHOUSE_SCANNER, self.testing_warehouse]:
                response = self.single_processor(warehouse=True)
            elif service_id in [self.STACK_DRYER_BUNDLE_ID, self.testing_stack_dryer]:
                response = self.stacked_processor()
            elif service_id == self.STACK_WAREHOUSE_SCANNER:
                response = self.stacked_processor(warehouse=True)
            elif service_id in [self.MAP_OUT_ASSET, self.testing_mapout_asset]:
                response = self.map_out_processor()
            else:
                response = 'Invalid Scanner'
        except Exception as e:
            response = f'An Exception occured: {e}'
        xml_response = XMLResponse(response).get_response()
        return HttpResponse(xml_response,  content_type='text/xml')


class SearchMachineForm(forms.Form):
    rooms = forms.ModelMultipleChoiceField(
        help_text='Leave Blank for Unbundled Assets',
        queryset=LaundryRoom.objects.all(),
        required = False
    )
    months_to_lookback = forms.IntegerField(min_value=1)

class SearchMachineView(View):
    template_name = 'search_machine.html'
    form_class = SearchMachineForm

    def get(self, request, *args, **kwargs):
        form = self.form_class()
        context = {'form':form}
        return TemplateResponse(request, self.template_name, context)


    def post(self, request, *args, **kwargs):
        context = self.kwargs
        form = self.form_class(request.POST)
        msg = ''
        if form.is_valid():
            rooms = form.cleaned_data.get('rooms')
            months_to_lookback = form.cleaned_data.get('months_to_lookback')
            start_from = date.today() - relativedelta(months=months_to_lookback)
            data = {}
            if rooms:
                for room in rooms:
                    msms = MachineSlotMap.objects.filter(
                        slot__laundry_room=room,
                        machine__asset_code__isnull=False,
                        is_active=True,
                        start_time__gte=start_from,
                    )
                    machines = [msm.machine for msm in msms]
                    data[room] = machines
            else:
                #Machine.objects.filter(asset_code__isnull=False)
                ins = OrphaneAssetsReport()
                machines_query = Machine.objects.filter(
                    asset_code__isnull=False
                )
                for machine in machines_query:
                    ins.check_asset(machine)
                data['Unbundled'] = ins.assets
        context.update({'form': form , 'data':data})
        return TemplateResponse(request, self.template_name, context)
    #assert machine.upkeep_id
    #assert machine.asset_code


class RepairReplaceView(DetailView):
    model = Machine
    slug_url_kwargs = 'asset_code'
    slug_field = 'asset_code'
    template_name = 'machine_detail.html'

    def get_context_data(self, **kwargs):
        context_data = super(RepairReplaceView, self).get_context_data(**kwargs)
        obj = self.get_object()
        meter = getattr(obj, 'meter')
        hbs = HardwareBundle.objects.filter(machine=obj).order_by('start_time')
        #slots = [getattr(hb, 'slot', None) for hb in hbs]
        first_scan_date = hbs.first().start_time
        upkeep_work_orders = WorkOrderRecord.objects.filter(asset_upkeep_id=obj.upkeep_id)
        maintainx_work_orders = MaintainxWorkOrderRecord.objects.filter(asset_maintainx_id=obj.maintainx_id)
        revenue_earned = MetricsCache.objects.filter(
            location_id=obj.id,
            location_level=LocationLevel.MACHINE,
            metric_type=MetricType.REVENUE_EARNED,
            duration=DurationType.MONTH
        ).order_by('start_date')
        if revenue_earned:
            total_revenue = revenue_earned.values('result').aggregate(total=Sum('result'))
            date_period = f"{revenue_earned.first().start_date} - {revenue_earned.last().start_date}"
        else:
            total_revenue = 'Unknown'
            date_period = 'Unknown'
        payload = {
            'meter_count' : meter.transactions_counter,
            'first_scan_date' : first_scan_date,
            'bundles_history' : hbs,
            'upkeep_work_orders' : upkeep_work_orders,
            'maintainx_work_orders' : maintainx_work_orders,
            'revenue_earned' : total_revenue,
            'date_period' : date_period
        }
        context_data.update(payload)
        return context_data


class FirstTransactionRoomForm(forms.Form):
    rooms = forms.ModelMultipleChoiceField(
        queryset=LaundryRoom.objects.filter(is_active=True),
        required = True,
        widget = forms.SelectMultiple(attrs = {'class':"big-select"})
    )
    number = forms.IntegerField(
        label = 'Number of Transactions to retrieve',
        required=False)
    filter_on_field = forms.ChoiceField(
        choices = (('assigned_laundry_room','assigned_laundry_room'),('laundry_room','laundry_room')),
        required = True)


class FirstTransactionView(LoginRequiredMixin, View):
    """
    Retrieves first n transactions in a room based on either laundry_room field or assigned_laundry_room_field
    """
    template_name = 'get_room_last_transaction.html'
    form_class = FirstTransactionRoomForm

    def get(self, request, *args, **kwargs):
        form = self.form_class()
        context = {'form':form}
        return TemplateResponse(request, self.template_name, context)


    def post(self, request, *args, **kwargs):
        context = self.kwargs
        form = self.form_class(request.POST)
        msg = ''
        if form.is_valid():
            rooms = form.cleaned_data.get('rooms')
            transactions_lookback = form.cleaned_data.get('number')
            filter_on_field = form.cleaned_data.get('filter_on_field')
            if not transactions_lookback: transactions_lookback = 10
            thread_processor = FirstTransactionThreadReport(
                rooms,
                filter_on_field,
                transactions_lookback,
                request.user.email
            )
            thread_processor.start()
            context['msg'] = 'Processing Jobs. Please check your email in a moment'
        context.update({'form': form})
        return TemplateResponse(request, self.template_name, context)

class HardwareBundleChangesForm(DateRangeForm):
    rooms = forms.ModelMultipleChoiceField(
        queryset=LaundryRoom.objects.filter(is_active=True),
        required = True
    )


class HardwareBundleChangesView(DetailView):
    form_class = HardwareBundleChangesForm
    template_name = 'hardware_bundle_changes_report.html'

    def get(self, request, *args, **kwargs):
        form = self.form_class()
        context = {'form':form}
        return TemplateResponse(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        context = self.kwargs
        form = self.form_class(request.POST)
        msg = ''
        if form.is_valid():
            rooms = form.cleaned_data.get('rooms')
            start_date = form.cleaned_data.get('start_date')
            end_date = form.cleaned_data.get('end_date')
            data = {}
            for room in rooms:
                data[room] = room.hardware_bundle_changes.filter(
                    timestamp__gte=start_date,
                    timestamp__lte=end_date)
        else:
            return TemplateResponse(request, self.template_name, {'form': form})
        context.update({'form': form , 'data':data})
        return TemplateResponse(request, self.template_name, context)


class BaseApprovalMixin():

    def _bundle_pairing_as_payload(self, hardware_bundle_pairing: HardwareBundle) -> dict:
        payload = {
            'submissionid' : hardware_bundle_pairing.submission_id,
            'codereadrusername' : hardware_bundle_pairing.codereadr_username,
            'fascardreader' : hardware_bundle_pairing.card_reader_code,
            'assettag' : hardware_bundle_pairing.asset_code,
            'assetpicture' : hardware_bundle_pairing.asset_picture,
            'assetserialpicture' : hardware_bundle_pairing.asset_serial_picture,
            'datamatrixstring' : hardware_bundle_pairing.data_matrix_string,
            'scantype' : hardware_bundle_pairing.scan_type,
            'warehouse' : hardware_bundle_pairing.warehouse,
            'dual_pocket_new_bundle': hardware_bundle_pairing.dual_pocket_new_bundle,
            'slot_being_replaced' : hardware_bundle_pairing.slot_being_replaced,
            'combostack' : hardware_bundle_pairing.combostack,
            'filetransfertype' : hardware_bundle_pairing.file_transfer_type,
            'fileuploadpath' : hardware_bundle_pairing.file_transfer_upload_path
        }
        return payload

    def post(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        form = form_class(request.POST, extra_init=self.extra_init)
        obj = self.get_object()
        extra_msg = None
        msg = ""
        if form.is_valid():
            approved = form.cleaned_data.get('approved')
            rejected = form.cleaned_data.get('rejected')
            asset_serial_number = form.cleaned_data.get('asset_serial_number')
            asset_factory_model = form.cleaned_data.get('asset_factory_model')
            machine_description = form.cleaned_data.get('machine_description')
            serial_number_not_available = form.cleaned_data.get('serial_number_not_available')
            decision_taken = False
            if approved:
                decision_taken = True
                try:
                    msg = self.success_message
                    with transaction.atomic():
                        as_payload = self._bundle_pairing_as_payload(obj.scan_pairing)
                        as_payload['asset_picture_decision'] = form.cleaned_data.get('asset_picture_decision')
                        as_payload['asset_serial_picture_decision'] = form.cleaned_data.get('asset_serial_picture_decision')
                        hardware_bundle_pairing = obj.scan_pairing
                        if asset_serial_number: hardware_bundle_pairing.asset_serial_number = asset_serial_number
                        if asset_factory_model: hardware_bundle_pairing.asset_factory_model = asset_factory_model
                        if machine_description: hardware_bundle_pairing.machine_description = machine_description
                        hardware_bundle_pairing.save()
                        hardware_bundle_pairing.refresh_from_db()
                        bundle_manager = HardwareBundleManager(**as_payload)
                        bundle_manager.object = hardware_bundle_pairing
                        bundle_manager._set_user_language()
                        bundle_manager.pair(requires_approval=False)
                        if hasattr(bundle_manager, 'err_msg'):
                            msg = bundle_manager.err_msg
                        elif hasattr(bundle_manager, 'msg'):
                            extra_msg = bundle_manager.msg
                            obj.approved = approved
                            obj.save()
                except Exception as e:
                    msg = f'Failed: {e}'
                if extra_msg: msg = '. '.join([msg, extra_msg])
            if rejected:
                decision_taken = True
                msg = self.rejected_message
                obj.rejected = rejected
            if decision_taken:
                obj.decision_maker = self.request.user
                #mark associated work order as done
                wo_manager = MaintainxWorkOrderManager()
                wo_manager.update_work_order({'status': "DONE"}, obj.associated_work_order_maintainx_id)
            obj.serial_number_not_available = serial_number_not_available
            obj.save()
        else:
            return TemplateResponse(request, self.template_name, {'form': form})
        return HttpResponse(msg)


class BundleChangeApprovalUpdateView(LoginRequiredMixin, BaseApprovalMixin, UpdateView):
    model =  BundleChangeApproval
    slug_field = 'pk'
    slug_url_kwarg = 'pk'
    template_name = "bundle_change_approval_form.html"
    form_class = BundleChangeApprovalForm
    success_message = "Bundle Change Successfully Approved"
    rejected_message = "Bundle Change Rejected"
    extra_init = False

    def get_context_data(self, *args, **kwargs):
        context = super(BundleChangeApprovalUpdateView, self).get_context_data(*args, **kwargs)
        context['obj'] = self.get_object()
        return context


class AssetUpdateApprovalView(LoginRequiredMixin, BaseApprovalMixin, UpdateView):
    model =  AssetUpdateApproval
    slug_field = 'pk'
    slug_url_kwarg = 'pk'
    template_name = "asset_update_approval_form.html"
    form_class = AssetUpdateApprovalForm
    success_message = "Asset Successfully Updated"
    rejected_message = "Asset Update Rejected"
    extra_init = True

    def get_context_data(self, *args, **kwargs):
        context = super(AssetUpdateApprovalView, self).get_context_data(*args, **kwargs)
        context['obj'] = self.get_object()
        return context


class BundleChangeListView(ListView):
    """
        Report of outstanding Bundle Changes requiring approval
    """
    model = BundleChangeApproval
    template_name = "bundle_change_list.html"

    def get_queryset(self, *args, **kwargs):
        q = super(BundleChangeListView, self).get_queryset(*args, **kwargs)
        q = q.filter(approved=False, rejected=False, superseded_by__isnull=True)
        return q


class BaseActionTakenView(ListView):

    def get_queryset(self, *args, **kwargs):
        q = super(BaseActionTakenView, self).get_queryset(*args, **kwargs)
        q = q.filter(**self.query)
        return q
    
    def get_context_data(self, *args, **kwargs):
        context = super(BaseActionTakenView, self).get_context_data(*args, **kwargs)
        context['action_taken'] = self.action_taken
        return context


class ApprovedBundleChangeListView(BaseActionTakenView):
    model = BundleChangeApproval
    template_name = "action_taken_bundle_change_list.html"
    query = {'approved':True}
    action_taken = 'approved'


class RejectedBundleChangeListView(BaseActionTakenView):
    model = BundleChangeApproval
    template_name = "action_taken_bundle_change_list.html"
    query = {'rejected':True}
    action_taken = 'rejected'



class OrphanedPieceAnswerUpdateView(UpdateView):
    fields = ('answer',)
    model =  OrphanedPieceRequiredAnswer
    context_obj_name = 'obj'
    slug_field = 'pk'
    slug_url_kwarg = 'pk'
    template_name = "orphaned_piece_answer.html"

    def get_context_data(self, *args, **kwargs):
        context = super(OrphanedPieceAnswerUpdateView, self).get_context_data(*args, **kwargs)
        context['obj'] = self.get_object()
        return context

    def get_form(self, form_class=None):
        if form_class is None:
            form_class = self.get_form_class()
        kwargs = self.get_form_kwargs()
        kwargs['instance'] = self.object
        form = form_class(**kwargs)
        if self.object.hbr.hardware_type == HardwareType.SLOT: form.fields['answer'].choices = OrphanedPieceAnswerChoices.SLOT_CHOICES
        else: form.fields['answer'].choices = OrphanedPieceAnswerChoices.MACHINE_CARDREADER_CHOICES
        return form        

    def post(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        form = form_class(request.POST)
        obj = self.get_object()
        if form.is_valid():
            answer = form.cleaned_data.get('answer')
            obj.answer = answer
            obj.save()
            msg = 'Answer successfully saved'
        else:
            msg = 'Invalid Form'
        return HttpResponse(msg)


class ManualAssetMapoutCreateView(View):
    template_name = "manual_asset_mapout.html"
    form_class = ManualAssetMapoutCreateForm

    @method_decorator(login_required)
    def get(self,request):
        form = self.form_class()
        return TemplateResponse(request, self.template_name, {'form': form})

    @method_decorator(login_required)
    def post(self, request, *args, **kwargs):
        context = self.kwargs
        form = self.form_class(request.POST)
        if form.is_valid():
            payload = {
                'asset-map-out' : form.cleaned_data.get('status'),
                'asset-tag' : form.cleaned_data.get('scan_asset_tag'),
                'description' : form.cleaned_data.get('description'),
            }
            response = MapOutAsset(payload, user=request.user).process()
            context['msg'] = response
        context['form'] = form
        return TemplateResponse(request, self.template_name, context)



class AssetMapOutUpdateView(UpdateView):
    fields = ('approved',)
    model =  AssetMapOut
    context_obj_name = 'obj'
    slug_field = 'pk'
    slug_url_kwarg = 'pk'
    template_name = "asset_mapout_approval.html"

    def get_context_data(self, *args, **kwargs):
        context = super(AssetMapOutUpdateView, self).get_context_data(*args, **kwargs)
        context['obj'] = self.get_object()
        return context

    def approve_mapout(self, instance: AssetMapOut):
        payload = {
            'asset-map-out' : instance.status,
            'asset-tag' : instance.scan_asset_tag,
            'description' : instance.description,
        }
        technician = getattr(instance, 'assigned_technician')
        mapout_manager = MapOutAsset(
            payload,
            tech_username = getattr(technician, 'codereadr_username', None),
            user = getattr(instance, 'assigned_user')
        )
        response = mapout_manager.process(instance)
        return (mapout_manager, response)

    def post(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        form = form_class(request.POST)
        obj = self.get_object()
        if form.is_valid():
            approved = form.cleaned_data.get('approved')
            if approved:
                mapout_manager, response = self.approve_mapout(obj)
                if mapout_manager.valid:
                    msg = 'Asset Mapout successfully approved'
                else:
                    msg = response
            else:
                msg = 'Asset Mapout NOT approved'
            obj.approved = approved
            obj.save()
        else:
            msg = 'Invalid Form'
        return HttpResponse(msg)


class SwapTagLogUpdateView(UpdateView):
    fields = ('approved',)
    model =  SwapTagLog
    context_obj_name = 'obj'
    slug_field = 'pk'
    slug_url_kwarg = 'pk'
    template_name = "swap_tag_approval.html"

    def get_context_data(self, *args, **kwargs):
        context = super(SwapTagLogUpdateView, self).get_context_data(*args, **kwargs)
        context['obj'] = self.get_object()
        return context

    def approve_swap(self, instance: SwapTagLog, request):
        payload = {
            'current_tag' : instance.current_tag,
            'new_tag' : instance.new_tag,
        }
        tech_username = getattr(instance, 'tech_username')
        swap_manager = SwapTagManager(
            payload,
            tech_username = tech_username,
            user = request.user
        )
        response = swap_manager.process(requires_approval=False)
        return (swap_manager, response)

    def post(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        form = form_class(request.POST)
        obj = self.get_object()
        if form.is_valid():
            approved = form.cleaned_data.get('approved')
            if approved:
                swap_manager, response = self.approve_swap(obj, request)
                if swap_manager.valid:
                    msg = 'Tag Swap successfully approved'
                else:
                    msg = response
            else:
                msg = 'Tag Swap NOT approved'
            obj.approved = approved
            obj.save()
        else:
            msg = 'Invalid Form'
        return HttpResponse(msg)


class SlotLabelCheckTriggerView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.BasicAuthentication]
    
    def post(self, request, *args, **kwargs):
        SlotLabelCheckThread().start()
        return Response(status=status.HTTP_201_CREATED)


class MachineMeterReadingCreateView(LoginRequiredMixin, CreateView):
    template_name = 'machine_meter_reading_create.html'

    def get(self, request, *args, **kwargs):
        context = {'form': MachineMeterReadingForm()}
        return TemplateResponse(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        form = MachineMeterReadingForm(request.POST, request.FILES)
        context = self.kwargs
        if form.is_valid():
            obj = form.save()
            context['msg'] = 'Successfully created Meter Reading update Request. Call to the office for approval'
        context['form'] = form
        return TemplateResponse(request, self.template_name, context)