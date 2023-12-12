from django.conf.urls import url, include
from revenue import views
from revenue import api


urlpatterns = [
    url(r'^refunds/', views.Transaction.as_view()),
    url(r'^wizard/', views.TransactionRefundWizard.as_view()),
    url(r'^cashout/', views.CashoutView.as_view()),
    url(r'^damage-refund/', views.DamageRefundView.as_view()),
    url(r'^get-slots/$', views.ajax_get_room_slots, name="get_room_slots"),
    url(r'^manual-tx-ingest/$', views.ManualTransactionIngest.as_view(), name="manual_tx_ingest"),
    #url(r'^echeck/', views.eCheckWizard.as_view()),
    #url(r'^echeck-form/', views.eCheckForm.as_view()),
    url(r'^api/v1/', include([
        url(r'^search$', api.TransactionList.as_view(), name='search-transaction'),
        url(r'^refund$', api.refund, name='refund-transaction'),
        url(r'^payment-types$', api.payment_type_list, name='payment-type-list'),
        url(r'^activity-types$', api.activity_type_list, name='activity-type-list'),
    ])),
    url(r'^machine-data/', views.DownloadMachineRevenueView.as_view()),
]
