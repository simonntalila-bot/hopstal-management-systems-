from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("control/", views.admin_home, name="admin_home"),
    path("control/logs/", views.platform_logs, name="platform_logs"),
    path("reception/", views.reception_home, name="reception_home"),
    path("pharmacy/", views.pharmacy_home, name="pharmacy_home"),
    path("doctor/", views.doctor_home, name="doctor_home"),
    path("lab/", views.lab_home, name="lab_home"),
    path("ultrasound/", views.ultrasound_home, name="ultrasound_home"),
    path("injection/", views.injection_home, name="injection_home"),
    path("rch/", views.rch_home, name="rch_home"),
    path("labour/", views.labour_home, name="labour_home"),
    path("control/reports/", views.admin_reports, name="admin_reports"),
    path("reports/doctor/", views.doctor_report, name="doctor_report"),
    path("reports/lab/", views.lab_report, name="lab_report"),
    path("reports/pharmacy/", views.pharmacy_report, name="pharmacy_report"),
    path("reports/rch/", views.rch_report, name="rch_report"),
    path("reports/labour/", views.labour_report, name="labour_report"),
]