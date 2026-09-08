"""
Seed common drugs for Argentina Dispensary.
Run: python manage.py seed_drugs
"""

from django.core.management.base import BaseCommand
from pharmacy.models import Drug


DRUGS = [
    # Antibiotics
    ("Amoxicillin", "Amoxicillin", "500mg", "Capsule", "capsule", 200, 30),
    ("Amoxicillin Suspension", "Amoxicillin", "125mg/5ml", "Syrup", "bottle", 50, 10),
    ("Azithromycin", "Azithromycin", "500mg", "Tablet", "tablet", 100, 20),
    ("Ciprofloxacin", "Ciprofloxacin", "500mg", "Tablet", "tablet", 100, 20),
    ("Metronidazole", "Metronidazole", "400mg", "Tablet", "tablet", 150, 30),
    ("Doxycycline", "Doxycycline", "100mg", "Capsule", "capsule", 80, 15),

    # Pain / fever
    ("Paracetamol", "Paracetamol", "500mg", "Tablet", "tablet", 500, 50),
    ("Paracetamol Suspension", "Paracetamol", "120mg/5ml", "Syrup", "bottle", 80, 15),
    ("Ibuprofen", "Ibuprofen", "400mg", "Tablet", "tablet", 200, 30),
    ("Diclofenac", "Diclofenac", "50mg", "Tablet", "tablet", 150, 25),

    # Antimalarials
    ("AL (Artemether-Lumefantrine)", "Artemether/Lumefantrine", "20/120mg", "Tablet", "tablet", 100, 20),
    ("Quinine", "Quinine sulphate", "300mg", "Tablet", "tablet", 60, 10),

    # GI
    ("ORS", "Oral Rehydration Salts", "", "Sachet", "sachet", 200, 40),
    ("Omeprazole", "Omeprazole", "20mg", "Capsule", "capsule", 100, 20),
    ("Metoclopramide", "Metoclopramide", "10mg", "Tablet", "tablet", 80, 15),

    # Respiratory / allergy
    ("Cetirizine", "Cetirizine", "10mg", "Tablet", "tablet", 120, 20),
    ("Salbutamol Inhaler", "Salbutamol", "100mcg", "Inhaler", "inhaler", 30, 5),
    ("Prednisolone", "Prednisolone", "5mg", "Tablet", "tablet", 100, 15),

    # Others
    ("Multivitamin", "Multivitamins", "", "Tablet", "tablet", 200, 40),
    ("Folic Acid", "Folic acid", "5mg", "Tablet", "tablet", 150, 30),
    ("Ferrous Sulphate", "Ferrous sulphate", "200mg", "Tablet", "tablet", 150, 30),
    ("Insulin (Actrapid)", "Insulin soluble", "100IU/ml", "Injection", "vial", 20, 5),
]


class Command(BaseCommand):
    help = "Seed common drugs into the pharmacy catalog"

    def handle(self, *args, **options):
        created = 0
        for name, generic, strength, form, unit, stock, reorder in DRUGS:
            obj, was_created = Drug.objects.get_or_create(
                name=name,
                defaults={
                    "generic_name": generic,
                    "strength": strength,
                    "form": form,
                    "unit": unit,
                    "stock_quantity": stock,
                    "reorder_level": reorder,
                    "is_active": True,
                },
            )
            if was_created:
                created += 1
            else:
                # Optional: refresh stock if already exists
                pass
        self.stdout.write(self.style.SUCCESS(f"Drugs seeded. New: {created}"))