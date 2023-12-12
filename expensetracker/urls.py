from django.conf.urls import url, include
from expensetracker import views
from expensetracker import api


urlpatterns = [
    url(r'^$', views.ExpenseTracker.as_view()),
    url(r'^api/v1/', include([
        url(r'^technicians$', api.TechnicianList.as_view(), name='technician-list'),
        url(r'^job-statuses$', api.job_status_list, name='job-status-list'),
        url(r'^job-types$', api.job_type_list, name='job-type-list'),
        url(r'^line-item-types$', api.line_item_type_list, name='line-item-type-list'),
        url(r'^line-item-statuses$', api.line_item_status_list, name='line-item-status-list'),
        url(r'^search$', api.JobList.as_view(), name='search'),
        url(r'^jobs$', api.JobDetail.as_view(), name='new-job'),
        url(r'^jobs/(?P<pk>[0-9]+)$', api.JobDetail.as_view(), name='job-detail'),
        url(r'^line_items/(?P<pk>[0-9]+)$', api.LineItemDetail.as_view(), name='line-item-detail'),
        url(r'^line_items$', api.LineItemDetail.as_view(), name='new-line-item'),
    ])),
    
]
