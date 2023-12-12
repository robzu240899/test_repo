import logging
from typing import List
import time
import requests
import os 
import csv
from collections import namedtuple, OrderedDict
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from itertools import groupby
from io import BytesIO
from tablib import Dataset, Databook
from django.core.mail import EmailMessage
from django.db.models import Q,Count,Min,Max
from main import settings
from reporting.models import CustomPriceHistory, MeterRaise, UpcomingMeterRaiseNotification, OutOfOrderReportLog, AnomalyDetectionJobTracker
from reporting.reliability import helpers
from revenue.models import FailedTransactionMatch
from revenue.enums import TransactionType
from roommanager.models import Slot, LaundryGroup, MachineSlotMap, Machine
from roommanager.enums import SlotType
from outoforder.enums import MachineStateType, SlotErrorType
from outoforder.models import SlotStateError, SlotState
from outoforder.config import ErrorMarkerConfig
from upkeep.manager import UpkeepAssetManager
from .enums import SLOT_STATE_ERROR_HEADERS, TIME_RANGE_HEADERS, METER_RAISES_HEADERS, UPKEEP_SYNCING_HEADERS, FLICKERING_ERRORS

logger = logging.getLogger()


class NewBaseReport():

    def __init__(self):
        self.initialize_dataset()

    def get_dataset_title(self):
        return getattr(self, 'dataset_title', None)

    def get_dataset_headers(self):
        assert hasattr(self, 'dataset_headers')
        return getattr(self, 'dataset_headers')

    def initialize_dataset(self):
        self.dataset = Dataset()
        self.dataset.title = self.get_dataset_title()
        self.dataset.headers = self.get_dataset_headers()

    def run(self):
        raise NotImplementedError


class ZeroPriceCycleManager():
    cycle_headers = [
        'equipment_name',
        'room_name',
        'equipment_fascard_id',
        'cycle_type',
        'cycle_detection_date',
        'price',
        'error_message',
    ]

    def __init__(self):
        self.dataset = Dataset()
        self.dataset.title = 'Pricing Errors'
        self.dataset.headers = self.cycle_headers

    def format_as_dict(self, cycle):
        cycle_data = {
                    'room_name': cycle.laundry_room.display_name, 
                    'equipment_name': cycle.equipment_type.machine_text,
                    'equipment_fascard_id': cycle.equipment_type.fascard_id,
                    'cycle_type': cycle.cycle_type,
                    'cycle_detection_date': cycle.detection_date,
                    'price': cycle.price
        }
        return cycle_data

    def __equipmenttype_as_dict(self, equipment_type):
        d = {}
        for f in self.equipment_type_fields:
            d[f] = getattr(equipment_type, f, None)
        return d

    def add_to_dataset(self, equipment_type, cycles, err=None):
        assert equipment_type
        assert cycles

        for cycle in cycles:
            cycle_data = self.format_as_dict(cycle)
            if err:
                cycle_data.update({'error_message':err})
            self.dataset.append([cycle_data.get(header, '') for header in self.cycle_headers])
        self.dataset.append_separator('\n')

    def run(self):
        msm_query = MachineSlotMap.objects.filter(
            is_active=True,
            machine__equipment_type__isnull=False
            ).values_list(
                'machine__equipment_type__fascard_id',
                flat=True
            ).distinct()

        active_equipment_types = [MachineSlotMap.objects.filter()]
        queryset = CustomPriceHistory.objects.filter(laundry_room__is_active=True)
        free_in_equipmentname_cycles = queryset.filter(
            equipment_type__machine_text__icontains = '*GRATIS*'
        )
        for equipment_type, cycles in groupby(free_in_equipmentname_cycles, lambda x: x.equipment_type):
            cycles_list = list(cycles)
            if all([cycle.price == 0 for cycle in cycles_list]):
                err_msg = 'The equipment type is totally gratis while it is labeled just as gratis'
            elif any([cycle.price == 0 for cycle in cycles_list]):
                continue
            else:
                err_msg = "GRATIS in name but none zero-priced cycles"
            self.add_to_dataset(equipment_type, cycles_list, err=err_msg)
        
        totally_free_cycles = queryset.filter(
            equipment_type__machine_text__icontains = '*TOTALLY GRATIS*'
        )
        for equipment_type, cycles in groupby(totally_free_cycles, lambda x: x.equipment_type):
            cycles_list = list(cycles)
            if all([cycle.price == 0 for cycle in cycles_list]):
                continue
            else:
                err_msg = 'At least one cycle price is not zero in a totally free equipment'
                self.add_to_dataset(equipment_type, cycles_list, err=err_msg)

        nofree_in_equipmentname_cycles = queryset.filter(
            price=0).exclude(
            equipment_type__machine_text__icontains='gratis')

        #Include only those equipment types that actually have an active MachineSLotMap
        #in a room.
        valid_no_free = []
        for price_history in nofree_in_equipmentname_cycles:
            active_slot_maps = MachineSlotMap.objects.filter(
                is_active = True,
                slot__laundry_room=price_history.laundry_room,
                slot__equipment_type=price_history.equipment_type
            )

            newer = queryset.filter(
                laundry_room=price_history.laundry_room, 
                equipment_type=price_history.equipment_type,
                cycle_type=price_history.cycle_type,
                id__gt=price_history.id,
            ).order_by('-id').first()

            if any(active_slot_maps) and not newer:
                valid_no_free.append(price_history.id)

        #TODO: Make sure you are only including the latest PricingHIstory of its kind
        #there might be two different pricing histories of the same feature in the database
        #only the last ingested is the one that matters.

        #Get equipments in which there is at least one cycle with 0 price. Check if last one is zero
        nofree_in_equipmentname_cycles = nofree_in_equipmentname_cycles.filter(id__in = valid_no_free)
        unique_equipment_types = nofree_in_equipmentname_cycles.values_list('equipment_type', flat=True)

        
        for equipment_type, cycles in groupby(nofree_in_equipmentname_cycles, lambda x: x.equipment_type):
            cycles_list = list(cycles)
            err_msg = 'Zero priced cycle in a none-free equipment type'
            self.add_to_dataset(equipment_type, cycles_list, err=err_msg)
            
        return self.dataset
            #print ("Equipment Type: {}".format(equipment_type))
            #print ("Cycles: {}")
            #for cycle in list(cycles):
            #    print ("Laundry Room: {}. CycleType: {}".format(cycle.laundry_room, cycle.cycle_type))

            
            #for cycle in list(cycles):
            #    print ("Laundry Room: {}. Price: {}. EquipmentTypeId: {}. Type: {}".format(
            #        cycle.laundry_room, cycle.price, cycle.equipment_type.id, cycle.cycle_type))

        #zero_price_errors = [self.__format_as_dict(cycle) for cycle in CustomPriceHistory.objects.filter(**self.zero_priced_filters)]
        #return zero_price_errors


class NewFailedTransactionMatchReport(NewBaseReport):
    transaction_headers = [
        'external_fascard_id',
        'utc_transaction_time',
        'external_fascard_user_id',
        'transaction_type',
        'credit_card_amount',
        'dirty_name'
    ]

    extra_headers = [
        'url',
    ]

    dataset_headers = transaction_headers + extra_headers
    dataset_title = 'Failed Transaction Matches'

    @classmethod
    def as_row(cls, record: FailedTransactionMatch) -> list:
        row = []
        for record_header in cls.transaction_headers:
            if hasattr(record.transaction, record_header):
                row.append(getattr(record.transaction,record_header))
        if record.transaction:        
            tx_id = record.transaction.id
            url = 'https://system.aceslaundry.com/admin/revenue/laundrytransaction/{}/'.format(
                tx_id
            )
        else: url = "Unknown Tx URL"
        row.append(url)
        return row

    def run(self):
        records = FailedTransactionMatch.objects.filter(solved=False)
        for record in records:
            self.dataset.append(self.as_row(record))


class TimeRangeErrorsReport(NewBaseReport):
    dataset_title = 'Time Range Errors'
    dataset_headers = TIME_RANGE_HEADERS

    def _filter_errors(self, starting_datetime):
        sloterrors_queryset = SlotStateError.objects.filter(
                slot_state__local_start_time__gt=starting_datetime,
                error_type=-2,
                slot_state__duration__gt=5,
        )
        return sloterrors_queryset

    def _find_errors_in_time_range(self, hours_ago):
        seq_memory = {}
        #slots_memory = []
        starting_datetime = datetime.today() - relativedelta(hours=hours_ago)
        all_errors = self._filter_errors(starting_datetime)

        if all_errors.count() < 2:
            return None

        for slot, slot_errors in groupby(all_errors, lambda x: x.slot_state.slot):
            slot_errors_list = list(slot_errors)
            if not slot.slot_fascard_id in self.slots_memory and len(slot_errors_list) > 1:
                mapped_slot_errors_list = [helpers.map_slot_error_as_dict(slot_error) for slot_error in slot_errors_list]
                seq_memory[slot.slot_fascard_id] = mapped_slot_errors_list
                self.slots_memory.append(slot.slot_fascard_id)
        return seq_memory

    def run(self, hours_ago, slots_memory=None):
        assert hours_ago is not None
        self.slots_memory = slots_memory
        self.dataset.title = self.dataset_title + ' ({})'.format(hours_ago)
        hour_range_errors = self._find_errors_in_time_range(hours_ago)
        
        if hour_range_errors is None:
            return

        for slot_fascard_id, slot_errors in hour_range_errors.items():
            for error in slot_errors:
                row = []
                for header in self.dataset_headers:
                    try:
                        if header == "error(s)":
                            err = ",".join([str(x) for x in error[header]])
                            row.append(err)
                        else:
                            row.append(error[header])
                    except Exception as e:
                        row.append('')
                self.dataset.append(row)
            self.dataset.append_separator('\n')


class FlickeringReport(NewBaseReport):
    universal_Q =  Q(slot_state__slot__is_active=True) & Q(slot_state__slot__laundry_room__is_active=True)
    #NB: no longer user long transaction gap!
    nonreported_Q = universal_Q  &  Q(slot_state__end_time=None)
    base_dataset_headers = [
        'building_name',
        'display_name',
        'start_time',
        'end_time', 
    ]
    extra_dataset_headers = ['maintainx_asset_url']
    dataset_headers = base_dataset_headers + extra_dataset_headers
    dataset_title = 'Flickering'

    def _find_flickering_errors(self):
        lookback_until =  datetime.utcnow() - timedelta(hours=24)
        flickering =  SlotStateError.objects.filter(
            self.universal_Q,
            error_type=SlotErrorType.FLICKERING,
            slot_state__start_time__gte=lookback_until
        ).values('slot_state__slot__id').annotate(
            num_times=Count('id'),
            start_time=Min('slot_state__start_time'),
            end_time=Max('slot_state__end_time'),
            display_name=Max('slot_state__slot__web_display_name'),
            building_name=Max('slot_state__slot__laundry_room__display_name')
        ).filter(num_times__gte=4) #TODO: make dynamic
        return flickering

    def run(self):
        flickering_errors = self._find_flickering_errors()
        for error in flickering_errors:
            this_row = [error.get(header) for header in self.base_dataset_headers]
            slot = Slot.objects.get(id=error.get('slot_state__slot__id'))
            this_row.append(helpers.get_maintainx_url(slot))
            #rows.append(this_row)
            self.dataset.append(this_row)


class NonFlickeringReport(NewBaseReport):
    dataset_headers = SLOT_STATE_ERROR_HEADERS
    dataset_title = 'Current Errors'
    universal_Q =  Q(slot_state__slot__is_active=True) & Q(slot_state__slot__laundry_room__is_active=True)
    nonreported_Q = universal_Q  &  Q(slot_state__end_time=None)

    @classmethod 
    def _get_last_run_start(self,slot):
        x = slot.slot_set.filter(slot_status=MachineStateType.RUNNING).order_by('-local_start_time').first()
        if x is None: return None 
        else: return x.local_start_time

    def _find_non_flickering_errors(self,universalQ):
        non_flickering_errors = SlotStateError.objects.filter(
            universalQ).exclude(error_type__in=[SlotErrorType.FLICKERING, SlotErrorType.DISABLED])
        return  [nfe for nfe in non_flickering_errors]
    
    def _find_double_barreled_errors(self):
        cuttoff_case_when_statement = '''
        case when idle_cutoff_seconds is null then %s
        when idle_cutoff_seconds > %s then %s
        when idle_cutoff_seconds < %s then %s 
        else idle_cutoff_seconds
        end 
        ''' % (ErrorMarkerConfig.IDLE_DEFAULT_SECONDS,
               ErrorMarkerConfig.IDLE_MAX_SECONDS,ErrorMarkerConfig.IDLE_MAX_SECONDS,
               ErrorMarkerConfig.IDLE_MIN_SECONDS,ErrorMarkerConfig.IDLE_MIN_SECONDS)
        
        sql = '''
            select *
            from slot b join laundry_room c on b.laundry_room_id = c.id 
            WHERE slot_type = '%s' and b.is_active=1 and c.is_active=1
            AND (last_run_time is null OR UTC_TIMESTAMP() > DATE_SUB(last_run_time, INTERVAL -%s SECOND));
            ''' % (SlotType.DOUBLE,cuttoff_case_when_statement)
        slots =  Slot.objects.raw(sql)
        SlotStateErrorMockup = namedtuple('SlotStateErrorMarkup',['slot_state','error_message'])
        SlotStateMockup = namedtuple('SlotStateMarkup',['slot','slot_id','start_time','end_time'])
        slot_state_errors = []
        for slot in slots:
            slot_state = SlotStateMockup(slot,slot.id,slot.last_run_time,None)
            slot_state_error = SlotStateErrorMockup(slot_state,'Double Barreled Idle')
            slot_state_errors.append(slot_state_error)
        return slot_state_errors

    def _rollup_slot_errors(self,non_flickering,double_barreled):
        slot_errors_memory = {}
        errors = non_flickering+double_barreled
        for error in errors:
            last_run_time = self._get_last_run_start(error.slot_state.slot)
            if last_run_time:
                error_start_time =last_run_time
            else:
                error_start_time = error.slot_state.start_time
            
            if error.slot_state.slot_id not in slot_errors_memory:
                error_data = helpers.map_slot_error_as_dict(error, error_start_time)

                slot_errors_memory[error.slot_state.slot_id] = error_data

            else:
                slot_errors_memory[error.slot_state.slot_id]['error(s)'].add(error.error_message)
    
                error_in_memory = slot_errors_memory[error.slot_state.slot_id]
                current_end_time = error_in_memory.get('end time')
                if current_end_time is None:
                    pass
                elif error.slot_state.end_time is None:
                    error_in_memory['end time'] = None
                elif error.slot_state.end_time > current_end_time:
                    error_in_memory['end time'] = error.slot_state.end_time

                current_start_time = error_in_memory.get('start time', None)
                if not current_start_time:
                    error_in_memory['start time'] = error_start_time
                elif error_start_time < current_start_time:
                    error_in_memory['start_time'] = error_start_time
            
        for slot_error in slot_errors_memory.values():
            slot_error['error(s)'] = ','.join(slot_error['error(s)'])
        return slot_errors_memory

    def run(self):
        #Generate Error Report CSV
        #universal_Q =  Q(slot_state__slot__is_active=True) & Q(slot_state__slot__laundry_room__is_active=True)
        #NB: no longer user long transaction gap!
        #nonreported_Q = universal_Q  &  Q(slot_state__end_time=None) # | ( Q(error_type=SlotErrorType.LONG_TRANSACTION_GAP) & Q(slot_state__end_time__gte=two_days_ago)) ) 

        non_flickering_errors = self._find_non_flickering_errors(self.nonreported_Q)
        double_barreled_idle_errors = self._find_double_barreled_errors()
        rolledup_non_flickering = self._rollup_slot_errors(non_flickering_errors,double_barreled_idle_errors)

        for error in rolledup_non_flickering.values():
            this_row = []
            for header in self.dataset_headers:
                try:
                    this_row.append(error[header])
                except:
                    this_row.append('')
            self.dataset.append(this_row)


class DisabledMachinesReport(NonFlickeringReport):
    dataset_headers = SLOT_STATE_ERROR_HEADERS
    dataset_title = 'Disabled Machines Errors'
    universal_Q =  Q(slot_state__slot__is_active=True) & Q(slot_state__slot__laundry_room__is_active=True)
    nonreported_Q = universal_Q  &  Q(slot_state__end_time=None)

    def _find_non_flickering_disabled_errors(self, universalQ):
        non_flickering_errors = SlotStateError.objects.filter(universalQ, error_type=SlotErrorType.DISABLED)
        return [nfe for nfe in non_flickering_errors]

    def run(self):
        disabled_errors = self._find_non_flickering_disabled_errors(self.nonreported_Q)
        errors = self._rollup_slot_errors(disabled_errors,[])
        for error in errors.values():
            this_row = []
            for header in self.dataset_headers:
                try:
                    this_row.append(error[header])
                except:
                    this_row.append('')
            self.dataset.append(this_row)


class MeterRaisesManager(NewBaseReport):
    dataset_headers = METER_RAISES_HEADERS
    dataset_title = "Upcoming Meter Raises"
    base_model = UpcomingMeterRaiseNotification
    notification_url = 'https://system.aceslaundry.com/admin/reporting/upcomingmeterraisenotification/{}/change/'

    def run(self):
        month_from_now = date.today() + relativedelta(months=2)
        upcoming_scheduled_raises = MeterRaise.objects.filter(
            scheduled_date__gte=date.today(),
            scheduled_date__lte=month_from_now,
            notification__isnull=True
        )
        for meter_raise in upcoming_scheduled_raises:
            self.base_model.objects.create(
                meter_raise = meter_raise
            )
        notifications_queryset = self.base_model.objects.filter(
            completed=False,
            meter_raise__scheduled_date__lte=month_from_now
        ).order_by('meter_raise__scheduled_date')
        for notification in notifications_queryset:
            bg_url = self.notification_url.format(notification.id)
            row = [
                notification.meter_raise.billing_group.display_name,
                notification.meter_raise.scheduled_date,
                notification.meter_raise.raise_limit,
                bg_url
            ]
            self.dataset.append(row)


class AssetSyncingReport(NewBaseReport):
    dataset_headers = UPKEEP_SYNCING_HEADERS
    dataset_title = 'Upkeep Syncing'
    asset_base_url = 'https://app.onupkeep.com/#/app/assets/view/{}'
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
                row = [
                    msm.slot.laundry_room.display_name,
                    UpkeepAssetManager._build_asset_name(
                        machine,
                        related_slots,
                        msm.slot.laundry_room
                    )[0],
                    machine.asset_code,
                    self.asset_base_url.format(machine.upkeep_id)
                ]
                self.dataset.append(row)


class InactivityReport(NewBaseReport):
    dataset_headers = ['slot', 'duration', 'maintainx_asset_url', 'fascard_url']
    dataset_title = 'Inactivity Report'

    def get_dates(self, slot, days):
        assert days % 3 == 0
        lookback_until = datetime.now() - timedelta(days=days)
        dates_queryset = slot.laundrytransaction_set.filter(
            transaction_type = TransactionType.VEND,
            local_transaction_time__gte=lookback_until,
        ).order_by('-local_transaction_time').values_list('local_transaction_time', flat=True)
        if dates_queryset:
            return dates_queryset
        else:
            if days >= 360:
                return dates_queryset
            return self.get_dates(slot, days+30)

    def run(self):
        import numpy as np
        #lookback_until = datetime.now() - timedelta(days=90)
        errors_memory = {}
        lookback_days = 90
        self.dict_sorter = OrderedDict()
        for slot in Slot.objects.filter(is_active=True, laundry_room__is_active=True):
            dates = self.get_dates(slot, lookback_days)
            dates = list(dates)
            dates.insert(0, datetime.now())
            slot_gaps = list()
            latest = 0
            for i in range(len(dates)-1):
                if len(slot_gaps) == 9: break
                diff = dates[i] - dates[i+1]
                if diff.total_seconds() < 1200: continue
                #print ("{}   --   {}      -->   {}".format(dates[i], dates[i+1], diff))
                slot_gaps.append(diff.total_seconds())
                if len(slot_gaps) == 1: latest = diff
            
            if not len(slot_gaps) > 1: continue
            avg = sum(slot_gaps[1:]) / len(slot_gaps[1:])
            sd = np.std(slot_gaps[1:])
            if slot_gaps[0] > 690000 and slot_gaps[0] > (avg + (sd*2)):
                row = [
                    str(slot),
                    str(latest),
                    helpers.get_maintainx_url(slot),
                    helpers.get_slot_fascard_url(slot)
                ]
                latest_diff_total = latest.total_seconds()
                if latest_diff_total in self.dict_sorter:
                    while True:
                        latest_diff_total += 1
                        if latest_diff_total not in self.dict_sorter: break
                self.dict_sorter[latest_diff_total] = row
        for k in sorted(self.dict_sorter.keys()): self.dataset.append(self.dict_sorter[k])


class SatelliteOfflineReport(NewBaseReport):
    dataset_headers = (
        'Satellite',
        'Current Status Time',
        '% DOWNTIME - Last 24 hours',
    )
    dataset_title = 'Satellite Report'

    def run(self):
        #url = 'http://127.0.0.1:8000/serve-online-hourly-report/'
        #r = requests.get(url, auth=('eljach','cauchomakia'), timeout=240)
        url = 'http://satellite.aceslaundry.com/serve-online-hourly-report/'
        r = requests.get(url, auth=('satelliteuser','QJrYbTbUWk'), timeout=600) #10 minutes
        if r.status_code == 500:
            self.dataset = Dataset()
            self.dataset.headers = ('Err Msg',)
            self.dataset.append([r.text])
            return
        temp_result = BytesIO()
        chunk_size = 2000 #bytes
        for chunk in r.iter_content(chunk_size):
            temp_result.write(chunk)
        temp_dataset = Dataset().load(temp_result.getvalue().decode("utf-8"), format='csv')
        self.dataset.csv = temp_dataset.csv


class AnomalyDetectionReport(NewBaseReport):
    dataset_headers = ['Anomaly']
    dataset_title = 'Probability-Based Anomalies'

    def run(self):
        self.dataset = Dataset()
        job_tracker = AnomalyDetectionJobTracker.objects.last()
        if not job_tracker.jobs_being_tracked.all().count() == job_tracker.jobs_processed: return
        anomalies = job_tracker.jobs_being_tracked.filter(anomaly_detected=True)
        for anomaly in anomalies: self.dataset.append([anomaly.msg])


class OOOReportManager():
    reports_managers = [
        NonFlickeringReport,
        DisabledMachinesReport,
        SatelliteOfflineReport,
        InactivityReport,
        AnomalyDetectionReport,
        ZeroPriceCycleManager,
        MeterRaisesManager,
        FlickeringReport,
        NewFailedTransactionMatchReport
    ]

    def __init__(self):
        self.databook = Databook()
        self.execution_log = OutOfOrderReportLog.objects.create()

    @classmethod
    def decide_to_run(cls) -> bool:
        """
        If an OOO report was run less than 5 hours ago, avoid running one again.

        Called only from tied-run processor.
        """
        latest = OutOfOrderReportLog.objects.filter(successfully_sent=True).order_by('-timestamp').first()
        if not latest: return True
        if (datetime.now() - latest.timestamp).seconds > 18000: return True
        else: return False

    def set_file_name(self):
        tm = datetime.now()
        tm = tm.strftime('%Y_%m_%d_%H_%M_%S')
        self.file_name = os.path.join(settings.BASE_DIR,'OutOfOrder_%s.xls' % tm)

    def email_report(self):
        subject = self.title
        body = self.body
        to_list = settings.OUT_OF_ORDER_TO_LIST
        #to_list = ['juaneljach10@gmail.com']
        from_email = settings.DEFAULT_FROM_EMAIL
        email = EmailMessage(subject, body, from_email, to_list)
        if self.file_name:
            email.attach_file(self.file_name)
        email.send(fail_silently=False)
        self.execution_log.successfully_sent = True
        self.execution_log.save()

    def _generate_body_and_title(self):
        room_list = list(set([result for result in self.NonFlickeringReport['building name']]))
        if len(room_list) >0:
            room_list = '\n'.join(room_list)
            self.body = 'Rooms with new errors: %s' % room_list
            self.title = 'Out of Order Report: New Errors on %s'
        else:
            self.body = 'No unreported errors.'
            self.title = 'Out of Order Report: No New Errors on %s'
        self.title = self.title % settings.ENV_TYPE

    def to_xls(self):
        assert self.file_name, "file_name must not be empty"
        with open(self.file_name,'wb') as f:
            f.write(self.databook.export("xls"))

    def generate(self):
        for report in self.reports_managers:
            try:
                start = time.time()
                ins = report()
                ins.run()
                self.databook.add_sheet(ins.dataset)
                end = time.time()
                logger.info(f"Processed {ins.__class__.__name__} in: {(end-start)} seconds")
                self.__dict__[report.__name__] = ins.dataset
            except Exception as e:
                logger.error(f"Failed processing step {report} with error {e}")

        slots_memory = []
        for hours_ago in [24,48,72]:
            try:
                start = time.time()
                time_range = TimeRangeErrorsReport()
                time_range.run(hours_ago, slots_memory)
                slots_memory = time_range.slots_memory
                self.databook.add_sheet(time_range.dataset)
                end = time.time()
                logger.info(f"Processed 'TimeRangeErrorsReport'-{hours_ago} in: {(end-start)} seconds")
            except Exception as e:
                pass

        self.set_file_name()
        self.to_xls()
        self._generate_body_and_title()
        self.email_report()



#NOTE: BELOW IS THE OLD VERSION OF OOO REPORT. It's been deprecated



class FailedTransactionMatchReport():
    transaction_headers = [
        'external_fascard_id',
        'utc_transaction_time',
        'external_fascard_user_id',
        'transaction_type',
        'credit_card_amount',
        'dirty_name'
    ]

    extra_headers = [
        'url',
    ]

    @classmethod
    def as_row(cls, record):
        row = []
        for record_header in cls.transaction_headers:
            if hasattr(record.transaction, record_header):
                row.append(getattr(record.transaction,record_header))
        
        tx_id = record.transaction.id
        url = 'https://system.aceslaundry.com/admin/revenue/laundrytransaction/{}/'.format(
            tx_id
        )
        row.append(url)
        return row

    @classmethod
    def report(cls):
        dataset = Dataset()
        dataset.title = 'Failed Transaction Matches'
        dataset.headers = cls.transaction_headers + cls.extra_headers
        records = FailedTransactionMatch.objects.filter(solved=False)
        for record in records:
            dataset.append(cls.as_row(record))
        return dataset

class BaseReport():
    
    def __init__(self):
        self.file_name = None
        self.title = None
        self.results = []  
        self.to_list = []
    
    def run_report(self,**kwargs):
        self.generate(**kwargs)
        self.set_file_name()
        #self.to_csv()
        self.to_xls()
        #self.email_report()
            
    def to_csv(self,delimiter=','):
        assert self.file_name, "file_name must not be empty"
        with open(self.file_name,'wb') as f:
            writer = csv.writer(f,delimiter=delimiter)
            for row in self.results:
                writer.writerow(row)
    
    def to_xls(self):
        assert self.file_name, "file_name must not be empty"
        with open(self.file_name,'wb') as f:
            f.write(self.results.export("xls"))
    
    def email_report(self):
        subject = self.title
        body = self.body
        to_list = settings.OUT_OF_ORDER_TO_LIST
        from_email = settings.DEFAULT_FROM_EMAIL
        email = EmailMessage(subject, body, from_email, to_list)
        if self.file_name:
            email.attach_file(self.file_name)
        email.send(fail_silently=False)



#NOTE: Below is deprecated

class OOOReport(BaseReport):
    
    def generate(self):
        self.set_file_name()
        #Generate Error Report CSV
        two_days_ago = datetime.utcnow()-timedelta(days=2)
        universal_Q =  Q(slot_state__slot__is_active=True) & Q(slot_state__slot__laundry_room__is_active=True)
        #NB: no longer user long transaction gap!
        nonreported_Q = universal_Q  &  Q(slot_state__end_time=None) # | ( Q(error_type=SlotErrorType.LONG_TRANSACTION_GAP) & Q(slot_state__end_time__gte=two_days_ago)) ) 
        
        non_flickering_errors = self._find_non_flickering_errors(nonreported_Q)
        double_barreled_idle_errors = self._find_double_barreled_errors()
        rolledup_non_flickering = self._rollup_slot_errors(non_flickering_errors,double_barreled_idle_errors)     
        flickering_errors = self._find_flickering_errors(universal_Q)

        hours_range_datasets = self._find_errors_in_time_range(72, 24)
        zero_price_errors_dataset = ZeroPriceCycleManager().run()

        failed_transactions_matches = FailedTransactionMatchReport().report()       
        
        self._generate_results(
            rolledup_non_flickering,
            flickering_errors,
            hours_range_datasets,
            zero_price_errors_dataset,
            failed_transactions_matches) #Creates self.resuls
        #Generate List of buildings with current errors
        self._generate_body_and_title()

    def set_file_name(self):
        tm = datetime.now()
        tm = tm.strftime('%Y_%m_%d_%H_%M_%S')
        self.file_name = os.path.join(settings.BASE_DIR,'OutOfOrder_%s.xls' % tm)
      
    def _find_non_flickering_errors(self,universalQ):
        non_flickering_errors = SlotStateError.objects.filter(universalQ).exclude(error_type=SlotErrorType.FLICKERING)
        return  [nfe for nfe in non_flickering_errors]

    def _find_flickering_errors(self,universalQ):
        lookback_until =  datetime.utcnow() - timedelta(hours=24)
        flickering =  SlotStateError.objects.filter(
                    universalQ,error_type=SlotErrorType.FLICKERING,slot_state__start_time__gte=lookback_until).values(
                    'slot_state__slot__id').annotate(num_times=Count('id'),start_time=Min('slot_state__start_time'),end_time=Max('slot_state__end_time'),
                    display_name=Max('slot_state__slot__web_display_name'),building_name=Max('slot_state__slot__laundry_room__display_name')).filter(num_times__gte=4) #TODO: make dynamic           
        return flickering
    
    def _find_double_barreled_errors(self):
        cuttoff_case_when_statement = '''
        case when idle_cutoff_seconds is null then %s
        when idle_cutoff_seconds > %s then %s
        when idle_cutoff_seconds < %s then %s 
        else idle_cutoff_seconds
        end 
        ''' % (ErrorMarkerConfig.IDLE_DEFAULT_SECONDS,
               ErrorMarkerConfig.IDLE_MAX_SECONDS,ErrorMarkerConfig.IDLE_MAX_SECONDS,
               ErrorMarkerConfig.IDLE_MIN_SECONDS,ErrorMarkerConfig.IDLE_MIN_SECONDS)
        
        sql = '''
            select *
            from slot b join laundry_room c on b.laundry_room_id = c.id 
            WHERE slot_type = '%s' and b.is_active=1 and c.is_active=1
            AND (last_run_time is null OR UTC_TIMESTAMP() > DATE_SUB(last_run_time, INTERVAL -%s SECOND));
            ''' % (SlotType.DOUBLE,cuttoff_case_when_statement)
        slots =  Slot.objects.raw(sql)
        SlotStateErrorMockup = namedtuple('SlotStateErrorMarkup',['slot_state','error_message'])
        SlotStateMockup = namedtuple('SlotStateMarkup',['slot','slot_id','start_time','end_time'])
        slot_state_errors = []
        for slot in slots:
            slot_state = SlotStateMockup(slot,slot.id,slot.last_run_time,None)
            slot_state_error = SlotStateErrorMockup(slot_state,'Double Barreled Idle')
            slot_state_errors.append(slot_state_error)
        return slot_state_errors

    def _filter_errors(self, starting_datetime):
        sloterrors_queryset = SlotStateError.objects.filter(
                slot_state__local_start_time__gt=starting_datetime,
                error_type=-2,
                slot_state__duration__gt=5,
        )
        return sloterrors_queryset

    def map_slot_error_as_dict(self, slot_error, error_start_time=None):
        if not error_start_time:
            error_start_time = slot_error.slot_state.start_time
        try:
            seconds = getattr(slot_error.slot_state, 'duration', 0)
            if seconds == 0 or seconds == None:
                final_duration = 0
                time_str = ''
            elif seconds <= 120:
                final_duration = seconds
                time_str = 'seconds'
            elif seconds > 120 and seconds <= 5400:
                final_duration = seconds / 60.0
                time_str = 'minutes'
            elif seconds >= 5400 and seconds <=86400:
                final_duration = ((seconds / 60.0) / 60.0)
                time_str = 'hours'
            elif seconds > 86400:
                final_duration = (((seconds / 60.0) / 60.0) / 12.0)
                time_str = 'days'
                #return in minutes
            duration = "{:.2f} {}".format(final_duration, time_str)
        except:
            duration = ''
        error_data = {
            'building name':slot_error.slot_state.slot.laundry_room.display_name,
            'display name':slot_error.slot_state.slot.web_display_name,
            'fascard_id': slot_error.slot_state.slot.slot_fascard_id,
            'internal_id': slot_error.slot_state.slot.id,
            'error(s)':set([slot_error.error_message]),
            'start time': error_start_time,
            'end time':slot_error.slot_state.end_time,
            'duration': duration,
            'fascard_url':self._get_slot_fascard_url(slot_error.slot_state.slot),
            'upkeep_create_work_order':self.get_upkeep_url(slot_error.slot_state.slot)
        }
        if isinstance(slot_error, SlotStateError):
            #if machine status is OK it means that the mlvmacherror was not ingested properly
            #and the status_text was setted by default to OK. So we better don't show it in the report
            if not slot_error.slot_state.mlvmacherror_description == 0:
                error_data['mlvmacherror_description'] = slot_error.get_mlv_error()
            error_data['slot_status_text'] =  slot_error.get_status_text()
        
        return error_data

    def _find_errors_in_time_range(self, hours, steps):
        seq_memory = {}
        end_value = hours + steps
        slots_memory = []

        for iter_index, hours_range in enumerate(range(steps, end_value, steps)):
            seq_memory[hours_range] = {}
            starting_datetime = datetime.today() - relativedelta(hours=hours_range)
            all_errors = self._filter_errors(starting_datetime)

            if all_errors.count() < 2:
                continue

            for slot, slot_errors in groupby(all_errors, lambda x: x.slot_state.slot):
                slot_errors_list = list(slot_errors)
                if not slot.slot_fascard_id in slots_memory and len(slot_errors_list) > 1:
                    mapped_slot_errors_list = list(map(self.map_slot_error_as_dict, slot_errors_list))
                    seq_memory[hours_range][slot.slot_fascard_id] = mapped_slot_errors_list
                    slots_memory.append(slot.slot_fascard_id)
        
        return seq_memory


            # for error in slot_errors:
            #     slot = error.slot_state.slot
            #     seq_memory[hours_range] = {slot.slot_fascard_id:[]}
            #     first = not iter_index #any number but 0 is True, therefore not True = false to first check
            #     if first:
            #         seq_memory[hours_range][slot.slot_fascard_id].append(error)
            #         slots_memory.append(slot)
            #     else:
            #         if not slot in slots_memory:
            #             seq_memory[hours_range][slot.slot_fascard_id].append(error)
            
    def _generate_body_and_title(self):
        room_list = list(set([result for result in self.errors_results_tablib['building name']]))
        if len(room_list) >0:
            room_list = '\n'.join(room_list)
            self.body = 'Rooms with new errors: %s' % room_list
            self.title = 'Out of Order Report: New Errors on %s'
        else:
            self.body = 'No unreported errors.'
            self.title = 'Out of Order Report: No New Errors on %s'
        self.title = self.title % settings.ENV_TYPE

    # def _get_machines_with_flickering_errors(self):
    #     three_days = date.today() - relativedelta(days=3)
    #     q = SlotStateError.objects.filter(
    #         slot_state__local_start_time__gt=days,
    #         slot_state__slot__laundry_room_id=x.id,
    #         slot_state__slot=slot,
    #         error_type=-2,
    #         slot_state__duration__gt=5,
    #     )

    def _rollup_flickering_errors(self,flickering):
        pass

    def _get_slot_fascard_url(self, slot):
        room_fascard_id = slot.laundry_room.fascard_code
        slot_fascard_id = slot.slot_fascard_id
        url = 'https://admin.fascard.com/86/MachineHist?locationID={}&machID={}'
        return url.format(room_fascard_id, slot_fascard_id)

    def get_upkeep_url(self, slot):
        """
            Retrieves upkeep URL to create a work order for the asset associated to the 
            given slot
        """
        base_url = 'https://app.onupkeep.com/web/work-orders/new?linked-asset={}&linked-location={}'
        machine = Slot.get_current_machine(slot)
        final_url = None
        if machine.upkeep_id and slot.laundry_room and slot.laundry_room.upkeep_code:
            final_url = base_url.format(machine.upkeep_id, slot.laundry_room.upkeep_code)
        return final_url

    def get_maintainx_url(self, slot):
        base_url = 'https://app.getmaintainx.com/assets/{}'
        machine = Slot.get_current_machine(slot)
        final_url = None
        if machine.upkeep_id and slot.laundry_room and slot.laundry_room.upkeep_code:
            final_url = base_url.format(machine.upkeep_id, slot.laundry_room.upkeep_code)
        return final_url

    
    def _rollup_slot_errors(self,non_flickering,double_barreled):
        slot_errors = {}
        errors = non_flickering+double_barreled
        for x in errors:
            last_run_time = self._get_last_run_start(x.slot_state.slot)
            if last_run_time:
                error_start_time =last_run_time
            else:
                error_start_time = x.slot_state.start_time
            
            if x.slot_state.slot_id not in slot_errors:
                error_data = self.map_slot_error_as_dict(x, error_start_time)

                slot_errors[x.slot_state.slot_id] = error_data

            else:
                slot_errors[x.slot_state.slot_id]['error(s)'].add(x.error_message)
                
                #Update End Time 
                if slot_errors[x.slot_state.slot_id]['end time'] is None:
                    pass
                elif x.slot_state.end_time is None:
                    slot_errors[x.slot_state.slot_id]['end time'] = None
                elif x.slot_state.end_time > slot_errors[x.slot_state.slot_id]['end time']:
                    slot_errors[x.slot_state.slot_id]['end time'] = x.slot_state.end_time
                #Update Start Time 
                if not slot_errors[x.slot_state.slot_id]['start time']:
                    slot_errors[x.slot_state.slot_id]['start time'] = error_start_time
                elif error_start_time < slot_errors[x.slot_state.slot_id]['start time']:
                    slot_errors[x.slot_state.slot_id]['start time'] = error_start_time
            
        for slot_error in slot_errors.values():
            slot_error['error(s)'] = ','.join(slot_error['error(s)'])
        return slot_errors
    
    def _generate_results(self,slot_errors,flickering_errors, hours_range_datasets, zero_price_errors_dataset, failed_transactions_matches):
        headers = [
            'building name',
            'display name',
            'start time',
            'end time',
            'error(s)',
            'mlvmacherror_description',
            'slot_status_text',
            'upkeep_create_work_order'
            'fascard_url',
            'fascard_id',
            'internal_id',
        ]
        rows = []
        rows.append(headers)
        current_errors_dataset = Dataset()
        for x in slot_errors.values():
            this_row = []
            for header in headers:
                try:
                    this_row.append(x[header])
                except:
                    this_row.append('')
            #rows.append(this_row)
            current_errors_dataset.append(this_row)
        current_errors_dataset.headers = headers
        current_errors_dataset.title = "Current Errors"
        rows.append(['------------------------------ FLICKERING --------------------------------------------'])
        flickering_dataset = Dataset()
        for y in flickering_errors:
            this_row = [y['building_name'],y['display_name'],y['start_time'],y['end_time'],'Flickering']
            #rows.append(this_row)
            flickering_dataset.append(this_row)
        flickering_dataset.headers = ['building_name', 'display_name', 'start_time', 'end_time', 'Flickering']
        flickering_dataset.title = "Flickering"
        databook = Databook()
        databook.add_sheet(current_errors_dataset)
        databook.add_sheet(flickering_dataset)

        #Add the 24, 48, 72 datasets here
        #Append duration column to headers. This column is only used in hours_range datasets
        headers.insert(4, 'duration')
        for title, data in hours_range_datasets.items():
            dataset = Dataset()
            dataset.title = "{}".format(title)
            dataset.headers = headers
            for slot_fascard_id, slot_errors in data.items():
                for error in slot_errors:
                    row = []
                    for header in headers:
                        try:
                            if header == "error(s)":
                                err = ",".join([str(x) for x in error[header]])
                                row.append(err)
                            else:
                                row.append(error[header])
                        except Exception as e:
                            row.append('')
                    dataset.append(row)
                dataset.append_separator('\n')
            databook.add_sheet(dataset)

        # zero_price_headers = [
        #     'room_name',
        #     'equipment_name',
        #     'equipment_fascard_id',
        #     'cycle_detection_date',
        #     'price'
        # ]

        # zero_price_errors_dataset = Dataset()
        # for error in zero_price_errors:
        #     this_row = []
        #     for header in zero_price_headers:
        #         try:
        #             this_row.append(error[header])
        #         except:
        #             this_row.append('')
        #     #rows.append(this_row)
        #     zero_price_errors_dataset.append(this_row)
        # zero_price_errors_dataset.headers = zero_price_headers
        # zero_price_errors_dataset.title = "Pricing Errors"
        databook.add_sheet(zero_price_errors_dataset)
        databook.add_sheet(failed_transactions_matches) 

        self.results = databook
        self.errors_results_tablib = current_errors_dataset
        #self.results = rows
        #print ("Results: {}".format(self.results))
    
    @classmethod 
    def _get_last_run_start(self,slot):
        x = slot.slot_set.filter(slot_status=MachineStateType.RUNNING).order_by('-local_start_time').first()
        if x is None:
            return None 
        else:
            return x.local_start_time 
    
    def post_send(self):
        marked_unreported = SlotStateError.objects.filter(is_reported=False)
        marked_unreported.update(is_reported=True)