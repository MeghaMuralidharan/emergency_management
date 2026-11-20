from django import forms
from .models import (Ward, Department, Medicine, LabTest, ProgressNote, LabTestType, MedicineStock, Equipment,
                     SupplyRequest, Referral, Patient, StaffProfile, Bed, Ambulance)


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs["rows"] = 3

GENDER_CHOICES = [("", "Select gender"), ("Female", "Female"), ("Male", "Male"), ("Other", "Other")]


class PatientForm(StyledModelForm):
    gender = forms.ChoiceField(choices=GENDER_CHOICES, required=False)
    department = forms.ChoiceField(choices=[], required=False)

    class Meta:
        model = Patient
        fields = ["name", "age", "gender", "contact", "complaint", "department", "severity", "status", "assigned_doctor", "bed", "notes"]
        widgets = {"complaint": forms.Textarea, "notes": forms.Textarea}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # declared fields are always added by Django: keep only the ones this variant of the form is meant to show
        for name in list(self.fields):
            if name not in self._meta.fields:
                del self.fields[name]
        if "department" in self.fields:
            names = list(Department.objects.filter(is_service=False).values_list("name", flat=True))
            cur = self.instance.department if self.instance and self.instance.pk else ""
            if cur and cur not in names:
                names.append(cur)
            self.fields["department"].choices = [("", "— none —")] + [(n, n) for n in names]
        # keep an old free-text value selectable when editing an existing patient
        current = self.instance.gender if self.instance and self.instance.pk else ""
        if "gender" in self.fields and current and current not in dict(GENDER_CHOICES):
            self.fields["gender"].choices = GENDER_CHOICES + [(current, current)]
        if "assigned_doctor" in self.fields:
            docs = StaffProfile.objects.filter(role="Doctor", status="Available", on_leave=False)
            if self.instance and self.instance.pk and self.instance.assigned_doctor_id:
                docs = docs | StaffProfile.objects.filter(pk=self.instance.assigned_doctor_id)
            self.fields["assigned_doctor"].queryset = docs
        if "bed" in self.fields:
            free = Bed.objects.filter(status="Available")
            if self.instance and self.instance.pk and self.instance.bed_id:
                free = free | Bed.objects.filter(pk=self.instance.bed_id)
            self.fields["bed"].queryset = free


# What each staff role may fill in on a patient case
_BASIC = ["name", "age", "gender", "contact", "complaint", "department"]
STAFF_PATIENT_FIELDS = {
    # (role, creating) -> fields
    ("Receptionist", True): _BASIC + ["severity", "assigned_doctor"],
    ("Receptionist", False): _BASIC + ["severity", "status", "assigned_doctor", "bed", "notes"],
    ("Front Desk", True): _BASIC + ["severity"],
    ("Front Desk", False): _BASIC + ["severity", "status", "notes"],
    ("Booking Clerk", True): _BASIC,
    ("Triage Staff", True): _BASIC + ["severity"],
    ("Triage Staff", False): _BASIC + ["severity", "status", "assigned_doctor", "bed", "notes"],
    ("Nurse", False): ["status", "bed", "notes"],
}


def staff_patient_form(role, creating):
    """Return a PatientForm class limited to the fields this role may edit, or None."""
    fields = STAFF_PATIENT_FIELDS.get((role, creating))
    if fields is None:
        return None
    return forms.modelform_factory(Patient, form=PatientForm, fields=fields)


class WardForm(StyledModelForm):
    """Create or edit a ward / ICU / room and say how many beds it has."""
    capacity = forms.IntegerField(min_value=1, max_value=200, label="Number of beds",
                                  help_text="Suggested: ICU 1 · Shared ICU 4 · Ward 10 · Room 2 · Personal room 1 · VIP room 1")
    field_order = ["name", "category", "capacity", "floor"]

    class Meta:
        model = Ward
        fields = ["name", "category", "floor"]
        labels = {"name": "Name", "category": "Type", "floor": "Floor / location (optional)"}
        widgets = {"name": forms.TextInput(attrs={"placeholder": "e.g. ICU 1, Ward A, Room 204, VIP 2"}),
                   "floor": forms.TextInput(attrs={"placeholder": "e.g. 2nd floor, East wing"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].choices = [("", "Select type")] + Ward.CATEGORIES
        if self.instance.pk:
            self.fields["capacity"].initial = self.instance.total

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        qs = Ward.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("A ward or room with this name already exists.")
        return name

    def clean(self):
        data = super().clean()
        cap = data.get("capacity")
        if self.instance.pk and cap is not None:
            occupied = self.instance.beds.filter(status="Occupied").count()
            if cap < occupied:
                self.add_error("capacity", f"{occupied} bed{'s are' if occupied != 1 else ' is'} occupied, so it cannot have fewer than {occupied} bed{'s' if occupied != 1 else ''}.")
        return data

    def save(self, commit=True):
        renamed = self.instance.pk and "name" in self.changed_data
        ward = super().save()
        cap, total = self.cleaned_data["capacity"], ward.total
        if cap > total:
            ward.add_beds(cap - total)
        elif cap < total:                      # remove free beds, highest number first
            for bed in ward.beds.exclude(status="Occupied").order_by("-number")[: total - cap]:
                bed.delete()
        if renamed:
            ward.renumber()
        return ward


class AmbulanceForm(StyledModelForm):
    class Meta:
        model = Ambulance
        fields = ["vehicle_number", "ambulance_type", "driver_name", "contact", "location", "status"]

# ---------------- Role-based sign-in ----------------
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.forms import AuthenticationForm


DEPT_RECEPTION = "Department reception"
COUNTERS = [DEPT_RECEPTION, "Hospital reception", "Booking counter", "Pharmacy", "Lab", "Nurse station"]
STAFF_JOB_ROLES = ["Receptionist", "Front Desk", "Nurse", "Pharmacist", "Lab Technician", "Triage Staff", "Booking Clerk"]


def department_choices(include_service=False, current=None):
    """Dropdown choices built from the Hospital directory (clinical departments, optionally service units too)."""
    qs = Department.objects.all() if include_service else Department.objects.filter(is_service=False)
    names = list(qs.values_list("name", flat=True))
    if current and current not in names:
        names.append(current)
    return [("", "Select department")] + [(n, n) for n in names]


def _check_reception_unique(form, counter, dept, exclude_pk=None):
    """Each department can have only one 'Department reception' desk."""
    if counter == DEPT_RECEPTION:
        if not dept:
            if "department" not in form.errors:
                form.add_error("department", "Choose the department this reception belongs to.")
            return
        qs = StaffProfile.objects.filter(counter=DEPT_RECEPTION, department=dept)
        if exclude_pk:
            qs = qs.exclude(pk=exclude_pk)
        if qs.exists():
            form.add_error("department", f"{dept} already has a reception registered.")


class PortalLoginForm(AuthenticationForm):
    """Login form that only lets a given portal's users in."""
    portal = None  # "doctor" or "patient"

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if self.portal == "admin":
            ok = user.is_staff
        elif self.portal == "doctor":
            ok = hasattr(user, "staffprofile") and user.staffprofile.role == "Doctor"
        elif self.portal == "department":
            ok = hasattr(user, "department_account")
        elif self.portal == "pharmacist":
            ok = hasattr(user, "staffprofile") and user.staffprofile.role == "Pharmacist"
        elif self.portal == "lab":
            ok = hasattr(user, "staffprofile") and user.staffprofile.role == "Lab Technician"
        else:  # staff: front desk, reception, nurses... (doctors, pharmacists and lab have their own portals)
            ok = hasattr(user, "staffprofile") and user.staffprofile.role not in ("Doctor", "Pharmacist", "Lab Technician")
        if not ok:
            raise forms.ValidationError("This account cannot sign in here.", code="wrong_portal")


class AdminLoginForm(PortalLoginForm):
    portal = "admin"


class DoctorLoginForm(PortalLoginForm):
    portal = "doctor"


class DepartmentLoginForm(PortalLoginForm):
    portal = "department"


class PharmacistLoginForm(PortalLoginForm):
    portal = "pharmacist"


class LabLoginForm(PortalLoginForm):
    portal = "lab"


class StaffLoginForm(PortalLoginForm):
    portal = "staff"


class _AccountForm(forms.Form):
    username = forms.CharField(max_length=150)
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = "form-control"

    def clean_username(self):
        u = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=u).exists():
            raise forms.ValidationError("This username is already taken.")
        return u

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 and p2:
            if p1 != p2:
                self.add_error("password2", "Passwords do not match.")
            else:
                try:
                    validate_password(p1)
                except forms.ValidationError as e:
                    self.add_error("password1", e)
        return data

    def _make_user(self):
        d = self.cleaned_data
        first, _, last = d["full_name"].partition(" ")
        return User.objects.create_user(d["username"], password=d["password1"], first_name=first, last_name=last)


class DoctorCreateForm(_AccountForm):
    full_name = forms.CharField(max_length=120)
    department = forms.ChoiceField(choices=[])
    phone = forms.CharField(max_length=25, required=False)
    skills = forms.CharField(max_length=300, required=False, label="Specialities / skills",
                             help_text="Separate with commas, e.g. Cardiology, ECG reading")
    field_order = ["full_name", "department", "phone", "skills", "username", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].choices = department_choices()

    def save(self):
        d = self.cleaned_data
        return StaffProfile.objects.create(user=self._make_user(), full_name=d["full_name"], role="Doctor",
                                           department=d["department"], phone=d["phone"], skills=d["skills"])


class StaffAccountForm(_AccountForm):
    """Admin creates a login for a staff member: department, counter / desk and job role."""
    full_name = forms.CharField(max_length=120, label="Name")
    department = forms.ChoiceField(choices=[], label="Department")
    counter = forms.ChoiceField(choices=[("", "Select counter / desk")] + [(c, c) for c in COUNTERS], label="Counter / desk",
                                help_text="Each department can have only one Department reception.")
    role = forms.ChoiceField(choices=[("", "Select job role")] + [(r, r) for r in STAFF_JOB_ROLES], label="Job role (kind of staff)")
    phone = forms.CharField(max_length=25, required=False)
    skills = forms.CharField(max_length=300, required=False, label="Skills / specialities",
                             help_text="Separate with commas, e.g. IV cannulation, triage, dispensing")
    field_order = ["full_name", "department", "counter", "role", "phone", "skills", "username", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].choices = department_choices(include_service=True)

    def clean(self):
        data = super().clean()
        _check_reception_unique(self, data.get("counter"), data.get("department"))
        return data

    def save(self):
        d = self.cleaned_data
        return StaffProfile.objects.create(user=self._make_user(), full_name=d["full_name"], role=d["role"],
                                           counter=d["counter"], department=d["department"],
                                           phone=d["phone"], skills=d["skills"])


def _clean_passwords(form, data):
    p1, p2 = data.get("password1"), data.get("password2")
    if p1 and p2:
        if p1 != p2:
            form.add_error("password2", "Passwords do not match.")
        else:
            try:
                validate_password(p1)
            except forms.ValidationError as e:
                form.add_error("password1", e)


def _check_username_free(username):
    if User.objects.filter(username__iexact=username).exists():
        raise forms.ValidationError("This username is already taken.")
    return username


class DepartmentForm(StyledModelForm):
    """Create a department together with the login the department uses at /department/."""
    username = forms.CharField(max_length=150, label="Department login username",
                               help_text="The department signs in with this at /department/, e.g. cardiology")
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput)
    field_order = ["name", "description", "username", "password1", "password2"]

    class Meta:
        model = Department
        fields = ["name", "description"]
        labels = {"name": "Department name"}

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if Department.objects.filter(name__iexact=name).exists():
            raise forms.ValidationError("This department already exists.")
        return name

    def clean_username(self):
        return _check_username_free(self.cleaned_data["username"].strip())

    def clean(self):
        data = super().clean()
        _clean_passwords(self, data)
        return data

    def save(self, commit=True):
        dept = super().save(commit=False)
        d = self.cleaned_data
        dept.user = User.objects.create_user(d["username"], password=d["password1"], first_name=dept.name)
        dept.save()
        return dept


class DepartmentAccountForm(forms.Form):
    """Admin creates a department login, or resets the password of the existing one."""
    username = forms.CharField(max_length=150, label="Department login username")
    password1 = forms.CharField(label="New password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput)

    def __init__(self, dept, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dept = dept
        if dept.user_id:
            del self.fields["username"]
        for f in self.fields.values():
            f.widget.attrs["class"] = "form-control"

    def clean_username(self):
        return _check_username_free(self.cleaned_data["username"].strip())

    def clean(self):
        data = super().clean()
        _clean_passwords(self, data)
        return data

    def save(self):
        d, dept = self.cleaned_data, self.dept
        if dept.user_id:
            dept.user.set_password(d["password1"])
            dept.user.save()
        else:
            dept.user = User.objects.create_user(d["username"], password=d["password1"], first_name=dept.name)
            dept.save()
        return dept

class StaffProfileForm(StyledModelForm):
    """Admin updates a doctor / staff member: details, availability, shift, leave and skills."""
    class Meta:
        model = StaffProfile
        fields = ["full_name", "role", "counter", "department", "phone", "status",
                  "shift_start", "shift_end", "on_leave", "leave_note", "skills"]
        widgets = {
            "shift_start": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "shift_end": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "skills": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {"full_name": "Name", "status": "Availability status", "shift_start": "Shift starts", "shift_end": "Shift ends",
                  "on_leave": "On leave", "leave_note": "Leave note", "skills": "Skills / specialities"}
        help_texts = {"skills": "Separate with commas, e.g. ECG, IV cannulation, triage"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = self.instance
        self.is_doctor = inst.role == "Doctor"
        if self.is_doctor:
            del self.fields["role"]
            del self.fields["counter"]
        else:
            roles = list(STAFF_JOB_ROLES)
            if inst.role and inst.role not in roles:
                roles.append(inst.role)
            self.fields["role"] = forms.ChoiceField(choices=[(r, r) for r in roles], label="Job role (kind of staff)")
            self.fields["counter"] = forms.ChoiceField(choices=[("", "— none —")] + [(c, c) for c in COUNTERS], required=False, label="Counter / desk")
            self.fields["role"].initial = inst.role
            self.fields["counter"].initial = inst.counter
        self.fields["department"] = forms.ChoiceField(
            choices=department_choices(include_service=not self.is_doctor, current=inst.department), label="Department")
        self.fields["department"].initial = inst.department
        for name, f in self.fields.items():
            f.widget.attrs["class"] = "" if name == "on_leave" else "form-control"
        self.fields["leave_note"].widget.attrs["placeholder"] = "e.g. back on 25 Nov"

    def clean(self):
        data = super().clean()
        if bool(data.get("shift_start")) != bool(data.get("shift_end")):
            self.add_error("shift_end", "Set both the start and the end time, or leave both empty.")
        if not self.is_doctor:
            _check_reception_unique(self, data.get("counter"), data.get("department"), self.instance.pk)
        return data


# ---------------- clinical record forms ----------------
FREQUENCIES = ["Once daily", "Twice daily", "Three times daily", "Four times daily", "Every 6 hours", "Every 8 hours",
               "At night", "As needed (SOS)"]


class MedicineForm(StyledModelForm):
    """Doctor prescribes a medicine."""
    frequency = forms.ChoiceField(choices=[("", "Select frequency")] + [(f, f) for f in FREQUENCIES])

    class Meta:
        model = Medicine
        fields = ["name", "dosage", "frequency", "duration", "instructions"]
        labels = {"name": "Medicine", "duration": "Duration"}
        widgets = {"name": forms.TextInput(attrs={"placeholder": "e.g. Paracetamol", "list": "med-names", "autocomplete": "off"}),
                   "dosage": forms.TextInput(attrs={"placeholder": "e.g. 500 mg"}),
                   "duration": forms.TextInput(attrs={"placeholder": "e.g. 5 days"}),
                   "instructions": forms.TextInput(attrs={"placeholder": "e.g. after food"})}


class TestRequestForm(StyledModelForm):
    """Doctor asks the lab for a test."""
    class Meta:
        model = LabTest
        fields = ["name", "notes"]
        labels = {"name": "Test", "notes": "Note for the lab"}
        widgets = {"name": forms.TextInput(attrs={"placeholder": "e.g. Complete blood count"})}


class TestAddForm(StyledModelForm):
    """Lab adds a finished test with its result."""
    class Meta:
        model = LabTest
        fields = ["name", "result", "notes"]
        labels = {"name": "Test", "notes": "Lab note"}
        widgets = {"name": forms.TextInput(attrs={"placeholder": "e.g. X-ray chest"}),
                   "result": forms.Textarea(attrs={"rows": 3}), }


class TestResultForm(StyledModelForm):
    """Lab enters the result of a requested test."""
    class Meta:
        model = LabTest
        fields = ["result", "notes"]
        labels = {"notes": "Lab note"}
        widgets = {"result": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["result"].required = True


class ProgressForm(StyledModelForm):
    """Doctor records whether the patient is improving."""
    class Meta:
        model = ProgressNote
        fields = ["condition", "note"]
        labels = {"condition": "How is the patient doing?", "note": "Note"}
        widgets = {"note": forms.Textarea(attrs={"rows": 3, "placeholder": "e.g. Fever settling, breathing easier"})}


# ---------------- checkups (lab tests), referrals, pharmacy stock, lab equipment & catalogue, supply requests ----------------
class CheckupForm(forms.Form):
    """Doctor ticks the checkups the patient needs, picked from the lab's catalogue."""
    tests = forms.ModelMultipleChoiceField(queryset=LabTestType.objects.none(), required=False)
    other = forms.CharField(max_length=120, required=False, label="Another test (not in the list)")
    urgent = forms.BooleanField(required=False, label="Urgent")
    notes = forms.CharField(max_length=250, required=False, label="Note for the lab")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tests"].queryset = LabTestType.objects.filter(available=True)

    def clean(self):
        data = super().clean()
        if not data.get("tests") and not (data.get("other") or "").strip():
            raise forms.ValidationError("Choose at least one checkup.")
        return data


class ReferralForm(forms.Form):
    """Doctor sends the patient to another department."""
    to_department = forms.ChoiceField(choices=[], label="Refer to department")
    reason = forms.CharField(label="Why is this needed?", widget=forms.Textarea(
        attrs={"rows": 3, "placeholder": "e.g. Cardiac patient with urinary symptoms, needs a urology opinion"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["to_department"].choices = department_choices()
        for f in self.fields.values():
            f.widget.attrs["class"] = "form-control"


class MedicineStockForm(StyledModelForm):
    class Meta:
        model = MedicineStock
        fields = ["name", "strength", "form", "quantity", "unit", "reorder_level"]
        labels = {"name": "Medicine", "strength": "Strength", "form": "Form", "quantity": "In stock",
                  "unit": "Unit", "reorder_level": "Reorder when stock is at or below"}
        widgets = {"strength": forms.TextInput(attrs={"placeholder": "e.g. 500 mg"}),
                   "unit": forms.TextInput(attrs={"placeholder": "tablets, bottles, vials..."})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["form"].choices = [("", "Select form")] + MedicineStock.FORMS


class EquipmentForm(StyledModelForm):
    class Meta:
        model = Equipment
        fields = ["name", "category", "quantity", "status", "location"]
        labels = {"quantity": "How many"}
        widgets = {"category": forms.TextInput(attrs={"placeholder": "e.g. Analyzer, Microscope, Imaging"}),
                   "location": forms.TextInput(attrs={"placeholder": "e.g. Lab room 2"})}


class LabTestTypeForm(StyledModelForm):
    class Meta:
        model = LabTestType
        fields = ["name", "category", "notes", "available"]
        labels = {"name": "Test", "notes": "Notes (fasting, turnaround time...)", "available": "Available now"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["available"].widget.attrs["class"] = ""


class SupplyRequestForm(StyledModelForm):
    """A unit asks the admin for medicine, equipment or supplies."""
    class Meta:
        model = SupplyRequest
        fields = ["kind", "item", "quantity", "urgent", "reason"]
        labels = {"kind": "What do you need?", "item": "Item", "urgent": "Urgent", "reason": "Why is it needed?"}
        widgets = {"reason": forms.Textarea(attrs={"rows": 3}), "item": forms.TextInput(attrs={"placeholder": "e.g. Insulin 100 IU, Centrifuge, Disposable gloves"})}

    def __init__(self, kinds, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kind"].choices = [(k, k) for k in kinds]
        self.fields["quantity"].min_value = 1
        self.fields["urgent"].widget.attrs["class"] = ""
