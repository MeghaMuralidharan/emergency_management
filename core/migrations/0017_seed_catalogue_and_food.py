from django.db import migrations

CATALOGUE = {
    "Blood": [
        "Complete Blood Count (CBC)", "Hemoglobin", "ESR", "Blood Sugar (Fasting)", "Blood Sugar (Post-meal)", "HbA1c",
        "Lipid Profile", "Liver Function Test (LFT)", "Kidney Function Test (KFT)", "Serum Electrolytes",
        "Thyroid Profile (TSH)", "Blood Group & Rh", "C-Reactive Protein (CRP)", "Troponin I", "D-Dimer",
        "Coagulation (PT / INR)", "Serum Creatinine", "Blood Urea",
    ],
    "Urine": ["Urine Routine", "Urine Culture"],
    "Imaging": ["X-ray Chest", "ECG", "Ultrasound Abdomen", "CT Scan", "MRI"],
    "Microbiology": ["Blood Culture", "Swab Culture"],
}


def seed(apps, schema_editor):
    LabTestType = apps.get_model("core", "LabTestType")
    Department = apps.get_model("core", "Department")
    for category, names in CATALOGUE.items():
        for name in names:
            LabTestType.objects.get_or_create(name=name, defaults={"category": category})
    # the food (dietary) department is a service unit like Pharmacy and Lab
    Department.objects.get_or_create(name="Food Department", defaults={"is_service": True, "description": "Kitchen and patient meals"})


class Migration(migrations.Migration):
    dependencies = [("core", "0016_equipment_labtesttype_medicinestock_labtest_urgent_and_more")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
