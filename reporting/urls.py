from django.conf.urls import  url
from .views import CustomPricingReportView, OnDemandPricingReportView, PricingChangesTaskView, \
         ajax_plot, TimeUsageReportView

urlpatterns = [
    url(r'^custom-pricing-history/$', CustomPricingReportView.as_view(), name="pricing_history_report"),
    url(r'^ondemand-pricing-history/$', OnDemandPricingReportView.as_view(), name="ondemand_pricing_history_report"),
    url(r'^time-usage-report/$', TimeUsageReportView.as_view(), name="time_usage_report"),
    url(r'^pricing-changes-detector-webhook/$',PricingChangesTaskView.as_view(), name="pricing_changes_task_webhook"),
    url(r'^custom-pricing-history/plotting/$',ajax_plot, name="pricing_history_plot"),
]
