from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from core.models import StaffProfile, Ward, Bed, Ambulance, Patient

class Command(BaseCommand):
    help = "Create fictional sample data and a demo admin account."
    def handle(self, *args, **kwargs):
        user, created = User.objects.get_or_create(username="admin", defaults={"email":"admin@example.com", "is_staff":True, "is_superuser":True})
        if created: user.set_password("Admin@12345"); user.save()
        doctors = []
        for name, role, dept, status in [
            ("Dr. Maya Nair","Doctor","Emergency Medicine","Available"),
            ("Dr. Arjun Menon","Doctor","Critical Care","Busy"),
            ("Anita Joseph","Nurse","Emergency","Available"),
            ("Ravi Kumar","Triage Staff","Triage","Available"),
            ("Meera Das","Receptionist","Front Desk","Available"),
        ]:
            obj, _ = StaffProfile.objects.get_or_create(full_name=name, defaults={"role":role,"department":dept,"status":status})
            if role == "Doctor": doctors.append(obj)
        for name, category, count in [("Emergency Bay", "Emergency", 4), ("ICU 1", "ICU", 1), ("Shared ICU", "Shared ICU", 4),
                                      ("Ward A", "Ward", 8), ("Room 204", "Room", 2), ("VIP 1", "VIP Room", 1)]:
            ward, created = Ward.objects.get_or_create(name=name, defaults={"category": category})
            if created:
                ward.add_beds(count)
        Ambulance.objects.get_or_create(vehicle_number="KL-07-AB-1024", defaults={"ambulance_type":"Emergency","driver_name":"Suresh P.","contact":"9876500001","location":"Main entrance","status":"Available"})
        Ambulance.objects.get_or_create(vehicle_number="KL-07-CD-2048", defaults={"ambulance_type":"ICU","driver_name":"Nikhil R.","contact":"9876500002","location":"City bypass","status":"Dispatched"})
        if not Patient.objects.exists():
            Patient.objects.create(name="Ananya S.", age=34, gender="Female", contact="9876501111", complaint="Chest discomfort and breathlessness", severity="Critical", status="In Treatment", assigned_doctor=doctors[0])
            Patient.objects.create(name="Rahul K.", age=52, gender="Male", contact="9876502222", complaint="Fall with suspected wrist injury", severity="Serious", status="Waiting")
            Patient.objects.create(name="Joseph M.", age=27, gender="Male", contact="9876503333", complaint="High fever and dehydration", severity="Stable", status="Waiting")
        self.stdout.write(self.style.SUCCESS("Demo data ready. Login: admin / Admin@12345"))
