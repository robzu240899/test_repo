import logging
from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import CreateView, FormView, TemplateView
from .api import EventsManager
from .forms import InternalReportForm, ClientRevenueReportConfigForm, ClientFullRevenueReportConfigForm, TransactionsReportConfigForm
from .models import InternalReportConfig, ClientRevenueReportConfig, ClientFullRevenueReportConfig, \
TransactionReportConfig, RentPaidReportConfig, EventRule
from .utils import EventBridgeHandler

logger = logging.getLogger(__name__)


class ReportConfigMixin():

    def post(self, request, *args, **kwargs):
        print ("entered post")
        form = self.get_form()
        context = {}
        if form.is_valid():
            cleaned_data = form.cleaned_data
            cron_expression = cleaned_data.get('cron_expression')
            description = cleaned_data.get('description') or ''
            timestamp = str(datetime.timestamp(datetime.now())).split('.')[0]
            rule_name = f"{self.model.__name__}-{timestamp}"
            logger.info(f"Creating {rule_name} rule. Cron: {cron_expression}. Description: {description}")
            response, msg, success = EventBridgeHandler()._create_event_rule(rule_name, description, cron_expression)
            if response:
                try:
                    #update queue policy
                    pass
                    # EventsManager()._add_queue_policy(event_rule_payload={
                    #     'name': rule_name,
                    #     'resource_arn' : response.get('event_rule_arn'),
                    #     'target_id': response.get('event_rule_arn')
                    # })
                except Exception as e:
                    msg = f'Failed adding policy to queue: {e}'
                    response = {}
            if response:
                self.object = form.save()
                report_config_instance = self.object
                event_rule_obj = EventRule.objects.create(
                    name = rule_name,
                    arn = response.get('event_rule_arn'),
                    target_id = response.get('target_id'),
                    description = description
                )
                report_config_instance.event_rule = event_rule_obj
                report_config_instance.save()
                msg += ". Successfuly saved report config for future processing"
            context['form'] = form
            context['msg'] = msg
            context.update(self.kwargs)
            return render(request,self.template_name,context)
        else:
            return render(request, self.template_name, {"form": form})


class InternalReportView(ReportConfigMixin, LoginRequiredMixin, CreateView):
    base_rule_name = 'InternalReportConfig'
    model = InternalReportConfig
    form_class = InternalReportForm
    template_name = 'base_template.html'


class ClientRevenueReportConfigView(ReportConfigMixin, LoginRequiredMixin, CreateView):
    form_class = ClientRevenueReportConfigForm
    model = ClientRevenueReportConfig
    template_name = 'base_template.html'


class ClientFullRevenueReportConfigView(ReportConfigMixin, LoginRequiredMixin, CreateView):
    form_class = ClientFullRevenueReportConfigForm
    model = ClientFullRevenueReportConfig
    template_name = 'base_template.html'


class RentPaidReportView(ReportConfigMixin, LoginRequiredMixin, CreateView):
    model = RentPaidReportConfig
    fields = (
        'time_units_lookback',
        'time_units',
        'billing_groups',
        'metric',
        'email',
        'cron_expression'
    )
    template_name = 'base_template.html'


class TransactionReportConfigView(ReportConfigMixin, LoginRequiredMixin, FormView):
    form_class = TransactionsReportConfigForm
    model = TransactionReportConfig
    template_name = 'base_template.html'


class ReportManager(LoginRequiredMixin, TemplateView):
    template_name = 'manager.html'

    def get_context_data(self, *args, **kwargs):
        kwargs.setdefault('view', self)
        managed_models = [
            InternalReportConfig,
            ClientRevenueReportConfig,
            ClientFullRevenueReportConfig,
            RentPaidReportConfig,
            TransactionReportConfig
        ]
        extra_context = {'current_configs' : {}}
        for model in managed_models:
            extra_context['current_configs'][model.__name__] = []
            q = model.objects.all()
            if q.count() > 0: extra_context['current_configs'][model.__name__] = q
        kwargs.update(extra_context)
        return kwargs
