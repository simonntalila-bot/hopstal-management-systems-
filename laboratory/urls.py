"""
laboratory/urls.py
"""

from django.urls import path
from . import views

app_name = "laboratory"

urlpatterns = [
    path("queue/", views.lab_queue, name="lab_queue"),
path("collect/<int:order_id>/", views.collect_sample, name="collect_sample"),
path("results/<int:order_id>/", views.enter_results, name="enter_results"),
path("print/<int:order_id>/", views.print_results, name="print_results"),
path("start/<int:encounter_id>/", views.lab_only_start, name="lab_only_start"),
]