from croniter import croniter
from cron_descriptor import get_description
from datetime import datetime
from django import template
from django.db.models.fields.related import ManyToManyField


register = template.Library()


blacklist_fields = (
    'time_units_lookback',
    'time_units',
    'event_rule',
    'email',
    'cron_expression'
)

url_reverse_map = {
    'InternalReportConfig' : 'internal_report',
    'ClientRevenueReportConfig' : 'client_revenue_report',
    'ClientFullRevenueReportConfig' : 'client_revenue_full_report',
    'RentPaidReportConfig' : 'rent_paid_report',
    'TransactionReportConfig' : 'transactions_report',
}


@register.simple_tag
def get_url_reverse_name(model_name):
    return url_reverse_map.get(model_name)

@register.simple_tag
def get_fields(instance):
    fields_list = [f for f in instance.__class__._meta.get_fields() if not f.auto_created]
    fields = []
    for field in fields_list:
        if field.name in blacklist_fields:
            continue
        fields.append(field.name)
    return fields


@register.simple_tag
def get_admin_url(instance):
    return f"/admin/reports/{str(instance.__class__.__name__).lower()}/{instance.id}/change/"


@register.simple_tag
def get_next_trigger_dates(cron_expr):
    cron_expr = cron_expr.split(' ')
    cron_expr = ' '.join(cron_expr[:5])
    if "?" in cron_expr: cron_expr = cron_expr.replace("?", "*")
    now = datetime.now()
    trigger_dates = []
    try:
        cron_iter = croniter(cron_expr, now)
        for i in range(5):
            trigger_dates.append(str(cron_iter.get_next(datetime)))
    except:
        pass
    return trigger_dates


@register.simple_tag
def get_human_readable_cron(cron_expr):
    cron_expr = cron_expr.split(' ')
    cron_expr = ' '.join(cron_expr[:5])
    return get_description(cron_expr)


@register.simple_tag
def parameters_as_dict(instance):
    fields_list = [f for f in instance.__class__._meta.get_fields() if not f.auto_created]
    payload = {}
    for field in fields_list:
        if field.name in blacklist_fields:
            continue
        if isinstance(field, ManyToManyField):
            val = getattr(instance, field.name)
            if val.all().count() == 0:
                val = None
            elif val.all().count() < 5:
                val = list(val.all())
            else:
                subset = val.all()[:5]
                val = [str(obj) for obj in subset] + [f' and {val.all().count() - 5} others']
                val = ', '.join(val)
        else:
            val = getattr(instance, field.name)
        payload[field.name] = val
    return payload