'''
Created on Apr 13, 2017

@author: Thomas
'''

from django.conf.urls import  url

from reporting.finance import client_revenue_views, internal_report_views


urlpatterns = [
    url(r'^client-report/$',client_revenue_views.BillingGroupSelectorClientRevenueReport.as_view()),
    url(r'^client-basic-report/$',client_revenue_views.ClientRevenueReportView.as_view()),
    url(r'^client-full-report/$',client_revenue_views.ClientRevenueFullReportView.as_view()),
    url(r'^client-net-rent-report/$',client_revenue_views.ClientRentReportView.as_view()),
    url(r'^internal-report/$',internal_report_views.InternalReportView.as_view()),
    url(r'^pricing-history-report/$',internal_report_views.PriceHistoryView.as_view()),
    url(r'^lease-abstract-report/$',internal_report_views.LeaseAbstractReportView.as_view()),
    url(r'^transactions-report/$', internal_report_views.TransactionReportView.as_view()),
    url(r'^refunds-report/$', internal_report_views.RefundsReportView.as_view()),
    url(r'^client-revenue-report-expenses/$',client_revenue_views.ExpensesClientRevenueReport.as_view()),
    url(r'^monthly-auto-report/$',client_revenue_views.MonthlyAutoReportView.as_view()),
]
