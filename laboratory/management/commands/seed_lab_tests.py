"""
Seed common lab tests for Argentina Dispensary.
Run: python manage.py seed_lab_tests
"""

from django.core.management.base import BaseCommand
from laboratory.models import LabTest


TESTS = [
    # Hematology
    ("CBC", "Complete Blood Count (Hemogram)", "HEMATOLOGY", "EDTA blood"),
    ("HB", "Hemoglobin", "HEMATOLOGY", "EDTA blood"),
    ("HCT", "Hematocrit", "HEMATOLOGY", "EDTA blood"),
    ("WBC", "White Blood Cell Count", "HEMATOLOGY", "EDTA blood"),
    ("PLT", "Platelet Count", "HEMATOLOGY", "EDTA blood"),
    ("ESR", "Erythrocyte Sedimentation Rate", "HEMATOLOGY", "EDTA blood"),
    ("BLOOD_FILM", "Peripheral Blood Film", "HEMATOLOGY", "EDTA blood"),
    ("MALARIA_RDT", "Malaria Rapid Diagnostic Test", "HEMATOLOGY", "Capillary / EDTA"),
    ("BLOOD_GROUP", "Blood Group & Rh", "HEMATOLOGY", "EDTA blood"),

    # Chemistry
    ("GLUCOSE", "Blood Glucose (RBS/FBS)", "CHEMISTRY", "Fluoride / Serum"),
    ("HBA1C", "Hemoglobin A1c", "CHEMISTRY", "EDTA blood"),
    ("UREA", "Urea (BUN)", "CHEMISTRY", "Serum"),
    ("CREATININE", "Creatinine", "CHEMISTRY", "Serum"),
    ("ELECTROLYTES", "Electrolytes (Na, K, Cl)", "CHEMISTRY", "Serum"),
    ("CALCIUM", "Calcium", "CHEMISTRY", "Serum"),

    # Liver
    ("LFT", "Liver Function Panel", "LIVER", "Serum"),
    ("AST", "AST (SGOT)", "LIVER", "Serum"),
    ("ALT", "ALT (SGPT)", "LIVER", "Serum"),
    ("BILIRUBIN", "Total Bilirubin", "LIVER", "Serum"),
    ("ALP", "Alkaline Phosphatase", "LIVER", "Serum"),
    ("ALBUMIN", "Albumin", "LIVER", "Serum"),
    ("TOTAL_PROTEIN", "Total Protein", "LIVER", "Serum"),

    # Lipid
    ("LIPID", "Lipid Panel", "LIPID", "Serum (fasting)"),
    ("CHOLESTEROL", "Total Cholesterol", "LIPID", "Serum"),
    ("TRIGLYCERIDE", "Triglycerides", "LIPID", "Serum"),
    ("HDL", "HDL Cholesterol", "LIPID", "Serum"),

    # Infectious
    ("HIV", "HIV Antibody / Rapid Test", "INFECTIOUS", "Serum / Whole blood"),
    ("HBSAG", "Hepatitis B Surface Antigen", "INFECTIOUS", "Serum"),
    ("VDRL", "Syphilis (VDRL/RPR)", "INFECTIOUS", "Serum"),
    ("WIDAL", "Widal Test (Typhoid)", "INFECTIOUS", "Serum"),
    ("CRP", "C-Reactive Protein", "INFECTIOUS", "Serum"),

    # Hormones & others
    ("TSH", "Thyroid Stimulating Hormone", "HORMONE", "Serum"),
    ("BHCG", "Pregnancy Test (β-hCG)", "HORMONE", "Serum / Urine"),
    ("PSA", "Prostate Specific Antigen", "HORMONE", "Serum"),
    ("URIC_ACID", "Uric Acid", "HORMONE", "Serum"),
    ("IRON", "Serum Iron", "HORMONE", "Serum"),

    # Urine & Stool
    ("UA", "Urinalysis (Complete)", "URINE_STOOL", "Urine"),
    ("URINE_MICRO", "Urine Microscopy", "URINE_STOOL", "Urine"),
    ("STOOL_MICRO", "Stool Microscopy", "URINE_STOOL", "Stool"),
    ("FOB", "Fecal Occult Blood", "URINE_STOOL", "Stool"),

    # Coagulation
    ("PT_INR", "PT / INR", "COAGULATION", "Citrate blood"),
]


class Command(BaseCommand):
    help = "Seed laboratory test catalog"

    def handle(self, *args, **options):
        created = 0
        for code, name, category, sample in TESTS:
            obj, was_created = LabTest.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "category": category,
                    "sample_type": sample,
                    "is_active": True,
                },
            )
            if was_created:
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded lab tests. New: {created}"))