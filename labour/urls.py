from django.urls import path
from . import views

app_name = "labour"

urlpatterns = [
    path("queue/", views.queue, name="queue"),
    path("open/<int:encounter_id>/", views.case_open, name="case_open"),
    path("case/<int:case_id>/", views.case_workspace, name="case_workspace"),
]