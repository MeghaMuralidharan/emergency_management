from django.db.models import F
from .permissions import (admin_required, doctor_required, pharmacist_required, lab_required, staff_required,
                          department_required, clinical_required, request_roles_required, referral_assign_required, role_of, HOME)
from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from .models import (Ward, Department, Patient, StaffProfile, Bed, Ambulance, Medicine, LabTest, ProgressNote, LabTestType,
                     MedicineStock, Equipment, SupplyRequest, Referral)
from .forms import DEPT_RECEPTION, DepartmentForm, DepartmentAccountForm, StaffProfileForm, DoctorCreateForm, StaffAccountForm, staff_patient_form, PatientForm, WardForm, AmbulanceForm, MedicineForm, TestAddForm, TestResultForm, ProgressForm , CheckupForm, ReferralForm, MedicineStockForm, EquipmentForm, LabTestTypeForm, SupplyRequestForm

@admin_required
def dashboard(request):
    today = timezone.localdate()
    patients = Patient.objects.all()
    context = {
        "total_today": patients.filter(arrival_time__date=today).count(),
        "waiting": patients.filter(status="Waiting").count(),
        "critical": patients.filter(severity="Critical").exclude(status="Discharged").count(),
        "occupied_beds": Bed.objects.filter(status="Occupied").count(),
        "total_beds": Bed.objects.count(),
        "available_staff": StaffProfile.objects.filter(status="Available").count(),
        "ambulances": Ambulance.objects.filter(status="Available").count(),
        "queue": sorted(patients.exclude(status="Discharged"), key=lambda p: (p.priority, p.arrival_time))[:7],
        "recent": patients.order_by("-arrival_time")[:5],
    }
    return render(request, "core/dashboard.html", context)

def _view_mode(request):
    return "list" if request.GET.get("view") == "list" else "grid"


TYPE_OPTIONS = [("", "All people"), ("Doctor", "Doctors"), ("staff", "All staff (non-doctors)"), ("Nurse", "Nurses"),
                ("Pharmacist", "Pharmacists"), ("Receptionist", "Receptionists"), ("Front Desk", "Front desk"),
                ("Lab Technician", "Lab technicians"), ("Triage Staff", "Triage staff"), ("Booking Clerk", "Booking clerks")]


@admin_required
def staff_list(request):
    q = request.GET.get("q", "").strip()
    kind = request.GET.get("type", "")
    if kind not in dict(TYPE_OPTIONS):
        kind = ""
    people = StaffProfile.objects.select_related("user").order_by("role", "full_name")
    if kind == "staff":
        people = people.exclude(role="Doctor")
    elif kind:
        people = people.filter(role=kind)
    if q:
        people = people.filter(Q(full_name__icontains=q) | Q(role__icontains=q) | Q(department__icontains=q)
                               | Q(counter__icontains=q) | Q(skills__icontains=q)
                               | Q(phone__icontains=q) | Q(user__username__icontains=q))
    return render(request, "core/staff.html", {"staff": people, "q": q, "type": kind, "types": TYPE_OPTIONS, "view": _view_mode(request)})


@admin_required
def hospital_directory(request):
    q = request.GET.get("q", "").strip()
    depts = Department.objects.all()
    if q:
        depts = depts.filter(Q(name__icontains=q) | Q(description__icontains=q))
    rows = []
    for d in depts:
        people = StaffProfile.objects.filter(department=d.name)
        rows.append({
            "dept": d,
            "doctors": people.filter(role="Doctor").count(),
            "staff": people.exclude(role="Doctor").count(),
            "on_leave": people.filter(on_leave=True).count(),
            "reception": people.filter(counter=DEPT_RECEPTION).first(),
        })
    return render(request, "core/hospital.html", {"rows": rows, "q": q, "view": _view_mode(request), "total": Department.objects.count()})


@admin_required
def department_detail(request, pk):
    dept = get_object_or_404(Department, pk=pk)
    q = request.GET.get("q", "").strip()
    everyone = list(StaffProfile.objects.filter(department=dept.name).select_related("user").order_by("role", "full_name"))
    people = [p for p in everyone if not q or q.lower() in " ".join(
        [p.full_name, p.role, p.phone, p.user.username if p.user else ""]).lower()]
    return render(request, "core/department.html", {
        "dept": dept, "q": q, "view": _view_mode(request),
        "doctors": [p for p in people if p.role == "Doctor"],
        "others": [p for p in people if p.role != "Doctor"],
        "n_doctors": sum(1 for p in everyone if p.role == "Doctor"),
        "n_staff": sum(1 for p in everyone if p.role != "Doctor"),
        "n_leave": sum(1 for p in everyone if p.on_leave),
        "n_on_duty": sum(1 for p in everyone if p.availability == "On duty"),
    })


def _dept_patients(dept):
    """Patients of a department: registered into it, or (if no department was set) seen by one of its doctors."""
    return Patient.objects.filter(Q(department=dept.name) | Q(department="", assigned_doctor__department=dept.name)
                                  | Q(referrals__to_department=dept.name)).distinct()


def _dept_context(dept):
    people = list(StaffProfile.objects.filter(department=dept.name).select_related("user").order_by("role", "full_name"))
    patients = []
    if not dept.is_service:
        qs = _dept_patients(dept).exclude(status="Discharged").select_related("assigned_doctor", "bed")
        patients = sorted(qs, key=lambda p: (p.priority, p.arrival_time))
    referrals = list(Referral.objects.filter(to_department=dept.name).exclude(status="Completed")
                     .select_related("patient", "from_doctor", "assigned_doctor"))
    return {
        "dept": dept, "people": people, "patients": patients, "referrals": referrals,
        "dept_doctors": [p for p in people if p.role == "Doctor"],
        "n_referrals_pending": sum(1 for r in referrals if r.status == "Pending"),
        "n_active": len(patients),
        "n_critical": sum(1 for p in patients if p.severity == "Critical"),
        "n_treatment": sum(1 for p in patients if p.status == "In Treatment"),
        "n_waiting": sum(1 for p in patients if p.status == "Waiting"),
        "n_doctors": sum(1 for p in people if p.role == "Doctor"),
        "n_staff": sum(1 for p in people if p.role != "Doctor"),
        "n_on_duty": sum(1 for p in people if p.availability == "On duty"),
        "n_leave": sum(1 for p in people if p.on_leave),
    }


@admin_required
def department_dashboard(request, pk):
    """Admin: full-page view of a department's dashboard."""
    dept = get_object_or_404(Department, pk=pk)
    return render(request, "core/department_dashboard.html", {**_dept_context(dept), "preview": True})


@department_required
def department_home(request):
    """A department's own login lands here: its dashboard (read-only)."""
    return render(request, "core/department_portal.html", {**_dept_context(request.user.department_account), "can_assign": True})


@admin_required
def department_account(request, pk):
    """Admin: create the department's login, or reset its password."""
    dept = get_object_or_404(Department.objects.select_related("user"), pk=pk)
    form = DepartmentAccountForm(dept, request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, f"{dept.name} login saved. Sign in at /department/ with username {dept.user.username}.")
        return redirect("department_detail", dept.pk)
    return render(request, "core/form.html", {
        "form": form, "eyebrow": "DEPARTMENT LOGIN",
        "heading": f"{'Reset password' if dept.user_id else 'Create login'} · {dept.name}"})


@admin_required
def department_create(request):
    form = DepartmentForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, "Department created with its login. It is now available in the doctor and reception forms.")
        return redirect("hospital")
    return render(request, "core/form.html", {"form": form, "heading": "Create department", "eyebrow": "HOSPITAL DIRECTORY"})


CATEGORY_OPTIONS = [("", "All types")] + Ward.CATEGORIES
BED_STATUS_OPTIONS = [("", "All bed states"), ("Available", "Has available beds"), ("Occupied", "Has occupied beds"), ("Cleaning", "Being cleaned")]


@admin_required
def bed_list(request):
    q = request.GET.get("q", "").strip()
    category = request.GET.get("category", "")
    bed_state = request.GET.get("state", "")
    category = category if category in dict(CATEGORY_OPTIONS) else ""
    bed_state = bed_state if bed_state in dict(BED_STATUS_OPTIONS) else ""
    wards = Ward.objects.prefetch_related("beds")
    if category:
        wards = wards.filter(category=category)
    if bed_state:
        wards = wards.filter(beds__status=bed_state).distinct()
    if q:
        wards = wards.filter(Q(name__icontains=q) | Q(floor__icontains=q) | Q(category__icontains=q))
    wards = list(wards.order_by("category", "name"))
    for w in wards:
        bs = list(w.beds.all())
        w.bed_list = bs
        w.n_total, w.n_free = len(bs), sum(1 for b in bs if b.status == "Available")
        w.n_occupied, w.n_cleaning = sum(1 for b in bs if b.status == "Occupied"), sum(1 for b in bs if b.status == "Cleaning")
    summary = []
    for cat in Ward.CATEGORY_NAMES:
        beds = Bed.objects.filter(ward__category=cat)
        units = Ward.objects.filter(category=cat).count()
        if units:
            summary.append({"category": cat, "units": units, "beds": beds.count(), "free": beds.filter(status="Available").count()})
    return render(request, "core/beds.html", {
        "wards": wards, "q": q, "category": category, "state": bed_state, "view": _view_mode(request),
        "categories": CATEGORY_OPTIONS, "states": BED_STATUS_OPTIONS, "summary": summary,
        "n_wards": Ward.objects.count(), "n_beds": Bed.objects.count(),
        "n_free": Bed.objects.filter(status="Available").count(), "n_occupied": Bed.objects.filter(status="Occupied").count(),
        "n_cleaning": Bed.objects.filter(status="Cleaning").count(),
    })


@admin_required
def bed_create(request):
    """Create a ward / ICU / room together with its beds."""
    form = WardForm(request.POST or None)
    if form.is_valid():
        ward = form.save()
        messages.success(request, f"{ward.name} created with {ward.total} bed{'s' if ward.total != 1 else ''}.")
        return redirect("ward_detail", ward.pk)
    return render(request, "core/form.html", {"form": form, "heading": "Add ward / room", "eyebrow": "BEDS & WARDS"})


def _active_patients_in(beds):
    """Map bed id -> the patient currently in it (discharged patients do not count)."""
    return {p.bed_id: p for p in Patient.objects.filter(bed__in=beds).exclude(status="Discharged")}


@admin_required
def ward_detail(request, pk):
    ward = get_object_or_404(Ward, pk=pk)
    beds = list(ward.beds.all())
    current = _active_patients_in(beds)
    for b in beds:
        b.current = current.get(b.pk)
    return render(request, "core/ward_detail.html", {
        "ward": ward, "beds": beds, "n_total": len(beds),
        "n_free": sum(1 for b in beds if b.status == "Available"),
        "n_occupied": sum(1 for b in beds if b.status == "Occupied"),
        "n_cleaning": sum(1 for b in beds if b.status == "Cleaning"),
    })


@admin_required
def ward_edit(request, pk):
    ward = get_object_or_404(Ward, pk=pk)
    form = WardForm(request.POST or None, instance=ward)
    if form.is_valid():
        form.save()
        messages.success(request, f"{ward.name} updated.")
        return redirect("ward_detail", ward.pk)
    return render(request, "core/form.html", {"form": form, "heading": f"Edit {ward.name}", "eyebrow": "BEDS & WARDS"})


@admin_required
def ward_delete(request, pk):
    ward = get_object_or_404(Ward, pk=pk)
    if request.method == "POST":
        if _active_patients_in(ward.beds.all()):
            messages.error(request, f"{ward.name} has patients in its beds. Move or discharge them first.")
            return redirect("ward_detail", ward.pk)
        name = ward.name
        ward.delete()
        messages.success(request, f"{name} deleted.")
    return redirect("beds")


@admin_required
def bed_add(request, pk):
    ward = get_object_or_404(Ward, pk=pk)
    if request.method == "POST":
        ward.add_beds(1)
        messages.success(request, f"Bed added to {ward.name}.")
    return redirect("ward_detail", ward.pk)


@admin_required
def bed_status(request, pk):
    bed = get_object_or_404(Bed, pk=pk)
    new = request.POST.get("status")
    if request.method == "POST" and new in ("Available", "Cleaning"):
        if _active_patients_in([bed]):
            messages.error(request, f"{bed.bed_number} has a patient in it.")
        else:
            bed.status = new
            bed.save()
            messages.success(request, f"{bed.bed_number} marked {new.lower()}.")
    return redirect("ward_detail", bed.ward_id)


@admin_required
def bed_delete(request, pk):
    bed = get_object_or_404(Bed, pk=pk)
    ward_id = bed.ward_id
    if request.method == "POST":
        if _active_patients_in([bed]):
            messages.error(request, f"{bed.bed_number} has a patient in it, so it cannot be deleted.")
        else:
            label = bed.bed_number
            bed.delete()
            messages.success(request, f"{label} deleted.")
    return redirect("ward_detail", ward_id)


@admin_required
def ambulance_list(request):
    return render(request, "core/ambulances.html", {"ambulances": Ambulance.objects.all()})

@admin_required
def ambulance_create(request):
    form = AmbulanceForm(request.POST or None)
    if form.is_valid(): form.save(); messages.success(request, "Ambulance record added."); return redirect("ambulances")
    return render(request, "core/form.html", {"form": form, "heading": "Add ambulance", "eyebrow": "EMERGENCY RESPONSE"})

@admin_required
def ambulance_edit(request, pk):
    ambulance = get_object_or_404(Ambulance, pk=pk)
    form = AmbulanceForm(request.POST or None, instance=ambulance)
    if form.is_valid():
        form.save()
        messages.success(request, f"{ambulance.vehicle_number} updated.")
        return redirect("ambulances")
    return render(request, "core/form.html", {"form": form, "heading": f"Edit {ambulance.vehicle_number}", "eyebrow": "EMERGENCY RESPONSE"})


@admin_required
def ambulance_delete(request, pk):
    ambulance = get_object_or_404(Ambulance, pk=pk)
    if request.method == "POST":
        ambulance.delete()
        messages.success(request, f"{ambulance.vehicle_number} deleted.")
    return redirect("ambulances")


@admin_required
def reports(request):
    return render(request, "core/reports.html", {
        "severity_data": [(label, Patient.objects.filter(severity=label).count()) for label in ["Critical", "Serious", "Stable", "Not triaged"]],
        "status_data": [(label, Patient.objects.filter(status=label).count()) for label in ["Waiting", "In Treatment", "Admitted", "Discharged"]],
        "beds": Bed.objects.count(), "occupied": Bed.objects.filter(status="Occupied").count(),
        "patients": Patient.objects.count(),
    })


def home(request):
    role = role_of(request.user)
    return redirect(HOME[role] if role else "login")


@admin_required
def doctor_create(request):
    """Only an admin can create doctor accounts."""
    form = DoctorCreateForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, "Doctor account created. They can sign in at /doctor/.")
        return redirect("staff")
    return render(request, "core/form.html", {"form": form, "heading": "Register doctor", "eyebrow": "DOCTOR ACCOUNT"})


# ---------------- Doctor portal ----------------
def _doctor_context(doctor):
    mine = (Patient.objects.filter(Q(assigned_doctor=doctor) | Q(referrals__assigned_doctor=doctor)).distinct()
            .exclude(status="Discharged").select_related("bed"))
    cases = sorted(mine, key=lambda p: (p.priority, p.arrival_time))
    for p in cases:
        p.consulting = p.assigned_doctor_id != doctor.pk   # referred to me by another doctor
    return {
        "doctor": doctor, "cases": cases,
        "active": len(cases),
        "critical": sum(1 for p in cases if p.severity == "Critical"),
        "in_treatment": sum(1 for p in cases if p.status == "In Treatment"),
        "waiting_all": Patient.objects.filter(status="Waiting").count(),
        "status_choices": StaffProfile.STATUS_CHOICES,
    }


@doctor_required
def doctor_dashboard(request):
    doctor = request.user.staffprofile
    if request.method == "POST" and request.POST.get("status") in dict(StaffProfile.STATUS_CHOICES):
        doctor.status = request.POST["status"]
        doctor.save()
        messages.success(request, f"Your availability is now {doctor.status}.")
        return redirect("doctor_dashboard")
    return render(request, "core/doctor_dashboard.html", _doctor_context(doctor))


# ---------------- Staff portal (nurse / triage / receptionist) ----------------
@admin_required
def staff_account_create(request):
    """Only an admin can create staff logins."""
    form = StaffAccountForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, "Staff account created. They can sign in at /staff/.")
        return redirect("staff")
    return render(request, "core/form.html", {"form": form, "heading": "Register staff login", "eyebrow": "STAFF ACCOUNT"})


def _staff_context(member):
    active = Patient.objects.exclude(status="Discharged")
    queue = sorted(active, key=lambda p: (p.priority, p.arrival_time))[:10]
    return {
        "member": member,
        "waiting": active.filter(status="Waiting").count(),
        "critical": active.filter(severity="Critical").count(),
        "free_beds": Bed.objects.filter(status="Available").count(),
        "doctors_free": StaffProfile.objects.filter(role="Doctor", status="Available").count(),
        "queue": queue,
        "show_queue": True,
        "can_register": staff_patient_form(member.role, True) is not None,
        "can_edit": staff_patient_form(member.role, False) is not None,
    }


@staff_required
def staff_dashboard(request):
    return render(request, "core/staff_dashboard.html", _staff_context(request.user.staffprofile))


@admin_required
def team_profile(request, pk):
    """Admin: a doctor / staff member's profile. Update details, availability, shift, leave and skills."""
    form = StaffProfileForm(request.POST or None, instance=get_object_or_404(StaffProfile, pk=pk))
    if form.is_valid():
        form.save()
        messages.success(request, "Profile updated.")
        return redirect("team_profile", pk)
    person = get_object_or_404(StaffProfile.objects.select_related("user"), pk=pk)  # untouched copy for the header
    return render(request, "core/team_profile.html", {"p": person, "form": form, "n_patients": person.patients.count()})


@admin_required
def team_delete(request, pk):
    """Admin: delete a doctor / staff member and their login. Their patients become unassigned."""
    person = get_object_or_404(StaffProfile, pk=pk)
    if request.method == "POST":
        name, user = person.full_name, person.user
        person.delete()
        if user and not (user.is_staff or user.is_superuser):   # never delete an admin account
            user.delete()
        messages.success(request, f"{name} was deleted.")
    return redirect("staff")


@admin_required
def team_preview(request, pk):
    """Admin: see exactly what a doctor / staff member sees after they log in (read-only)."""
    person = get_object_or_404(StaffProfile, pk=pk)
    if person.role == "Doctor":
        ctx, template = _doctor_context(person), "core/doctor_dashboard.html"
    elif person.role == "Pharmacist":
        ctx, template = _pharmacist_context(person), "core/pharmacist_dashboard.html"
    elif person.role == "Lab Technician":
        ctx, template = _lab_context(person), "core/lab_dashboard.html"
    else:
        ctx, template = _staff_context(person), "core/staff_dashboard.html"
    ctx.update({"preview": True, "can_register": False, "can_edit": False,
                "dept": Department.objects.filter(name=person.department).first()})
    return render(request, template, ctx)


def _limit_doctors_to_department(form, member):
    """A department reception desk can only assign doctors from its own department."""
    if "assigned_doctor" in form.fields and member.department and member.counter == DEPT_RECEPTION:
        form.fields["assigned_doctor"].queryset = form.fields["assigned_doctor"].queryset.filter(department=member.department)


@staff_required
def staff_patient_create(request):
    form_class = staff_patient_form(request.user.staffprofile.role, True)
    if form_class is None:
        messages.error(request, "Your role cannot register patients.")
        return redirect("staff_dashboard")
    member = request.user.staffprofile
    initial = {"department": member.department} if member.counter == DEPT_RECEPTION else {}
    form = form_class(request.POST or None, initial=initial)
    _limit_doctors_to_department(form, member)
    if form.is_valid():
        form.save()
        messages.success(request, "Emergency patient registered.")
        return redirect("staff_dashboard")
    return render(request, "core/form.html", {"form": form, "heading": "Register emergency patient", "eyebrow": "PATIENT INTAKE"})


@staff_required
def staff_patient_edit(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    form_class = staff_patient_form(request.user.staffprofile.role, False)
    if form_class is None:
        messages.error(request, "Your role cannot update patient cases.")
        return redirect("staff_dashboard")
    form = form_class(request.POST or None, instance=patient)
    _limit_doctors_to_department(form, request.user.staffprofile)
    if form.is_valid():
        obj = form.save()
        if obj.bed:
            obj.bed.status = "Occupied"
            obj.bed.save()
        messages.success(request, "Patient case updated.")
        return redirect("staff_dashboard")
    return render(request, "core/form.html", {"form": form, "heading": "Update patient case", "eyebrow": "CASE MANAGEMENT"})


def logout_view(request):
    """Sign out, then return to the login page of the portal the user came from."""
    from django.contrib.auth import logout
    target = {"admin": "login", "doctor": "doctor_login", "staff": "staff_login",
              "pharmacist": "pharmacist_login", "lab": "lab_login",
              "department": "department_login"}.get(role_of(request.user), "login")
    if request.method == "POST":
        logout(request)
    return redirect(target)


# ---------------- Admin: patient directory ----------------
def _free_bed(bed):
    if bed and bed.status == "Occupied" and not bed.patients.exclude(status="Discharged").exists():
        bed.status = "Available"
        bed.save()


def _sync_beds(patient, old_bed):
    """Keep bed status in step with the case: new bed -> Occupied, old/discharged bed -> Available."""
    if patient.bed and patient.status != "Discharged":
        patient.bed.status = "Occupied"
        patient.bed.save()
    if old_bed and (old_bed != patient.bed or patient.status == "Discharged"):
        _free_bed(old_bed)
    if patient.bed and patient.status == "Discharged":
        _free_bed(patient.bed)


SEVERITY_OPTIONS = [("", "All severities"), ("Critical", "Critical"), ("Serious", "Serious"), ("Stable", "Stable"), ("Not triaged", "Not triaged")]
STATUS_OPTIONS = [("", "All statuses"), ("Waiting", "Waiting"), ("In Treatment", "In Treatment"), ("Admitted", "Admitted"), ("Discharged", "Discharged")]


def _can_see(role):
    """Which clinical sections a role may see on a patient's page."""
    return {
        "meds": role in ("admin", "doctor", "pharmacist"),   # medicine list: doctor prescribes, pharmacist dispenses
        "tests": role in ("admin", "doctor", "lab"),          # lab tests: doctor requests, lab records results
    }


def _visible_patients(request):
    """Doctors see only the patients assigned to them. Admin, pharmacist and lab see everyone."""
    role = role_of(request.user)
    if role == "doctor":
        me = request.user.staffprofile
        return Patient.objects.filter(Q(assigned_doctor=me) | Q(referrals__assigned_doctor=me)).distinct()
    if role == "department":
        return _dept_patients(request.user.department_account)
    return Patient.objects.all()


@clinical_required
def patient_list(request):
    role = role_of(request.user)
    see = _can_see(role)
    q = request.GET.get("q", "").strip()
    severity = request.GET.get("severity", "")
    status = request.GET.get("status", "")
    severity = severity if severity in dict(SEVERITY_OPTIONS) else ""
    status = status if status in dict(STATUS_OPTIONS) else ""
    queue_options = {"pharmacist": [("", "All patients"), ("new", "● New prescriptions")],
                     "lab": [("", "All patients"), ("new", "● New checkups")]}.get(role, [])
    queue = "new" if (queue_options and request.GET.get("queue") == "new") else ""
    qs = _visible_patients(request).select_related("assigned_doctor", "bed").prefetch_related("medicines", "tests", "progress")
    if severity:
        qs = qs.filter(severity=severity)
    if status:
        qs = qs.filter(status=status)
    if queue and role == "pharmacist":
        qs = qs.filter(medicines__status="Prescribed").distinct()
    if queue and role == "lab":
        qs = qs.filter(tests__status="Requested").distinct()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(complaint__icontains=q) | Q(contact__icontains=q)
                       | Q(severity__icontains=q) | Q(status__icontains=q) | Q(department__icontains=q)
                       | Q(assigned_doctor__full_name__icontains=q) | Q(bed__bed_number__icontains=q))
    patients = sorted(qs, key=lambda p: (p.status == "Discharged", p.priority, p.arrival_time))
    for p in patients:
        p.med_names = [m.name for m in p.medicines.all() if m.status != "Stopped"] if see["meds"] else []
        p.test_names = [t.name for t in p.tests.all()] if see["tests"] else []
        p.latest = next(iter(p.progress.all()), None)
        p.new_meds = sum(1 for m in p.medicines.all() if m.status == "Prescribed") if role == "pharmacist" else 0
        p.new_tests = sum(1 for t in p.tests.all() if t.status == "Requested") if role == "lab" else 0
    return render(request, "core/patients.html", {
        "patients": patients, "q": q, "severity": severity, "status": status,
        "severities": SEVERITY_OPTIONS, "statuses": STATUS_OPTIONS, "queue_options": queue_options, "queue": queue,
        "view": _view_mode(request), "total": _visible_patients(request).count(),
        "is_admin": role == "admin", "is_doctor": role == "doctor",
        "dept_name": request.user.department_account.name if role == "department" else "",
        "show_meds": see["meds"], "show_tests": see["tests"],
    })


@clinical_required
def patient_detail(request, pk):
    role = role_of(request.user)
    see = _can_see(role)
    patient = get_object_or_404(_visible_patients(request).select_related("assigned_doctor", "bed"), pk=pk)
    return render(request, "core/patient_detail.html", {
        "p": patient, "role": role,
        "is_admin": role == "admin", "is_doctor": role == "doctor", "is_pharmacist": role == "pharmacist", "is_lab": role == "lab",
        "show_meds": see["meds"], "show_tests": see["tests"],
        "medicines": patient.medicines.select_related("prescribed_by", "dispensed_by") if see["meds"] else [],
        "tests": patient.tests.select_related("requested_by", "done_by") if see["tests"] else [],
        "progress": patient.progress.select_related("recorded_by"),
        "show_referrals": role in ("admin", "doctor", "department"),
        "referrals": _referrals_for(request, patient, role),
        "n_new_meds": patient.medicines.filter(status="Prescribed").count() if role == "pharmacist" else 0,
        "n_new_tests": patient.tests.filter(status="Requested").count() if role == "lab" else 0,
        "me": request.user.staffprofile if role == "doctor" else None,
    })


def _referrals_for(request, patient, role):
    """The referrals shown on a patient's page. Each carries the doctors the receiving department can assign."""
    refs = patient.referrals.select_related("from_doctor", "assigned_doctor")
    if role == "department":
        refs = refs.filter(to_department=request.user.department_account.name)
    refs = list(refs)
    for r in refs:
        r.can_assign = r.status == "Pending" and (role == "admin" or role == "department")
        r.choices = (StaffProfile.objects.filter(role="Doctor", department=r.to_department).order_by("full_name")
                     if r.can_assign else [])
    return refs


@admin_required
def patient_create(request):
    form = PatientForm(request.POST or None)
    if form.is_valid():
        patient = form.save()
        _sync_beds(patient, None)
        messages.success(request, "Patient registered.")
        return redirect("patient_detail", patient.pk)
    return render(request, "core/form.html", {"form": form, "heading": "Register patient", "eyebrow": "PATIENT DIRECTORY"})


@admin_required
def patient_edit(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    old_bed = patient.bed
    form = PatientForm(request.POST or None, instance=patient)
    if form.is_valid():
        patient = form.save()
        _sync_beds(patient, old_bed)
        messages.success(request, "Patient details updated.")
        return redirect("patient_detail", patient.pk)
    return render(request, "core/form.html", {"form": form, "heading": f"Edit {patient.name}", "eyebrow": "PATIENT DIRECTORY"})


def _record_form(request, pk, form_class, heading, eyebrow, save, extra=None):
    """Shared handler: show a small form for a patient and call save(form, patient) on success."""
    patient = get_object_or_404(_visible_patients(request), pk=pk)   # a doctor can only act on their own patients
    form = form_class(request.POST or None)
    if form.is_valid():
        save(form, patient)
        return redirect("patient_detail", patient.pk)
    return render(request, "core/form.html", {"form": form, "heading": f"{heading} · {patient.name}", "eyebrow": eyebrow, **(extra or {})})


@doctor_required
def patient_medicine_new(request, pk):
    """Only the patient's own doctor can add (prescribe) a medicine. The pharmacy and admin see it."""
    def save(form, patient):
        m = form.save(commit=False)
        m.patient, m.prescribed_by = patient, request.user.staffprofile
        m.save()
        messages.success(request, f"{m.name} added. The pharmacy can now see it.")
    return _record_form(request, pk, MedicineForm, "Add medicine", "PRESCRIPTION", save,
                        extra={"datalist": list(MedicineStock.objects.values_list("name", flat=True))})


@doctor_required
def patient_medicine_stop(request, pk):
    m = get_object_or_404(Medicine, pk=pk, patient__in=_visible_patients(request))
    if request.method == "POST" and m.status != "Stopped":
        m.status = "Stopped"
        m.save()
        messages.success(request, f"{m.name} stopped.")
    return redirect("patient_detail", m.patient_id)


@pharmacist_required
def patient_medicine_dispense(request, pk):
    m = get_object_or_404(Medicine, pk=pk)
    if request.method == "POST" and m.status == "Prescribed":
        m.status, m.dispensed_by, m.dispensed_at = "Dispensed", request.user.staffprofile, timezone.now()
        m.save()
        messages.success(request, f"{m.name} dispensed for {m.patient.name}.")
    if request.POST.get("next") == "dashboard":
        return redirect("pharmacist_dashboard")
    return redirect("patient_detail", m.patient_id)


@doctor_required
def patient_test_request(request, pk):
    """Doctor adds checkups (lab tests) from the lab's catalogue. They appear in the lab's list as NEW."""
    patient = get_object_or_404(_visible_patients(request), pk=pk)
    form = CheckupForm(request.POST or None)
    if form.is_valid():
        d, me, made = form.cleaned_data, request.user.staffprofile, 0
        for t in d["tests"]:
            LabTest.objects.create(patient=patient, name=t.name, test_type=t, urgent=d["urgent"], notes=d["notes"], requested_by=me)
            made += 1
        if (d["other"] or "").strip():
            LabTest.objects.create(patient=patient, name=d["other"].strip(), urgent=d["urgent"], notes=d["notes"], requested_by=me)
            made += 1
        messages.success(request, f"{made} checkup{'s' if made != 1 else ''} added. The lab can now see {'them' if made != 1 else 'it'}.")
        return redirect("patient_detail", patient.pk)
    groups = []
    for cat, _label in LabTestType.CATEGORIES:
        items = list(form.fields["tests"].queryset.filter(category=cat))
        if items:
            groups.append((cat, items))
    selected = {int(x) for x in request.POST.getlist("tests") if x.isdigit()}
    return render(request, "core/checkup_form.html", {"form": form, "patient": patient, "groups": groups, "selected": selected})


@doctor_required
def patient_refer(request, pk):
    """Doctor refers the patient to another department. That department then assigns one of its doctors."""
    def save(form, patient):
        Referral.objects.create(patient=patient, from_doctor=request.user.staffprofile,
                                to_department=form.cleaned_data["to_department"], reason=form.cleaned_data["reason"])
        messages.success(request, f"{patient.name} referred to {form.cleaned_data['to_department']}.")
    return _record_form(request, pk, ReferralForm, "Refer to another department", "REFERRAL", save)


@doctor_required
def referral_complete(request, pk):
    ref = get_object_or_404(Referral, pk=pk, assigned_doctor=request.user.staffprofile)
    if request.method == "POST" and ref.status == "Assigned":
        ref.status, ref.completed_at = "Completed", timezone.now()
        ref.save()
        messages.success(request, "Referral marked completed.")
    return redirect("patient_detail", ref.patient_id)


@referral_assign_required
def referral_assign(request, pk):
    """The receiving department (or admin) picks the doctor who will see the referred patient."""
    ref = get_object_or_404(Referral, pk=pk)
    role = role_of(request.user)
    if role == "department" and request.user.department_account.name != ref.to_department:
        return redirect("department_home")
    if request.method == "POST" and ref.status == "Pending":
        doc = StaffProfile.objects.filter(pk=request.POST.get("doctor") or 0, role="Doctor", department=ref.to_department).first()
        if doc is None:
            messages.error(request, "Choose a doctor from this department.")
        else:
            ref.assigned_doctor, ref.status, ref.assigned_at = doc, "Assigned", timezone.now()
            ref.save()
            messages.success(request, f"{ref.patient.name} assigned to {doc.full_name}.")
    if request.POST.get("next") == "patient" or role == "admin":
        return redirect("patient_detail", ref.patient_id)
    return redirect("department_home")


@lab_required
def patient_test_add(request, pk):
    def save(form, patient):
        t = form.save(commit=False)
        t.patient, t.status, t.done_by, t.completed_at = patient, "Completed", request.user.staffprofile, timezone.now()
        t.save()
        messages.success(request, f"{t.name} result saved.")
    return _record_form(request, pk, TestAddForm, "Add test result", "LAB TEST", save)


@lab_required
def patient_test_result(request, pk):
    test = get_object_or_404(LabTest, pk=pk)
    form = TestResultForm(request.POST or None, instance=test)
    if form.is_valid():
        t = form.save(commit=False)
        t.status, t.done_by, t.completed_at = "Completed", request.user.staffprofile, timezone.now()
        t.save()
        messages.success(request, f"{t.name} result saved.")
        return redirect("lab_dashboard" if request.GET.get("next") == "dashboard" else "patient_detail", *([] if request.GET.get("next") == "dashboard" else [t.patient_id]))
    return render(request, "core/form.html", {"form": form, "heading": f"Result: {test.name} · {test.patient.name}", "eyebrow": "LAB TEST"})


@doctor_required
def patient_progress_new(request, pk):
    def save(form, patient):
        n = form.save(commit=False)
        n.patient, n.recorded_by = patient, request.user.staffprofile
        n.save()
        messages.success(request, "Progress update added.")
    return _record_form(request, pk, ProgressForm, "Progress update", "HEALTH PROGRESS", save)


# ---------------- Pharmacist portal ----------------
def _pharmacist_context(member):
    pending = list(Medicine.objects.filter(status="Prescribed").select_related("patient", "prescribed_by"))
    pending.sort(key=lambda m: (m.patient.priority, m.created_at))
    stock = {x.name.lower(): x for x in MedicineStock.objects.all()}
    for m in pending:
        m.stock = stock.get(m.name.lower())
    today = timezone.localdate()
    return {
        "member": member, "pending": pending, "n_pending": len(pending),
        "n_low_stock": sum(1 for x in stock.values() if x.level != "In stock"),
        "n_dispensed_today": Medicine.objects.filter(status="Dispensed", dispensed_at__date=today).count(),
        "n_patients": Patient.objects.filter(medicines__status__in=["Prescribed", "Dispensed"]).exclude(status="Discharged").distinct().count(),
        "recent": Medicine.objects.filter(status="Dispensed").select_related("patient", "dispensed_by").order_by("-dispensed_at")[:6],
    }


@pharmacist_required
def pharmacist_dashboard(request):
    return render(request, "core/pharmacist_dashboard.html", _pharmacist_context(request.user.staffprofile))


# ---------------- Lab portal ----------------
def _lab_context(member):
    pending = list(LabTest.objects.filter(status="Requested").select_related("patient", "requested_by"))
    pending.sort(key=lambda t: (not t.urgent, t.patient.priority, t.created_at))
    today = timezone.localdate()
    return {
        "member": member, "pending": pending, "n_pending": len(pending),
        "n_equipment_attention": Equipment.objects.exclude(status__in=["Available", "In use"]).count(),
        "n_done_today": LabTest.objects.filter(status="Completed", completed_at__date=today).count(),
        "n_patients": Patient.objects.filter(tests__isnull=False).distinct().count(),
        "recent": LabTest.objects.filter(status="Completed").select_related("patient", "done_by").order_by("-completed_at")[:6],
    }


@lab_required
def lab_dashboard(request):
    return render(request, "core/lab_dashboard.html", _lab_context(request.user.staffprofile))


# ---------------- Pharmacist: medicine stock ----------------
LEVEL_OPTIONS = [("", "All medicines"), ("low", "Low stock"), ("out", "Out of stock")]


@pharmacist_required
def pharmacy_medicines(request):
    q = request.GET.get("q", "").strip()
    level = request.GET.get("level", "")
    level = level if level in dict(LEVEL_OPTIONS) else ""
    items = MedicineStock.objects.all()
    if q:
        items = items.filter(Q(name__icontains=q) | Q(strength__icontains=q) | Q(form__icontains=q))
    if level == "out":
        items = items.filter(quantity=0)
    elif level == "low":
        items = items.filter(quantity__gt=0, quantity__lte=F("reorder_level"))
    allm = MedicineStock.objects.all()
    return render(request, "core/pharmacy_medicines.html", {
        "items": items, "q": q, "level": level, "levels": LEVEL_OPTIONS,
        "n_total": allm.count(), "n_out": allm.filter(quantity=0).count(),
        "n_low": allm.filter(quantity__gt=0, quantity__lte=F("reorder_level")).count(),
        "n_new_week": allm.filter(updated_at__gte=timezone.now() - timezone.timedelta(days=7)).count(),
    })


@pharmacist_required
def pharmacy_medicine_new(request):
    form = MedicineStockForm(request.POST or None)
    if form.is_valid():
        m = form.save()
        messages.success(request, f"{m.name} added to the pharmacy list.")
        return redirect("pharmacy_medicines")
    return render(request, "core/form.html", {"form": form, "heading": "Add medicine to stock", "eyebrow": "PHARMACY"})


@pharmacist_required
def pharmacy_medicine_edit(request, pk):
    m = get_object_or_404(MedicineStock, pk=pk)
    form = MedicineStockForm(request.POST or None, instance=m)
    if form.is_valid():
        form.save()
        messages.success(request, f"{m.name} updated.")
        return redirect("pharmacy_medicines")
    return render(request, "core/form.html", {"form": form, "heading": f"Edit {m.name}", "eyebrow": "PHARMACY"})


@pharmacist_required
def pharmacy_medicine_receive(request, pk):
    """New stock arrived: add to the quantity."""
    m = get_object_or_404(MedicineStock, pk=pk)
    if request.method == "POST":
        try:
            n = int(request.POST.get("qty", "0"))
        except ValueError:
            n = 0
        if 0 < n <= 100000:
            m.quantity += n
            m.save()
            messages.success(request, f"{n} {m.unit} of {m.name} added. Now {m.quantity} in stock.")
        else:
            messages.error(request, "Enter how many arrived (a whole number above 0).")
    return redirect("pharmacy_medicines")


@pharmacist_required
def pharmacy_medicine_delete(request, pk):
    m = get_object_or_404(MedicineStock, pk=pk)
    if request.method == "POST":
        m.delete()
        messages.success(request, f"{m.name} removed from the list.")
    return redirect("pharmacy_medicines")


# ---------------- Lab: equipment and the test catalogue ----------------
@lab_required
def lab_equipment(request):
    items = Equipment.objects.all()
    q = request.GET.get("q", "").strip()
    if q:
        items = items.filter(Q(name__icontains=q) | Q(category__icontains=q) | Q(location__icontains=q))
    allq = Equipment.objects.all()
    return render(request, "core/lab_equipment.html", {
        "items": items, "q": q, "n_items": allq.count(),
        "n_ok": allq.filter(status="Available").count(),
        "n_attention": allq.exclude(status__in=["Available", "In use"]).count(),
        "my_requests": SupplyRequest.objects.filter(unit="Lab")[:6],
    })


@lab_required
def lab_equipment_new(request):
    form = EquipmentForm(request.POST or None)
    if form.is_valid():
        e = form.save()
        messages.success(request, f"{e.name} added.")
        return redirect("lab_equipment")
    return render(request, "core/form.html", {"form": form, "heading": "Add equipment", "eyebrow": "LAB EQUIPMENT"})


@lab_required
def lab_equipment_edit(request, pk):
    e = get_object_or_404(Equipment, pk=pk)
    form = EquipmentForm(request.POST or None, instance=e)
    if form.is_valid():
        form.save()
        messages.success(request, f"{e.name} updated.")
        return redirect("lab_equipment")
    return render(request, "core/form.html", {"form": form, "heading": f"Edit {e.name}", "eyebrow": "LAB EQUIPMENT"})


@lab_required
def lab_equipment_delete(request, pk):
    e = get_object_or_404(Equipment, pk=pk)
    if request.method == "POST":
        e.delete()
        messages.success(request, f"{e.name} removed.")
    return redirect("lab_equipment")


@lab_required
def lab_tests(request):
    q = request.GET.get("q", "").strip()
    tests = LabTestType.objects.all()
    if q:
        tests = tests.filter(Q(name__icontains=q) | Q(category__icontains=q) | Q(notes__icontains=q))
    groups = [(cat, list(tests.filter(category=cat))) for cat, _ in LabTestType.CATEGORIES]
    groups = [(c, items) for c, items in groups if items]
    return render(request, "core/lab_tests.html", {
        "groups": groups, "q": q, "n_total": LabTestType.objects.count(),
        "n_available": LabTestType.objects.filter(available=True).count(),
    })


@lab_required
def lab_test_new(request):
    form = LabTestTypeForm(request.POST or None, initial={"available": True})
    if form.is_valid():
        t = form.save()
        messages.success(request, f"{t.name} added to the test list.")
        return redirect("lab_tests")
    return render(request, "core/form.html", {"form": form, "heading": "Add a test", "eyebrow": "LAB TESTS"})


@lab_required
def lab_test_edit(request, pk):
    t = get_object_or_404(LabTestType, pk=pk)
    form = LabTestTypeForm(request.POST or None, instance=t)
    if form.is_valid():
        form.save()
        messages.success(request, f"{t.name} updated.")
        return redirect("lab_tests")
    return render(request, "core/form.html", {"form": form, "heading": f"Edit {t.name}", "eyebrow": "LAB TESTS"})


@lab_required
def lab_test_toggle(request, pk):
    t = get_object_or_404(LabTestType, pk=pk)
    if request.method == "POST":
        t.available = not t.available
        t.save()
        messages.success(request, f"{t.name} is now {'available' if t.available else 'unavailable'}.")
    return redirect("lab_tests")


@lab_required
def lab_test_delete(request, pk):
    t = get_object_or_404(LabTestType, pk=pk)
    if request.method == "POST":
        t.delete()
        messages.success(request, f"{t.name} removed from the list.")
    return redirect("lab_tests")


# ---------------- Supply requests (pharmacy, lab, departments, food...) ----------------
REQUEST_KINDS = {"pharmacist": ["Medicine"], "lab": ["Equipment"], "department": ["Equipment", "Supplies"]}


def _unit_name(request):
    role = role_of(request.user)
    if role == "pharmacist":
        return "Pharmacy"
    if role == "lab":
        return "Lab"
    return request.user.department_account.name


@request_roles_required
def supply_requests(request):
    role = role_of(request.user)
    status = request.GET.get("status", "")
    status = status if status in dict(SupplyRequest.STATUS) else ""
    qs = SupplyRequest.objects.all()
    if role != "admin":
        qs = qs.filter(unit=_unit_name(request))
    if status:
        qs = qs.filter(status=status)
    return render(request, "core/requests.html", {
        "reqs": qs, "status": status, "statuses": [("", "All requests")] + SupplyRequest.STATUS,
        "is_admin": role == "admin", "role": role,
        "unit": "" if role == "admin" else _unit_name(request),
        "kind_word": {"pharmacist": "medicine", "lab": "equipment"}.get(role, "supplies"),
        "n_open": SupplyRequest.objects.filter(status="Requested").count() if role == "admin" else 0,
    })


@request_roles_required
def supply_request_new(request):
    role = role_of(request.user)
    if role == "admin":
        return redirect("supply_requests")
    form = SupplyRequestForm(REQUEST_KINDS[role], request.POST or None)
    if form.is_valid():
        r = form.save(commit=False)
        r.unit, r.requested_by = _unit_name(request), request.user
        r.save()
        messages.success(request, f"Request sent to the admin: {r.quantity} × {r.item}.")
        return redirect("supply_requests")
    word = {"pharmacist": "Request medicine", "lab": "Request equipment"}.get(role, "Request supplies or equipment")
    return render(request, "core/form.html", {"form": form, "heading": word, "eyebrow": f"{_unit_name(request).upper()} REQUEST"})


def _apply_delivery(r):
    """A delivered medicine / equipment request is added to the unit's list."""
    if r.kind == "Medicine":
        m = MedicineStock.objects.filter(name__iexact=r.item).first()
        if m:
            m.quantity += r.quantity
            m.save()
        else:
            MedicineStock.objects.create(name=r.item, quantity=r.quantity)
    elif r.kind == "Equipment" and r.unit == "Lab":
        e = Equipment.objects.filter(name__iexact=r.item).first()
        if e:
            e.quantity += r.quantity
            e.save()
        else:
            Equipment.objects.create(name=r.item, quantity=r.quantity)


@admin_required
def supply_request_status(request, pk):
    r = get_object_or_404(SupplyRequest, pk=pk)
    new = request.POST.get("status")
    if request.method == "POST" and new in dict(SupplyRequest.STATUS):
        previous = r.status
        r.status = new
        note = request.POST.get("note", "").strip()
        if note:
            r.admin_note = note[:200]
        r.save()
        if new == "Delivered" and previous != "Delivered":
            _apply_delivery(r)
        messages.success(request, f"{r.item} marked {new.lower()}.")
    return redirect("supply_requests")
