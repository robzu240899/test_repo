from django.conf import settings
from django.conf.urls import include, url
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import login
from django.urls import path
from main import views


admin.autodiscover()
admin.site.enable_nav_sidebar = False

urlpatterns = [
      url(r'^admin/', admin.site.urls),
      url(r'^menu/',views.MenuView.as_view()),
      url(r'^manual/ooo',views.ManualOOOView.as_view()),
      url(r'^manual/daily-upkeep-report',views.ManualUpkeepReportView.as_view()),
      url(r'^manual/metrics',views.MetricsRecaculationView.as_view()),
      url(r'^manual/revenue',views.ManualReingestTransactionsView.as_view()),
      url(r'^manual/nightly-run',views.ManualNightlyRun.as_view()),
      url(r'^manual/match',views.RevenueMatchView.as_view()),
      url(r'^manual/slots-fascard-sync',views.ManualSlotsFascardSync.as_view()),
      url(r'^queue/',include('queuehandler.urls')),
      url(r'^revenue-reporting/',include('reporting.finance.urls')),
      url(r'^reporting/',include('reporting.urls')),
      url(r'^reports/',include('reports.urls')),
      url(r'^expensetracker/', include('expensetracker.urls')),
      url(r'^accounts/', include('django.contrib.auth.urls')),
      url(r'^roommanager/', include('roommanager.urls')),
      url(r'^revenue/', include('revenue.urls')),
      url(r'^upkeep/', include('upkeep.urls')),
      path('explorer/', include('explorer.urls')),
      path('data-browser/', include('data_browser.urls')),
      # url(r'^__debug__/', include(debug_toolbar.urls)),
    ] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
