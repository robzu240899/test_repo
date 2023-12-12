from datetime import date
from django import forms
from django.contrib import admin
from django.forms import BaseInlineFormSet, ModelForm
from django.views.decorators.csrf import csrf_protect
from import_export.admin import ImportExportModelAdmin
from import_export import resources
from roommanager.models import LaundryRoom
from reporting import models as reporting_models
from .models import BillingGroup, Payee, BillingGroupEmailAddress, ClientEmailAddress, MeterRaise, RevenueSplitRule, NonRecurrentExpense
from .enums import RevenueSplitScheduleType


class CombinedFormSet(BaseInlineFormSet):
    # Validate formset data here
    def clean(self):
        super(CombinedFormSet, self).clean()
        for form in self.forms:
            if not hasattr(form, 'cleaned_data'):
                continue

            data = self.cleaned_data
            valid = False
            percentages = list()
            for i in data:
                if i != {}:
                    print (i)
                    percentages.append(i['percentage_share'])

            if len(percentages)>0:
                if sum(percentages) == 100:
                    valid = True
                else:
                    valid = False
            else:
                valid = True

            if not valid:
                raise forms.ValidationError("Percentages must add up to 100.")
            return data

class MeterCombinedFormSet(BaseInlineFormSet):
    def clean(self):
        super(MeterCombinedFormSet, self).clean()
        if not hasattr(self, 'cleaned_data'):
            raise forms.ValidationError("Invalid MeterRaise data")
        data = self.cleaned_data
        bg = data[0].get('billing_group')

        counter = 0
        for i in data:
            if i != {}:
                counter += 1

        if bg is not None:
            if bg.max_meter_raises is None:
                if counter != 0:
                    valid = False
                else:
                    valid = True
            else:
                if counter > bg.max_meter_raises:
                    valid = False
                else:
                    valid = True
            
        else:
            valid = True

        if valid:
            return data
        else:
            raise forms.ValidationError("Meter Raises are more than allowed")
        
class RevenueSplitRuleCombinedFormSet(BaseInlineFormSet):

    def _clean_time_based_rules(self) -> bool:
        non_empty_forms = [form for form in self.forms if form.cleaned_data != {}]
        for i, form in enumerate(non_empty_forms):
            if form.cleaned_data == {}: continue
            form_start_date = form.cleaned_data.get('start_date')
            form_end_date = form.cleaned_data.get('end_date')
            if i==0:
                form.cleaned_data['start_date'] = None
                form.instance.start_date = None
                #Make the effectuation start_date of the first revenue split rule None by default
                #so that the first monthly revenue calculations don't conflict with the revenue split rule
                #E.g: If the effectuation start_ date for the first revenuesplit rule is Feb 19th and we are trying
                #to get a revenue report starting on Feb 1st, it would fail because there is no revenuesplit rule having
                #started before Feb 1st.
            else:
                if form_start_date is None:
                    raise forms.ValidationError("Start date must be filled in for time based rules other than the first one.")
                if form_start_date != non_empty_forms[i-1].cleaned_data.get('end_date'):
                    raise forms.ValidationError(("Time based rules must have no gaps and not overlap."))
            
            if form_start_date and form_end_date and form_end_date < form_start_date:
                raise forms.ValidationError(("Start date must be less than end date"))           
            if (i != len(non_empty_forms)-1) and form_end_date is None:
                raise forms.ValidationError(('Only the last revenue rule may have a null end time'))
        return True

    def clean(self):
        super(RevenueSplitRuleCombinedFormSet, self).clean()
        if any(self.errors):
            return
        if not any(cleaned_data and not cleaned_data.get('DELETE', False)
                   for cleaned_data in self.cleaned_data):
            raise forms.ValidationError('At least one Revenue Split Rule is required.')
        
        non_empty_forms = [cleaned_data for cleaned_data in self.cleaned_data if cleaned_data != {}]
        for cleaned_data in non_empty_forms:
            if cleaned_data.get('min_comp_per_day') is None or not (int(cleaned_data.get('min_comp_per_day')) >= 0):
                raise forms.ValidationError('All revenue split rules must have min_comp_per_day. Enter 0 for None')

        bg = self.cleaned_data[0].get('billing_group')
        if bg.schedule_type == RevenueSplitScheduleType.TIME:
            self._clean_time_based_rules()
        return self.cleaned_data


class BillingGroupBaseForm(ModelForm):
    class Meta:
        model = BillingGroup
        fields = '__all__'
        exclude = ('min_compensation_per_day',)

    def clean(self, *args, **kwargs):
        auto_renew = self.cleaned_data.get('lease_term_auto_renew')
        auto_renew_length = self.cleaned_data.get('lease_term_auto_renew_length')
        if auto_renew and auto_renew_length is None:
            raise forms.ValidationError('Auto renew length not specified')
        
        lease_term_duration_months = self.cleaned_data.get('lease_term_duration_months')
        lease_term_duration_days = self.cleaned_data.get('lease_term_duration_days')
        lease_term_end = self.cleaned_data.get('lease_term_end')
        if lease_term_duration_months == 0:
            pass #month-to-month lease
        elif not any([lease_term_duration_months, lease_term_duration_days]) and not lease_term_end:
            raise forms.ValidationError('At least one form of lease end date is needed')
        #make sure that either relative duration or lease end date is specified
        #if no lease end date is specified make sure that either one from month and days is greater than zero
        return self.cleaned_data

    def clean_display_name(self):
        invalids = '<>:\"/\\|?*'
        display_name = self.cleaned_data["display_name"]
        for c in invalids:
            display_name = display_name.replace(c,'')
        return display_name


class PayeeInline(admin.TabularInline):
    model = Payee
    formset = CombinedFormSet


class MeterRaiseInline(admin.TabularInline):
    model = MeterRaise
    formset = MeterCombinedFormSet


class RevenueSplitRuleInline(admin.TabularInline):
    model = RevenueSplitRule
    formset = RevenueSplitRuleCombinedFormSet

class BillingGroupEmailInline(admin.TabularInline):
    model = BillingGroupEmailAddress


class ClientEmailInline(admin.TabularInline):
    model = ClientEmailAddress


class BillingGroupExpenseTypeMapInline(admin.TabularInline):
    model = reporting_models.BillingGroupExpenseTypeMap


class AutoRenewHistoryInline(admin.TabularInline):
    model = reporting_models.AutoRenewHistory
    readonly_fields = ('timestamp', 'lease_start_date', 'lease_end_date', 'original')
    classes = ('collapse',)


class LaundryRoomExtensionTabularAdmin(admin.TabularInline):
    model = reporting_models.LaundryRoomExtension
    show_change_link = True
    fields = ('laundry_room',)
    readonly_fields = fields

    def has_add_permission(self, obj, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False


class BillingGroupAdmin(admin.ModelAdmin):
    inlines = [
        AutoRenewHistoryInline,
        PayeeInline,
        BillingGroupEmailInline,
        BillingGroupExpenseTypeMapInline,
        MeterRaiseInline,
        RevenueSplitRuleInline,
        LaundryRoomExtensionTabularAdmin,
    ]
    form = BillingGroupBaseForm


class ClientAdmin(admin.ModelAdmin):
    inlines = [ClientEmailInline]


class UpcomingMeterRaiseNotificationAdmin(admin.ModelAdmin):
    ordering = ['completed']
    list_display = [
        '__str__',
        'get_billing_group',
        'get_scheduled_date',
        'get_raise_limit',
        'completed'
    ]

    def get_scheduled_date(self, obj):
        return obj.meter_raise.scheduled_date
    get_scheduled_date.short_description = 'Scheduled Meter Raise'
    get_scheduled_date.admin_order_field = 'meter_raise__scheduled_date'

    def get_billing_group(self, obj):
        return obj.meter_raise.billing_group
    get_billing_group.short_description = 'Billing Group'

    def get_raise_limit(self, obj):
        return obj.meter_raise.raise_limit
    get_raise_limit.short_description = 'Raise Limit (Description)'


class LaundryRoomExtensionAdmin(admin.ModelAdmin):
    list_display = [
        '__str__',
        'laundry_room',
        'billing_group'
    ]
    search_fields = ['laundry_room__display_name', 'billing_group__display_name']
    list_max_show_all = 100
    list_per_page = 300


class LaundryRoomExtensionResource(resources.ModelResource):

    class Meta:
        model = reporting_models.LaundryRoomExtension
        fields = (
            'id',
            'laundry_room__display_name',
            'billing_group__display_name',
            'latitude',
            'longitude',
            'num_units',
            'square_feet_residential',
            'has_elevator',
            'is_outdoors',
            'laundry_in_unit',
            'legal_structure__name',
            'building_type__name',
        )
        export_order = fields

class LaundryRoomExtensionResourceAdmin(LaundryRoomExtensionAdmin, ImportExportModelAdmin):
    resource_class = LaundryRoomExtensionResource


class NonEditableMixin():

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in obj._meta.fields] + \
               [field.name for field in obj._meta.many_to_many]

    def has_add_permission(self, obj, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class CustomPriceHistoryAdmin(NonEditableMixin, admin.ModelAdmin):
    pass


class PricingPeriodAdmin(NonEditableMixin, admin.ModelAdmin):
    pass


class NonRecurrentExpenseAdmin(admin.ModelAdmin):
    list_display = [
        '__str__',
        'expense_type',
        'short_description',
        'laundry_room',
        'amount',
        'approved'
    ]
    readonly_fields = ['timestamp', 'approved_by', 'created_by']

    def short_description(self, obj):
        return obj.description[:20]

    def get_form(self, request, obj=None, **kwargs):
        if not obj:
            if not request.user.has_perm('reporting.approve_or_reject'):
                kwargs['exclude'] = ('approved', 'rejected', 'approved_by', 'created_by')
        return super(NonRecurrentExpenseAdmin, self).get_form(request, obj, **kwargs)

    def save_model(self, request, obj, form, change):
        if not change: obj.created_by = request.user
        if obj.approved: obj.approved_by = request.user
        super(NonRecurrentExpenseAdmin, self).save_model(request, obj, form, change)
    

admin.site.register(reporting_models.LaundryRoomExtension, LaundryRoomExtensionResourceAdmin)
admin.site.register(reporting_models.LegalStructureChoice)
admin.site.register(reporting_models.BuildingTypeChoice)
admin.site.register(reporting_models.Client, ClientAdmin)
admin.site.register(reporting_models.Payee)
admin.site.register(reporting_models.Lessee)
admin.site.register(reporting_models.BillingGroup, BillingGroupAdmin)
admin.site.register(reporting_models.UpcomingMeterRaiseNotification, UpcomingMeterRaiseNotificationAdmin)
admin.site.register(reporting_models.RevenueSplitRule)
admin.site.register(reporting_models.ExpenseType)
admin.site.register(reporting_models.BillingGroupExpenseTypeMap)
admin.site.register(reporting_models.NonRecurrentExpense, NonRecurrentExpenseAdmin)
#admin.site.register(reporting_models.CustomPriceHistory, CustomPriceHistoryAdmin)
#admin.site.register(reporting_models.PricingPeriod, PricingPeriodAdmin)
#admin.site.register(reporting_models.ClientReportFullStoredFile)
