"""
encounters/urls.py
"""

from django.urls import path
from . import views

app_name = "encounters"

urlpatterns = [
    # Reception – pay-first
    path("payment-pending/", views.payment_pending_queue, name="payment_pending_queue"),
    path("collect-payment/<int:encounter_id>/", views.collect_payment, name="collect_payment"),

    # Doctor queue (paid patients)
    path("doctor-queue/", views.doctor_queue, name="doctor_queue"),
]