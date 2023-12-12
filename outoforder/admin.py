from datetime import date
from dateutil.relativedelta import relativedelta
from django.contrib import admin
from .models import SlotState, SlotStateError

class SlotStateErrorInline(admin.TabularInline):
    model = SlotStateError


class SlotStateErrorAdmin(admin.ModelAdmin):
    list_display = ['get_slot', 'get_laundry_room', 'error_type', 'get_local_slotstate_time']
    list_filter = ('slot_state__slot__laundry_room',)

class SlotStateAdmin(admin.ModelAdmin):
    inlines = [
        SlotStateErrorInline
    ]
    list_display = ['slot', 'local_start_time', 'local_end_time', 'get_readable_slot_status']
    list_filter = ('slot',)

    # def local_start_time(self, obj):
    #     return obj.local_start_time

    # local_start_time.admin_order_field = '-local_start_time'

    def get_queryset(self, request):
        #qs = super(SlotStateAdmin, self).get_queryset(request)
        starting_date = date.today() - relativedelta(months=1)
        #return qs.filter()
        return SlotState.objects.filter(local_start_time__gt=starting_date).order_by('-local_start_time')

#admin.site.register(SlotState, SlotStateAdmin)
#admin.site.register(SlotStateError, SlotStateErrorAdmin)