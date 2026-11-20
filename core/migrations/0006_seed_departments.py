from django.db import migrations

DEFAULTS = ["Emergency", "ENT", "Cardiology", "Orthopedics", "Neurology", "Pediatrics",
            "General Medicine", "Surgery", "Gynecology", "Radiology", "ICU", "Psychology"]


def seed(apps, schema_editor):
    Department = apps.get_model("core", "Department")
    StaffProfile = apps.get_model("core", "StaffProfile")
    names = list(DEFAULTS)
    # keep any department names already used by existing staff
    for n in StaffProfile.objects.exclude(department="").values_list("department", flat=True).distinct():
        if n not in names:
            names.append(n)
    for n in names:
        Department.objects.get_or_create(name=n)


class Migration(migrations.Migration):
    dependencies = [("core", "0005_department")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
