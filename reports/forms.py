from django import forms
from reporting.enums import TransactionReportType
from reporting.finance.internal_report_views import RevenueForm, CustomModelChoiceField
from reporting.models import BillingGroup
from revenue.models import FascardUser
from .enums import TimeUnits
from .models import InternalReportConfig, ClientRevenueReportConfig, ClientFullRevenueReportConfig, \
TransactionReportConfig, RentPaidReportConfig

class InitFormMixin():

    def __init__(self, *args, **kwargs):
        super(InitFormMixin, self).__init__(*args, **kwargs)
        for field in self.blacklist_fields:
            self.fields.pop(field)

class ClientReportMixin():
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ids = []
        for bg in BillingGroup.objects.filter(is_active=True):
            if bg.revenuesplitrule_set.all().count() > 0:
                ids.append(bg.id)
        self.fields['billing_groups'].queryset = BillingGroup.objects.filter(id__in=ids, is_active=True)


class InternalReportForm(forms.ModelForm):
    class Meta:
        model = InternalReportConfig
        fields = (
        'time_units_lookback',
        'time_units',
        'time_grouping',
        'location_grouping',
        'revenue_rule',
        'rooms',
        'include_all_rooms',
        'billing_groups',
        'include_all_billing_groups',
        'active_only',
        'exclude_zero_rows',
        'sort_by',
        'email',
        'cron_expression'
    )

    def clean(self, *args, **kwargs):
        include_all_rooms = self.cleaned_data.get('include_all_rooms')
        include_all_billing_groups = self.cleaned_data.get('include_all_billing_groups')
        rooms = self.cleaned_data.get('rooms')
        bgs = self.cleaned_data.get('billing_groups')
        if (include_all_rooms and include_all_billing_groups) or (rooms and bgs):
            raise forms.ValidationError("May not include both rooms and billing groups")


class ClientRevenueReportConfigForm(ClientReportMixin, forms.ModelForm):
    class Meta:
        model = ClientRevenueReportConfig
        fields = (
            'time_units_lookback',
            'time_units',
            'billing_groups',
            'pdf_generation',
            'html_generation',
            'include_zero_rows',
            'email',
            'cron_expression'
        )


class ClientFullRevenueReportConfigForm(ClientReportMixin, forms.ModelForm):
    class Meta:
        model = ClientFullRevenueReportConfig
        fields = (
            'time_units_lookback',
            'time_units',
            'billing_groups',
            'include_zero_rows',
            'email',
            'cron_expression'
        )


class TransactionsReportConfigForm(forms.ModelForm):
    employees = CustomModelChoiceField(
        queryset=FascardUser.objects.filter(is_employee=True).order_by('-fascard_last_activity_date'), 
        required=False
    )

    class Meta:
        model = TransactionReportConfig
        fields = (
            'time_units_lookback',
            'time_units',
            'employees',
            'last_activity_lookback',
            'last_activity_lookback_time_units',
            'report_type',
            'email',
            'cron_expression'
        )

    def clean(self):
        last_activity_lookback = self.cleaned_data.get('last_activity_lookback')
        last_activity_lookback_time_units = self.cleaned_data.get('last_activity_lookback_time_units')
        employees = self.cleaned_data.get('employees')
        if (last_activity_lookback and last_activity_lookback_time_units and employees):
            raise forms.ValidationError("May not select both Employees and Activty Lookback at the same time")


# class TransactionsReportConfigForm(TransactionReportForm):
#     time_units_lookback = forms.IntegerField(min_value=1, max_value=100)
#     time_units = forms.ChoiceField(choices=TimeUnits.CHOICES)
#     start_date = None
#     end_date = None
