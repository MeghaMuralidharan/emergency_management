from django.db import migrations, models
import django.db.models.deletion


def to_wards(apps, schema_editor):
    Ward = apps.get_model("core", "Ward")
    Bed = apps.get_model("core", "Bed")
    cats = {"ICU": "ICU", "Emergency": "Emergency"}
    counters = {}
    for bed in Bed.objects.all().order_by("pk"):
        name = (bed.legacy_ward or "General Ward").strip()
        ward = Ward.objects.filter(name=name).first()
        if ward is None:
            ward = Ward.objects.create(name=name, category=cats.get(bed.legacy_type, "Ward"))
        counters[ward.pk] = counters.get(ward.pk, 0) + 1
        bed.ward = ward
        bed.number = counters[ward.pk]
        bed.save()


class Migration(migrations.Migration):
    dependencies = [("core", "0014_department_user_patient_department")]

    operations = [
        migrations.CreateModel(
            name="Ward",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=60, unique=True)),
                ("category", models.CharField(choices=[("ICU", "ICU"), ("Shared ICU", "Shared ICU"), ("Ward", "Ward"), ("Room", "Room"),
                                                       ("Personal Room", "Personal Room"), ("VIP Room", "VIP Room"), ("Emergency", "Emergency")], max_length=20)),
                ("floor", models.CharField(blank=True, max_length=60)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.RenameField("bed", "ward", "legacy_ward"),
        migrations.RenameField("bed", "bed_type", "legacy_type"),
        migrations.AddField("bed", "number", models.PositiveSmallIntegerField(default=1)),
        migrations.AddField("bed", "ward", models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name="beds", to="core.ward")),
        migrations.AlterField("bed", "bed_number", models.CharField(max_length=80, unique=True)),
        migrations.RunPython(to_wards, migrations.RunPython.noop),
        migrations.RemoveField("bed", "legacy_ward"),
        migrations.RemoveField("bed", "legacy_type"),
        migrations.AlterField("bed", "ward", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="beds", to="core.ward")),
        migrations.AlterModelOptions("bed", options={"ordering": ["ward__name", "number"]}),
    ]
