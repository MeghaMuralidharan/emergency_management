from django.db import migrations

# old role -> (new job role, counter / desk)
MAP = {
    "Hospital Reception": ("Front Desk", "Hospital reception"),
    "Booking Counter": ("Booking Clerk", "Booking counter"),
    "Pharmacy": ("Pharmacist", "Pharmacy"),
    "Lab": ("Lab Technician", "Lab"),
}


def convert(apps, schema_editor):
    StaffProfile = apps.get_model("core", "StaffProfile")
    for p in StaffProfile.objects.all():
        if p.role in MAP:
            p.role, p.counter = MAP[p.role]
            p.save()
        elif p.role == "Receptionist" and not p.counter:
            p.counter = "Department reception"
            p.save()


class Migration(migrations.Migration):
    dependencies = [("core", "0011_staffprofile_counter_staffprofile_skills_and_more")]
    operations = [migrations.RunPython(convert, migrations.RunPython.noop)]
