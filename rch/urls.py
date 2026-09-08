from django.urls import path
from . import views

app_name = "rch"

urlpatterns = [
    path("queue/", views.queue, name="queue"),
    path("start/<int:encounter_id>/", views.service_start, name="service_start"),
    path("service/<int:encounter_id>/", views.service_form, name="service_form"),
]