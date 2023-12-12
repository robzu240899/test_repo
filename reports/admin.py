from django.contrib import admin
from .models import InternalReportConfig, ClientRevenueReportConfig, ClientFullRevenueReportConfig, RentPaidReportConfig, TransactionReportConfig
from reports.templatetags.reportstags import get_next_trigger_dates

class BaseAdmin(admin.ModelAdmin):
    readonly_fields = (
        'next_trigger_dates',
    )

    def has_add_permission(self, request, obj=None):
        return False

    def next_trigger_dates(self, instance):
        return get_next_trigger_dates(instance.cron_expression)


class InternalReportConfigAdmin(BaseAdmin):
    list_display = (
        'cron_expression',
        'email',
        'revenue_rule',
        'time_units_lookback',
        'time_units',
        'rooms_count',
    )
    
    def rooms_count(self, instance):
        return instance.rooms.all().count()


class ClientRevenueReportConfigAdmin(BaseAdmin):
    list_display = (
        'cron_expression',
        'email',
        'pdf_generation',
        'html_generation',
        'billing_groups_count'
    )
    
    def billing_groups_count(self, instance):
        return instance.billing_groups.all().count()

class ClientFullRevenueReportConfigAdmin(BaseAdmin):
    list_display = (
        'cron_expression',
        'email',
        'billing_groups_count'
    )
    
    def billing_groups_count(self, instance):
        return instance.billing_groups.all().count()
    

class RentPaidReportConfigAdmin(BaseAdmin):
    list_display = (
        'cron_expression',
        'email',
        'metric',
        'billing_groups_count'
    )
    
    def billing_groups_count(self, instance):
        return instance.billing_groups.all().count()

class TransactionReportConfigAdmin(BaseAdmin):
    list_display = (
        'cron_expression',
        'email',
        'report_type',
        'employees_count'
    )
    
    def employees_count(self, instance):
        return instance.employees.all().count()


admin.site.register(InternalReportConfig, InternalReportConfigAdmin)
admin.site.register(ClientRevenueReportConfig, ClientRevenueReportConfigAdmin)
admin.site.register(ClientFullRevenueReportConfig, ClientFullRevenueReportConfigAdmin)
admin.site.register(RentPaidReportConfig, RentPaidReportConfigAdmin)
admin.site.register(TransactionReportConfig, TransactionReportConfigAdmin)
# Register your models here.
