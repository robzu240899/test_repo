from django.urls import path

from . import views

urlpatterns = [
    path('manager/', views.ReportManager.as_view(), name='report_manager'),
    path('internal-report/', views.InternalReportView.as_view(), name='internal_report'),
    path('client-revenue-report/', views.ClientRevenueReportConfigView.as_view(), name='client_revenue_report'),
    path('client-full-revenue-report/', views.ClientFullRevenueReportConfigView.as_view(), name='client_revenue_full_report'),
    path('rent-paid-report/', views.RentPaidReportView.as_view(), name='rent_paid_report'),
    path('transactions-report/', views.TransactionReportConfigView.as_view(), name='transactions_report'),
]