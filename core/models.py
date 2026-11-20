from django.db import models
from django.contrib.auth.models import User

class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=250, blank=True)
    user = models.OneToOneField(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="department_account")  # department login
    is_service = models.BooleanField(default=False, help_text="Service unit such as pharmacy or lab (staff only, no doctors)")
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ["name"]
    def __str__(self): return self.name

class StaffProfile(models.Model):
    ROLE_CHOICES = [(x, x) for x in ["Admin", "Doctor", "Nurse", "Triage Staff", "Receptionist", "Front Desk", "Pharmacist", "Lab Technician", "Booking Clerk"]]
    STATUS_CHOICES = [("Available", "Available"), ("Busy", "Busy"), ("Off Duty", "Off Duty")]
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    full_name = models.CharField(max_length=120)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    department = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=25, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="Available")
    shift_start = models.TimeField(null=True, blank=True)
    shift_end = models.TimeField(null=True, blank=True)
    on_leave = models.BooleanField(default=False)
    leave_note = models.CharField(max_length=150, blank=True)
    counter = models.CharField(max_length=40, blank=True)   # desk / counter they work at
    skills = models.CharField(max_length=300, blank=True)   # comma separated skills / specialities
    def __str__(self): return f"{self.full_name} — {self.role}"

    @property
    def skills_list(self):
        return [x.strip() for x in self.skills.split(",") if x.strip()]

    @property
    def shift_label(self):
        if self.shift_start and self.shift_end:
            return f"{self.shift_start:%H:%M} – {self.shift_end:%H:%M}"
        return "Not set"

    @property
    def availability(self):
        """On leave / On duty (now) / Off shift, based on leave flag and shift timing."""
        if self.on_leave:
            return "On leave"
        if self.shift_start and self.shift_end:
            from django.utils import timezone
            now = timezone.localtime().time()
            s, e = self.shift_start, self.shift_end
            within = (s <= now < e) if s < e else (now >= s or now < e)  # handles night shifts
            return "On duty" if within else "Off shift"
        return "Off shift" if self.status == "Off Duty" else "On duty"

class Patient(models.Model):
    SEVERITY = [("Critical", "Critical"), ("Serious", "Serious"), ("Stable", "Stable"), ("Not triaged", "Not triaged")]
    STATUS = [("Waiting", "Waiting"), ("In Treatment", "In Treatment"), ("Admitted", "Admitted"), ("Discharged", "Discharged")]
    name = models.CharField(max_length=120)
    age = models.PositiveSmallIntegerField()
    gender = models.CharField(max_length=20, blank=True)
    contact = models.CharField(max_length=25, blank=True)
    complaint = models.TextField()
    department = models.CharField(max_length=100, blank=True)   # department the patient belongs to
    arrival_time = models.DateTimeField(auto_now_add=True)
    severity = models.CharField(max_length=20, choices=SEVERITY, default="Not triaged")
    status = models.CharField(max_length=20, choices=STATUS, default="Waiting")
    assigned_doctor = models.ForeignKey(StaffProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="patients")
    bed = models.ForeignKey("Bed", null=True, blank=True, on_delete=models.SET_NULL, related_name="patients")
    notes = models.TextField(blank=True)
    def __str__(self): return f"{self.name} ({self.id})"
    @property
    def priority(self):
        return {"Critical": 1, "Serious": 2, "Stable": 3, "Not triaged": 4}.get(self.severity, 5)

class Ward(models.Model):
    """A ward, ICU, room... that holds one or more beds."""
    CATEGORY_NAMES = ["ICU", "Shared ICU", "Ward", "Room", "Personal Room", "VIP Room", "Emergency"]
    CATEGORIES = [(c, c) for c in CATEGORY_NAMES]
    # sensible number of beds when a new one is created
    DEFAULT_BEDS = {"ICU": 1, "Shared ICU": 4, "Ward": 10, "Room": 2, "Personal Room": 1, "VIP Room": 1, "Emergency": 6}
    name = models.CharField(max_length=60, unique=True)
    category = models.CharField(max_length=20, choices=CATEGORIES)
    floor = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ["name"]
    def __str__(self): return self.name

    @property
    def total(self): return self.beds.count()
    @property
    def free(self): return self.beds.filter(status="Available").count()
    @property
    def occupied(self): return self.beds.filter(status="Occupied").count()

    def bed_label(self, number): return f"{self.name} · B{number}"

    def renumber(self):
        """Keep bed names in step with the ward name."""
        for bed in self.beds.all():
            bed.bed_number = self.bed_label(bed.number)
            bed.save(update_fields=["bed_number"])

    def add_beds(self, count):
        last = self.beds.aggregate(m=models.Max("number"))["m"] or 0
        for i in range(1, count + 1):
            Bed.objects.create(ward=self, number=last + i, bed_number=self.bed_label(last + i))


class Bed(models.Model):
    STATUS = [("Available", "Available"), ("Occupied", "Occupied"), ("Cleaning", "Cleaning")]
    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name="beds")
    number = models.PositiveSmallIntegerField(default=1)
    bed_number = models.CharField(max_length=80, unique=True)
    status = models.CharField(max_length=15, choices=STATUS, default="Available")
    class Meta: ordering = ["ward__name", "number"]
    def __str__(self): return f"{self.bed_number} — {self.ward.category}"

class Ambulance(models.Model):
    STATUS = [("Available", "Available"), ("Dispatched", "Dispatched"), ("Returning", "Returning"), ("Maintenance", "Maintenance")]
    TYPES = [(t, t) for t in ["Normal", "Emergency", "ICU", "Advanced Life Support", "Neonatal", "Patient Transport"]]
    vehicle_number = models.CharField(max_length=25, unique=True)
    ambulance_type = models.CharField(max_length=30, choices=TYPES, default="Normal")
    driver_name = models.CharField(max_length=100)
    contact = models.CharField(max_length=25, blank=True)
    location = models.CharField(max_length=150, blank=True)
    status = models.CharField(max_length=15, choices=STATUS, default="Available")
    def __str__(self): return self.vehicle_number


class Medicine(models.Model):
    """A medicine prescribed to a patient by a doctor and dispensed by the pharmacy."""
    STATUS = [("Prescribed", "Prescribed"), ("Dispensed", "Dispensed"), ("Stopped", "Stopped")]
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="medicines")
    name = models.CharField(max_length=120)
    dosage = models.CharField(max_length=60)
    frequency = models.CharField(max_length=60)
    duration = models.CharField(max_length=60, blank=True)
    instructions = models.CharField(max_length=250, blank=True)
    status = models.CharField(max_length=15, choices=STATUS, default="Prescribed")
    prescribed_by = models.ForeignKey(StaffProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="prescriptions")
    dispensed_by = models.ForeignKey(StaffProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="dispensed_medicines")
    created_at = models.DateTimeField(auto_now_add=True)
    dispensed_at = models.DateTimeField(null=True, blank=True)
    class Meta: ordering = ["-created_at"]
    def __str__(self): return f"{self.name} for {self.patient}"


class LabTest(models.Model):
    """A lab test requested by a doctor (or added directly by the lab) with its result."""
    STATUS = [("Requested", "Requested"), ("Completed", "Completed")]
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="tests")
    name = models.CharField(max_length=120)
    status = models.CharField(max_length=15, choices=STATUS, default="Requested")
    result = models.TextField(blank=True)
    notes = models.CharField(max_length=250, blank=True)
    urgent = models.BooleanField(default=False)
    test_type = models.ForeignKey("LabTestType", null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    requested_by = models.ForeignKey(StaffProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="tests_requested")
    done_by = models.ForeignKey(StaffProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="tests_done")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    class Meta: ordering = ["-created_at"]
    def __str__(self): return f"{self.name} for {self.patient}"


class ProgressNote(models.Model):
    """A doctor's update on whether the patient's health is improving."""
    CONDITIONS = [(c, c) for c in ["Improving", "Stable", "Not improving", "Worsening"]]
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="progress")
    condition = models.CharField(max_length=20, choices=CONDITIONS)
    note = models.TextField()
    recorded_by = models.ForeignKey(StaffProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="progress_notes")
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ["-created_at"]
    def __str__(self): return f"{self.condition} - {self.patient}"


class LabTestType(models.Model):
    """A test the lab offers (the catalogue doctors choose checkups from)."""
    CATEGORIES = [(c, c) for c in ["Blood", "Urine", "Imaging", "Microbiology", "Other"]]
    name = models.CharField(max_length=120, unique=True)
    category = models.CharField(max_length=20, choices=CATEGORIES, default="Blood")
    notes = models.CharField(max_length=200, blank=True)   # e.g. fasting needed, turnaround time
    available = models.BooleanField(default=True)
    class Meta: ordering = ["category", "name"]
    def __str__(self): return self.name


class MedicineStock(models.Model):
    """A medicine the pharmacy keeps, with how much is in stock."""
    FORMS = [(f, f) for f in ["Tablet", "Capsule", "Syrup", "Injection", "Ointment", "Drops", "Inhaler", "Other"]]
    name = models.CharField(max_length=120, unique=True)
    strength = models.CharField(max_length=60, blank=True)          # e.g. 500 mg
    form = models.CharField(max_length=20, choices=FORMS, blank=True)
    quantity = models.PositiveIntegerField(default=0)
    unit = models.CharField(max_length=20, default="units")
    reorder_level = models.PositiveIntegerField(default=10)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta: ordering = ["name"]
    def __str__(self): return self.name

    @property
    def level(self):
        if self.quantity == 0:
            return "Out of stock"
        return "Low stock" if self.quantity <= self.reorder_level else "In stock"


class Equipment(models.Model):
    """Equipment a unit (mainly the lab) owns."""
    STATUS = [(s, s) for s in ["Available", "In use", "Under maintenance", "Out of order"]]
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=60, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS, default="Available")
    location = models.CharField(max_length=100, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta: ordering = ["name"]
    def __str__(self): return self.name


class SupplyRequest(models.Model):
    """A unit (pharmacy, lab, a department, the food department...) asks the admin for medicines, equipment or supplies."""
    KINDS = [(k, k) for k in ["Medicine", "Equipment", "Supplies"]]
    STATUS = [(s, s) for s in ["Requested", "Approved", "Delivered", "Rejected"]]
    unit = models.CharField(max_length=100)
    kind = models.CharField(max_length=15, choices=KINDS)
    item = models.CharField(max_length=120)
    quantity = models.PositiveIntegerField(default=1)
    reason = models.TextField(blank=True)
    urgent = models.BooleanField(default=False)
    status = models.CharField(max_length=15, choices=STATUS, default="Requested")
    admin_note = models.CharField(max_length=200, blank=True)
    requested_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="supply_requests")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta: ordering = ["-created_at"]
    def __str__(self): return f"{self.item} for {self.unit}"


class Referral(models.Model):
    """A doctor sends a patient to another department; the department then picks one of its doctors."""
    STATUS = [(s, s) for s in ["Pending", "Assigned", "Completed"]]
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="referrals")
    from_doctor = models.ForeignKey(StaffProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="referrals_made")
    to_department = models.CharField(max_length=100)
    reason = models.TextField()
    status = models.CharField(max_length=15, choices=STATUS, default="Pending")
    assigned_doctor = models.ForeignKey(StaffProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="referrals_received")
    created_at = models.DateTimeField(auto_now_add=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    class Meta: ordering = ["-created_at"]
    def __str__(self): return f"{self.patient} -> {self.to_department}"
