from django.conf.urls import url, include
from roommanager import api

from roommanager import views


urlpatterns = [
    url(r'^api/v1/', include([
        url(r'^laundry-rooms$', api.LaundryRoomList.as_view(), name='laundry-room-list'),
        url(r'^machines$', api.MachineList.as_view(), name='machine-list'),
        url(r'^slots$', api.SlotList.as_view(), name='slot-list'),
    ])),
    url(r'^ondemand-laundryroom-sync/$', views.OnDemandLaundryRoomSync.as_view()),
    url(r'^hardware-bundle-pairing-webhook/$', views.HardwareBundleView.as_view()),
    url(r'^update-machineslotmap/$', views.UpdateMachineSlotMap.as_view()),
    url(r'^search-machine/$', views.SearchMachineView.as_view()),
    url(r'^hardware-bundle-changes/$', views.HardwareBundleChangesView.as_view()),
    url(r'^bundle-change-approval/(?P<pk>[0-9]+)/$', views.BundleChangeApprovalUpdateView.as_view()),
    url(r'^asset-update-approval/(?P<pk>[0-9]+)/$', views.AssetUpdateApprovalView.as_view()),
    url(r'^bundle-changes/$', views.BundleChangeListView.as_view()),
    url(r'^approved-bundle-changes/$', views.ApprovedBundleChangeListView.as_view()),
    url(r'^rejected-bundle-changes/$', views.RejectedBundleChangeListView.as_view()),
    url(r'^orphaned-piece-required-answer/(?P<pk>[0-9]+)/$', views.OrphanedPieceAnswerUpdateView.as_view()),
    url(r'^asset-mapout-approval/(?P<pk>[0-9]+)/$', views.AssetMapOutUpdateView.as_view()),
    url(r'^swap-tag-approval/(?P<pk>[0-9]+)/$', views.SwapTagLogUpdateView.as_view()),
    url(r'^first-transaction/$', views.FirstTransactionView.as_view()),
    url(r'^repair-replace/(?P<slug>[-\w]+)/$', views.RepairReplaceView.as_view(), name='repair_replace_report'),
    url(r'^locations/$', views.LocationsListView.as_view()),
    url(r'^slot-label-check/$', views.SlotLabelCheckTriggerView.as_view()),
    url(r'^manual-mapout/$', views.ManualAssetMapoutCreateView.as_view()),
    url(r'^create/$', views.MachineMeterReadingCreateView.as_view(), name='create_meter_reading'),
]