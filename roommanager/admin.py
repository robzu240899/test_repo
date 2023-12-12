'''
Created on Apr 22, 2017

@author: Thomas
'''
import datetime
import pytz
from django import forms
from dateutil.parser import parse
from import_export.admin import ImportExportModelAdmin, ImportMixin
from import_export import resources
from django.conf import settings
from django.contrib import admin
from django.utils.timezone import make_aware
from queuehandler.job_creator import UpkeepAssetSyncEnqueuer
from roommanager import models as roommager_models
from roommanager.signals import process_machine_thread
from roommanager.enums import HardwareType
from upkeep.manager import UpkeepCardReaderManager
from upkeep.config import WORK_ORDER_FIELD_MAP
import re
# class MachineSlotMapAdmin(admin.TabularInline):
#     model = roommager_models.MachineSlotMap

# class SlotAdmin(admin.ModelAdmin):
#     inlines = [
#         MachineSlotMapAdmin
#     ]

class EquipmentTypeAdmin(admin.ModelAdmin):
    readonly_fields = ('machine_type',)
    list_display = [
        'machine_text',
        'machine_type',
        'equipment_start_check_method',
        'fascard_id'
    ]


class MachineSlotMapInline(admin.TabularInline):
    model = roommager_models.MachineSlotMap
    readonly_fields = ['slot', 'machine', 'end_time', 'is_active']
    extra = 0

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(end_time=None, is_active=True).order_by('-start_time')


class HardwareBundleAdminInline(admin.TabularInline):
    model = roommager_models.HardwareBundle
    readonly_fields = ('slot', 'card_reader', 'start_time')
    fields = (
        'slot', 
        'card_reader',
        'machine',
        'is_active',
        'start_time',
        'end_time',
        'bundle_type'
    )
    extra = 0


class SlotAdmin(admin.ModelAdmin):
    inlines = [
        MachineSlotMapInline,
    ]
    list_filter = ('laundry_room',)
    readonly_fields = ('equipment_type',)

class SlotAdminView(SlotAdmin):
    inlines = []


class CurrentRoomFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = 'Current Laundry Room'

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'laundryroom'

    def lookups(self, request, model_admin):
        l = []
        for room in roommager_models.LaundryRoom.objects.filter(is_active=True):
            l.append((room.display_name, room.display_name))
        return l

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        room = roommager_models.LaundryRoom.objects.get(display_name=self.value())
        machine_ids = roommager_models.HardwareBundle.objects.filter(location=room).values('machine')
        return queryset.filter(id__in=machine_ids)


class MachineAdminForm(forms.ModelForm):
    def clean_asset_serial_picture(self):
        """
        Validate that when assigning "NOT AVAILABLE" it has the appropriate structure
        replacing the space with an underscore
        Fields: asset_serial_picture
        """
        available_display = 'NOT_AVAILABLE'
        pattern = r"[(http(s)?):\/\/(www\.)?a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,6}\b([-a-zA-Z0-9@:%_\+.~#?&//=]*)"
        asset_serial_picture = self.cleaned_data['asset_serial_picture']

        if re.match(pattern, asset_serial_picture): # regex for URL patterns (http/https/www)
            return self.cleaned_data['asset_serial_picture']
        
        if asset_serial_picture != available_display:
            raise forms.ValidationError(f'{asset_serial_picture} cannot be registered. If the field is not available, make sure you write: NOT_AVAILABLE')
        
        return self.cleaned_data['asset_serial_picture']


class MachineAdmin(admin.ModelAdmin):
    form = MachineAdminForm
    list_filter = (CurrentRoomFilter,)
    list_display = [
        '__str__',
        'maintainx_id',
        'asset_code',
        'current_location'
    ]
    search_fields = ('upkeep_id', 'asset_code','asset_serial_number')
    inlines = [
        HardwareBundleAdminInline
    ]
    regular_fields = (
        'machine_type',
        'make',
        'is_active',
        'machine_description',
        'asset_code',
        'maintainx_id',
        'asset_serial_number',
        'asset_factory_model',
        'equipment_type',
        'placeholder',
    )
    fieldsets = (
        (None, {
            'fields': regular_fields,
        }),
        ('Pictures', {
            'fields': ('asset_picture', 'asset_serial_picture'),
            'description': "To require a new scan delete the link and make the field blank. " \
                        "To flag a picture as not available write NOT_AVAILABLE on its corresponding field"
        }),
    )
    readonly_fields = ('equipment_type',)

    def current_location(self, obj):
        return obj.get_location()
    current_location.short_description = 'Current Location'

    def save_model(self, request, obj, form, change):
        super(MachineAdmin, self).save_model(request, obj, form, change)
        obj.refresh_from_db()
        process_machine_thread([obj])


class MachineSlotMapAdmin(admin.ModelAdmin):
    readonly_fields = ('machine','slot')
    list_filter = (CurrentRoomFilter,)


class HardwareBundleAdmin(admin.ModelAdmin):
    list_filter = ('is_active',)
    list_display = [
        '__str__',
        'slot',
        'get_card_reader_tag',
        'get_machine_tag'
    ]
    search_fields = [
        'card_reader__card_reader_tag',
        'machine__asset_code',
        'slot__laundry_room__display_name'
    ]
    readonly_fields = ('slot', 'card_reader')

    def get_card_reader_tag(self, obj):
        return obj.card_reader.card_reader_tag
    get_card_reader_tag.short_description = 'Card Reader Tag'
    get_card_reader_tag.admin_order_field = 'card_reader__card_reader_tag'

    def get_machine_tag(self, obj):
        return obj.machine.asset_code
    get_machine_tag.short_description = 'Machine Tag'
    get_machine_tag.admin_order_field = 'machine__asset_code'


class CardReaderResource(resources.ModelResource):

    class Meta:
        model = roommager_models.CardReaderAsset
        fields = (
            'id',
            'condition',
            'model',
            'serial', 
            'status',
            'card_reader_tag',
        )

    # def __init__(self, *args, **kwargs):
    #     super(CardReaderResource, self).__init__(*args, **kwargs)
    #     self.upkeep_manager = UpkeepCardReaderManager()

    def after_save_instance(self, instance, using_transactions, dry_run, **kwargs):
        super(CardReaderResource, self).after_save_instance(instance, using_transactions, dry_run, **kwargs)
        if not dry_run:
            UpkeepAssetSyncEnqueuer.enqueue_asset_syncing(instance.id, HardwareType.CARD_READER)
            #self.upkeep_manager.create_or_update(instance)

        
class CardReaderResourceAdmin(ImportExportModelAdmin):
    resource_class = CardReaderResource
    inlines = [
        HardwareBundleAdminInline
    ]
    ordering = ('card_reader_tag',)
    search_fields = ['card_reader_tag']


class ValidTagResource(resources.ModelResource):

    class Meta:
        model = roommager_models.ValidTag
        fields = (
            'id',
            'tag_string',
        )

    def skip_row(self, instance, original):
        return True if roommager_models.ValidTag.objects.filter(tag_string=instance.tag_string).exists() else False

class ValidTagResourceAdmin(ImportExportModelAdmin):
    resource_class = ValidTagResource


class WorkOrderRecordResource(resources.ModelResource):

    class Meta:
        model = roommager_models.WorkOrderRecord
        fields = ('id',) + tuple(WORK_ORDER_FIELD_MAP.values())

    def clean_date(self, date_record):
        date_record = parse(date_record, tzinfos={'EDT':-14400, 'EST':-18000})
        local_time_zone = pytz.timezone(settings.DEFAULT_LAUNDRYROOM_TIMEZONE)
        local_time = date_record.astimezone(local_time_zone)
        return local_time.replace(tzinfo=None)

    def clean_dataset(self, dataset):
        date_fields = ('completed_date', 'created_date', 'updated_date')
        i = 0
        last = dataset.height - 1
        while i <= last:
            data = [dataset.get_col(j)[0] for j in range(0, len(dataset.headers))]
            for date_field in date_fields:
                if date_field in dataset.headers:
                    try:
                        date_record = dataset[date_field][0]
                        cleaned_date = self.clean_date(date_record)
                        at = dataset.headers.index(date_field)
                        data[at] = cleaned_date
                    except:
                        cleaned_date = None
            dataset.rpush(tuple(data))
            dataset.lpop()
            i = i + 1
        return dataset

    def before_import(self, dataset, using_transactions, dry_run, **kwargs):
        try:
            cleaned_dataset = self.clean_dataset(dataset)
        except Exception as e:
            raise Exception(e)
        return cleaned_dataset


class WorkOrderRecordAdmin(ImportExportModelAdmin):
    resource_class = WorkOrderRecordResource
    list_display = [ 'title', 'created_date', 'status','asset_upkeep_id']


class LaundryAdminForm(forms.ModelForm):
    def clean_display_name(self):
        invalids = '<>:\"/\\|?*'
        display_name = self.cleaned_data["display_name"]
        for c in invalids:
            display_name = display_name.replace(c,'')
        return display_name


class LaundryRoomAdmin(admin.ModelAdmin):
    form = LaundryAdminForm



class MachineMeterReadingAdmin(admin.ModelAdmin):
    readonly_fields = ('machine',)
    list_display = ['__str__', 'approved']


admin.site.register(roommager_models.LaundryGroup)
admin.site.register(roommager_models.MachineMeterReading, MachineMeterReadingAdmin)
admin.site.register(roommager_models.LaundryRoom, LaundryRoomAdmin)
admin.site.register(roommager_models.DefaultRoom)
admin.site.register(roommager_models.Slot, SlotAdmin)
admin.site.register(roommager_models.SlotView, SlotAdminView)
admin.site.register(roommager_models.MachineSlotMap, MachineSlotMapAdmin)
admin.site.register(roommager_models.Machine, MachineAdmin)
admin.site.register(roommager_models.CardReaderAsset, CardReaderResourceAdmin)
admin.site.register(roommager_models.TechnicianEmployeeProfile)
admin.site.register(roommager_models.EquipmentType, EquipmentTypeAdmin)
admin.site.register(roommager_models.HardwareBundle, HardwareBundleAdmin)
admin.site.register(roommager_models.HardwareBundlePairing)
admin.site.register(roommager_models.BundleChangeApproval)
admin.site.register(roommager_models.ValidTag, ValidTagResourceAdmin)
admin.site.register(roommager_models.WorkOrderRecord, WorkOrderRecordAdmin)
