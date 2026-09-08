from django.urls import path
from . import views

app_name = "injection"

urlpatterns = [
    path("queue/", views.queue, name="queue"),
    path("service/<int:encounter_id>/", views.service, name="service"),
    path("surgery/queue/", views.surgery_queue, name="surgery_queue"),
    path(
        "surgery/service/<int:encounter_id>/",
        views.surgery_service,
        name="surgery_service",
    ),
]