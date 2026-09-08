from django.urls import path
from . import views

app_name = "ultrasound"
urlpatterns = [
    path("queue/", views.queue, name="queue"),
    path("service/<int:encounter_id>/", views.service, name="service"),
]