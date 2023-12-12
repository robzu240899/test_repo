
from django.conf.urls import  url
from django.contrib.auth.decorators import login_required
from .queue import InboundMessageView
from .views import NightlyRunProcess, TestView, NightlyRunEnqueue, EmployeeScansAnalysisEnqueuerView, MaintainxMeterUpdateEnqueuerView

urlpatterns = [
      url(r'^process/', InboundMessageView.as_view()),
      url(r'^nightly-run-process/', NightlyRunProcess.as_view()),
      url(r'^nightly-run-enqueue/', NightlyRunEnqueue.as_view(), {'jobname':'nightlyrun'}),
      url(r'^on-demand-transaction-ingest/', NightlyRunEnqueue.as_view(), {'jobname':'tiedrun','stepstorun':'transaction_ingest,match,employee_scans_analysis'}),
      url(r'^nightly-metrics-enqueue/', NightlyRunEnqueue.as_view(), {'jobname':'nightlymetricsrun'}),
      url(r'^maintainx-meters-update/', MaintainxMeterUpdateEnqueuerView.as_view()),
      url(r'^tied-steps-ooo/', NightlyRunEnqueue.as_view(), {'jobname':'tiedrun','stepstorun':'ingest_slot_states,send_ooo'}),
      url(r'^test/', TestView.as_view()),
      url(r'^employeescansanalysis/', EmployeeScansAnalysisEnqueuerView.as_view()),
]
