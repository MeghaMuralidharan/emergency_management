from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path, include
from django.contrib.auth import views as auth_views
from core.forms import AdminLoginForm, DepartmentLoginForm, DoctorLoginForm, LabLoginForm, PharmacistLoginForm, StaffLoginForm
from core.views import logout_view

TEMPLATE = "registration/login.html"


def portal_login(form, portal):
    return auth_views.LoginView.as_view(
        template_name=TEMPLATE, authentication_form=form,
        redirect_authenticated_user=True, extra_context={"portal": portal})


urlpatterns = [
    # Three separate logins
    path("admin/", portal_login(AdminLoginForm, "admin"), name="login"),         # Admin
    path("doctor/", portal_login(DoctorLoginForm, "doctor"), name="doctor_login"),  # Doctor
    path("staff/", portal_login(StaffLoginForm, "staff"), name="staff_login"),      # Staff
    path("department/", portal_login(DepartmentLoginForm, "department"), name="department_login"),  # Department login
    path("pharmacist/", portal_login(PharmacistLoginForm, "pharmacist"), name="pharmacist_login"),  # Pharmacist
    path("lab/", portal_login(LabLoginForm, "lab"), name="lab_login"),                # Lab
    path("login/", lambda request: redirect("login")),  # old address -> /admin/
    path("logout/", logout_view, name="logout"),
    # Django's built-in data admin (superusers) moved out of the way
    path("django-admin/", admin.site.urls),
    path("", include("core.urls")),
]
