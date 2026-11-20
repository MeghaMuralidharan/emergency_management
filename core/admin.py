from django.contrib import admin
from .models import Patient, StaffProfile, Bed, Ambulance
admin.site.register([Patient, StaffProfile, Bed, Ambulance])
