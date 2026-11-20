from functools import wraps
from django.shortcuts import redirect


def role_of(user):
    """Return 'admin', 'doctor', 'pharmacist', 'lab', 'staff', 'department' or None."""
    if not user.is_authenticated:
        return None
    if user.is_staff:
        return "admin"
    sp = getattr(user, "staffprofile", None)
    if sp is None:
        return "department" if hasattr(user, "department_account") else None
    if sp.role == "Doctor":
        return "doctor"
    if sp.role == "Pharmacist":
        return "pharmacist"
    if sp.role == "Lab Technician":
        return "lab"
    return "staff"


HOME = {"admin": "dashboard", "doctor": "doctor_dashboard", "pharmacist": "pharmacist_dashboard",
        "lab": "lab_dashboard", "staff": "staff_dashboard", "department": "department_home"}
LOGIN = {"admin": "login", "doctor": "doctor_login", "pharmacist": "pharmacist_login",
         "lab": "lab_login", "staff": "staff_login", "department": "department_login"}


def _require(*roles):
    """Allow only the given roles. Others go to their own home; anonymous users go to the first role's login."""
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            current = role_of(request.user)
            if current in roles:
                return view(request, *args, **kwargs)
            if current:
                return redirect(HOME[current])
            return redirect(LOGIN[roles[0]])
        return wrapper
    return decorator


admin_required = _require("admin")
doctor_required = _require("doctor")
pharmacist_required = _require("pharmacist")
lab_required = _require("lab")
staff_required = _require("staff")
department_required = _require("department")
# anyone who can raise supply requests (admin reviews them)
request_roles_required = _require("admin", "pharmacist", "lab", "department")
# who may assign a referral to a doctor: the receiving department, or the admin
referral_assign_required = _require("admin", "department")
# patient records: admin, the clinical portals and read-only department logins
clinical_required = _require("admin", "doctor", "pharmacist", "lab", "department")
