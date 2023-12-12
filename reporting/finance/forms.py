from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from django import forms
from django.core.exceptions import ValidationError, PermissionDenied
from reporting.enums import ClientRentReportMetrics, LocationLevel, DurationType
from reporting.models import BillingGroup, ExpenseType, MetricsCache, LaundryRoomExtension
from reporting.helpers import Helpers

class BillingGroupSelectionForm(forms.Form):
    billing_group = forms.ModelChoiceField(queryset=BillingGroup.objects.all().order_by('display_name'))
    month = forms.ChoiceField(choices=[(x, x) for x in range(1, 13)])
    year = forms.ChoiceField(choices=[(x, x) for x in range(datetime.now().year-5, datetime.now().year+1)])

    def clean(self):

        cleaned_data=super(BillingGroupSelectionForm, self).clean()
        cleaned_data['year'] = int(cleaned_data['year'])
        cleaned_data['month'] = int(cleaned_data['month'])
        dt = date(cleaned_data['year'],cleaned_data['month'],1) + relativedelta(months=1)
        if dt > datetime.now().date():
            raise ValidationError(_("To ensure data quality, this report must be run after the month is completed."))
        return cleaned_data

class MultipleBillingGroupSelectionForm(BillingGroupSelectionForm):
    billing_group = forms.ModelMultipleChoiceField(
        #queryset=BillingGroup.objects.all(),
        queryset = None,
        required=True,
        widget=forms.SelectMultiple(attrs={'id':'select_billing_group'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ids = []
        for bg in BillingGroup.objects.filter(is_active=True):
            if bg.revenuesplitrule_set.all().count() > 0:
                ids.append(bg.id)
        self.fields['billing_group'].queryset = BillingGroup.objects.filter(id__in=ids, is_active=True)


class ClientRevenueReportForm(forms.Form):
    billing_group = forms.ModelMultipleChoiceField(
        queryset = None,
        required=True,
        widget=forms.SelectMultiple(attrs={'id':'select_billing_group'})
    )
    start_year = forms.ChoiceField(choices=[(x, x) for x in range(datetime.now().year-5, datetime.now().year+1)])
    start_month = forms.ChoiceField(choices=[(x, x) for x in range(1, 13)])
    end_year = forms.ChoiceField(choices=[(x, x) for x in range(datetime.now().year-5, datetime.now().year+1)])
    end_month = forms.ChoiceField(choices=[(x, x) for x in range(1, 13)])
    pdf_generation = forms.BooleanField(required=False)
    html_generation = forms.BooleanField(required=False)
    include_zero_rows = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ids = []
        for bg in BillingGroup.objects.filter(is_active=True):
            if bg.revenuesplitrule_set.all().count() > 0:
                ids.append(bg.id)
        self.fields['billing_group'].queryset = BillingGroup.objects.filter(id__in=ids, is_active=True)

    def clean(self):
        cleaned_data=super(ClientRevenueReportForm, self).clean()
        billing_groups = cleaned_data.get('billing_group')
        errors = []
        metrics_base_query = MetricsCache.objects.filter(
            duration = DurationType.BEFORE,
            start_date__gte=date(
                int(cleaned_data.get('start_year')),
                int(cleaned_data.get('start_month')),
                1)
            )
        for bg in billing_groups:
            errors.extend(Helpers.bg_extra_checks(bg, cleaned_data, query=metrics_base_query))
        orphane_room_extensions = LaundryRoomExtension.objects.filter(billing_group__isnull=True)
        for ext in orphane_room_extensions:
            errors.append(f"The Laundry Room Extension group {ext} is not associated with a Billing Group yet.")
        if errors: raise ValidationError(errors)
        return cleaned_data


class ClientFullLowLevelReportForm(ClientRevenueReportForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['pdf_generation'].widget = forms.HiddenInput()
        self.fields['html_generation'].widget = forms.HiddenInput()


class CustomDateInput(forms.widgets.TextInput):
    input_type = 'date'
    input_formats=['%Y-%m']


class RentReportForm(forms.Form):
    billing_group = forms.ModelMultipleChoiceField(
        #queryset=BillingGroup.objects.all(),
        queryset = None,
        required=True,
        widget=forms.SelectMultiple(attrs={'id':'select_billing_group'})
    )
    start_year = forms.ChoiceField(choices=[(x, x) for x in range(datetime.now().year-5, datetime.now().year+1)])
    start_month = forms.ChoiceField(choices=[(x, x) for x in range(1, 13)])
    end_year = forms.ChoiceField(choices=[(x, x) for x in range(datetime.now().year-5, datetime.now().year+1)])
    end_month = forms.ChoiceField(choices=[(x, x) for x in range(1, 13)])
    metric = forms.ChoiceField(
        label='Extra Metric to Include',
        required=True,
        choices=ClientRentReportMetrics.CHOICES
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ids = []
        for bg in BillingGroup.objects.filter(is_active=True):
            if bg.revenuesplitrule_set.all().count() > 0:
                ids.append(bg.id)
        self.fields['billing_group'].queryset = BillingGroup.objects.filter(id__in=ids, is_active=True)

    def clean(self):
        cleaned_data=super(RentReportForm, self).clean()
        billing_groups = cleaned_data.get('billing_group')
        errors = []
        metrics_base_query = MetricsCache.objects.filter(
            duration = DurationType.BEFORE,
            start_date__gte=date(
                int(cleaned_data.get('start_year')),
                int(cleaned_data.get('start_month')),
                1)
            )
        for bg in billing_groups:
            errors.extend(Helpers.bg_extra_checks(bg, cleaned_data, query=metrics_base_query))
        if errors: raise ValidationError(errors)
        return cleaned_data

# class MultipleBillingGroupSelectionForm(forms.Form):
#     billing_group = forms.ModelMultipleChoiceField(
#         queryset=LaundryRoom.objects.all(),
#         required=True
#     )
#     month = forms.ChoiceField(choices=[(x, x) for x in range(1, 13)])
#     year = forms.ChoiceField(choices=[(x, x) for x in range(datetime.now().year-5, datetime.now().year+1)])
#
#     def clean(self):
#         cleaned_data=super(CustomPriceHistoryForm, self).clean()
#         cleaned_data['year'] = int(cleaned_data['year'])
#         cleaned_data['month'] = int(cleaned_data['month'])
#         dt = date(cleaned_data['year'],cleaned_data['month'],1) + relativedelta(months=1)
#         if dt > datetime.now().date():
#             raise ValidationError(_("To ensure data quality, this report must be run after the month is completed."))
#         return cleaned_data

class ExpenseForm(forms.Form):
    expense_type = forms.ModelChoiceField(required=False,queryset=ExpenseType.objects.all().order_by('display_name'),widget = forms.Select(attrs={'readonly':'readonly'}))
    expense_amount = forms.FloatField(required=False)

    def clean(self):
        cleaned_data=super(ExpenseForm, self).clean()
        if cleaned_data['expense_type'] and (cleaned_data['expense_amount'] is None):
            raise ValidationError(_("If expense type is selected, you must input an expense amount."))
        return cleaned_data