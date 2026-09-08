from django.urls import path
from . import views

app_name = "consultations"

urlpatterns = [
    path("queue/", views.consultation_queue, name="consultation_queue"),
    path("consult/<int:encounter_id>/", views.conduct_consultation, name="conduct_consultation"),
    path("rx-print/<int:encounter_id>/", views.external_rx_print, name="external_rx_print"),
]