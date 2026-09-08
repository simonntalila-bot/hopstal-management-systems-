from django.urls import path
from . import views
app_name = "pharmacy"

urlpatterns = [
    path("queue/", views.pharmacy_queue, name="pharmacy_queue"),
    path("dispense/<int:encounter_id>/", views.dispense, name="dispense"),
    path("inventory/", views.inventory, name="inventory"),
    path("inventory/<int:drug_id>/toggle/", views.toggle_drug_active, name="toggle_drug"),
    path("stock/<int:drug_id>/", views.stock_adjust, name="stock_adjust"),
]