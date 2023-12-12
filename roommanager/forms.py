import logging
from django import forms
from django.forms.widgets import HiddenInput
from .models import BundleChangeApproval, Machine, AssetUpdateApproval, OrphanedPieceRequiredAnswer, MachineMeterReading
from .enums import AssetMapOutChoices


logger = logging.getLogger(__name__)


class BaseApprovalForm(forms.ModelForm):
    asset_serial_number = forms.CharField(required=False)
    asset_factory_model = forms.CharField(required=False)

    def _extra_init(self, *args, **kwargs):
        ins = kwargs.get('instance')
        if not ins: ins = self.instance
        if ins:
            try:
                machine = ins.get_current_machine()
                current_machine_asset_code = getattr(machine, 'asset_code', ins.scan_pairing.asset_code)
                self.initial['asset_serial_number'] = ins.scan_pairing.asset_serial_number or getattr(machine, 'asset_serial_number', None)
                self.initial['asset_factory_model'] = getattr(machine, 'asset_factory_model', None)
                self.initial['machine_description'] = ins.scan_pairing.machine_description or getattr(machine, 'machine_description', None)
                self.fields['asset_serial_number'].help_text = f'For Machine {current_machine_asset_code}'
                self.fields['asset_factory_model'].help_text = f'For Machine {current_machine_asset_code}'
                self.fields['machine_description'].help_text = f'For Machine {current_machine_asset_code}'
                #hide asset pictures action fields if no pictures
                scan = ins.scan_pairing
                if not scan.asset_picture: self.fields['asset_picture_decision'].widget = HiddenInput()
                if not scan.asset_serial_picture: self.fields['asset_serial_picture_decision'].widget = HiddenInput()
            except Exception as e:
                logger.error(f"failed fething machine: {e}")

    def clean(self, *args, **kwargs):
        approved = self.cleaned_data.get('approved')
        rejected = self.cleaned_data.get('rejected')
        if approved and rejected:
            raise forms.ValidationError("Can't approve and reject at the same time")
        return self.cleaned_data


class BundleChangeApprovalForm(BaseApprovalForm):

    class Meta:
        model = BundleChangeApproval
        fields = (
            'asset_serial_number',
            'asset_factory_model',
            'asset_picture_decision',
            'asset_serial_picture_decision',
            'machine_description',
            'approved',
            'rejected',
            'serial_number_not_available'
        )

    def __init__(self, *args, **kwargs):
        if 'extra_init' in kwargs: extra_init = kwargs.pop('extra_init')
        else: extra_init = True
        super(BundleChangeApprovalForm, self).__init__(*args, **kwargs)
        if extra_init: self._extra_init(args, kwargs)


class AssetUpdateApprovalForm(BaseApprovalForm):

    class Meta:
        model = AssetUpdateApproval
        fields = (
            'asset_serial_number',
            'asset_factory_model',
            'asset_picture_decision',
            'asset_serial_picture_decision',
            'machine_description',
            'approved', 
            'rejected',
            'serial_number_not_available'
        )

    def __init__(self, *args, **kwargs):
        if 'extra_init' in kwargs: extra_init = kwargs.pop('extra_init')
        else: extra_init = True
        super(AssetUpdateApprovalForm, self).__init__(*args, **kwargs)
        if extra_init: self._extra_init(args, kwargs)

class ManualAssetMapoutCreateForm(forms.Form):
    status = forms.ChoiceField(choices=AssetMapOutChoices.CHOICES)
    scan_asset_tag = forms.CharField(max_length=20)
    description = forms.CharField(widget=forms.Textarea)


class MachineMeterReadingForm(forms.ModelForm):

    def __init__(self,*args,**kwargs):
        super (MachineMeterReadingForm,self ).__init__(*args,**kwargs)
        self.fields['machine'].queryset = Machine.objects.filter(is_active=True, placeholder=False)

    class Meta:
        model = MachineMeterReading
        fields = ['machine', 'current_reading', 'picture']