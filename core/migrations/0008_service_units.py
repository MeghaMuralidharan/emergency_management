from django.db import migrations

UNITS = ["Pharmacy", "Lab", "Hospital Reception", "Booking Counter"]


def seed(apps, schema_editor):
    Department = apps.get_model("core", "Department")
    StaffProfile = apps.get_model("core", "StaffProfile")
    for name in UNITS:
        Department.objects.update_or_create(name=name, defaults={"is_service": True})
        # existing staff of that kind belong to the unit
        StaffProfile.objects.filter(role=name).update(department=name)


class Migration(migrations.Migration):
    dependencies = [("core", "0007_department_is_service_staffprofile_leave_note_and_more")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
