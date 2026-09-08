from django.urls import path
from . import views

app_name = "patients"

urlpatterns = [
    path("", views.patient_list, name="patient_list"),
    path("register/", views.patient_register, name="patient_register"),
    path("<int:pk>/", views.patient_detail, name="patient_detail"),
    path("<int:pk>/start-visit/", views.start_visit, name="start_visit"),  # ← new
]