import os
from django.conf import settings


def asset_version(request):
    """Cache-busting token that changes whenever app.css / app.js change."""
    newest = 0
    for rel in ("css/app.css", "js/app.js"):
        try:
            newest = max(newest, int(os.path.getmtime(os.path.join(settings.BASE_DIR, "static", rel))))
        except OSError:
            pass
    return {"asset_version": newest}


def notifications(request):
    """How many new items wait for this user (shown as a red badge in the sidebar)."""
    n = 0
    user = request.user
    if user.is_authenticated:
        from .permissions import role_of
        from .models import Medicine, LabTest, Referral, SupplyRequest
        role = role_of(user)
        if role == "pharmacist":
            n = Medicine.objects.filter(status="Prescribed").count()
        elif role == "lab":
            n = LabTest.objects.filter(status="Requested").count()
        elif role == "department":
            n = Referral.objects.filter(to_department=user.department_account.name, status="Pending").count()
        elif role == "admin":
            n = SupplyRequest.objects.filter(status="Requested").count()
    return {"badge_new": n}
