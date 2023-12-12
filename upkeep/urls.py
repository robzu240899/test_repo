from django.urls import path
from .views import NonGeneratedView


urlpatterns = [
    path('upkeep-cleaning/', NonGeneratedView.as_view(), name='report_manager'),
]