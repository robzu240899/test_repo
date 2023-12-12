from django.contrib import admin
from expensetracker.models import Job, Technician, LineItem
 
# Register your models here.
admin.site.register(Job)
admin.site.register(Technician)
admin.site.register(LineItem)
