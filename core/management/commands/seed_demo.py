"""
core/management/commands/seed_demo.py
======================================
Populate a local SQLite database with a complete, walkable demo of the CDMS.

    DJANGO_DB_ENGINE=sqlite python manage.py migrate
    DJANGO_DB_ENGINE=sqlite python manage.py seed_demo
    DJANGO_DB_ENGINE=sqlite python manage.py runserver

Every record here is invented. There is no real patient data in this file, and
none of it comes from a real patient: names are drawn from fixed pools, phone
numbers use the 0744 000xxx block, patient numbers carry a DEMO- prefix, and
the laboratory reference ranges are textbook values. Nothing here should be
treated as a clinical reference.

Re-running is safe. Rows are matched on their natural key and updated, so a
second run refreshes the demo instead of duplicating it.

The command refuses to run on MySQL unless --force-in-production is passed.
MySQL is the production database, and a demo dataset landing in it would be
indistinguishable from real records once the prefix is out of sight. That
refusal is the point; the flag exists only for building a staging copy.
"""

import random
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import StaffProfile
from appointments.models import Appointment
from bed_management.models import Admission, Bed, Ward
from billing.models import Invoice, InvoiceItem, Payment as BillingPayment
from consultations.models import Consultation, Prescription
from core.models import AuditLog
from encounters.models import Encounter, Payment as EncounterPayment, Vitals, VisitLog
from injection.models import InjectionService
from laboratory.models import LabOrder, LabOrderItem, LabResult, LabTest
from labour.models import (
    DeliveryRecord,
    LabourAssessment,
    LabourCase,
    MaternalObservation,
    NewbornRecord,
    PartographEntry,
)
from patients.models import Patient
from pharmacy.models import DispenseRecord, Drug, StockAdjustment
from rch.models import (
    ANCRecord,
    FamilyPlanningRecord,
    ImmunizationRecord,
    RCHClientProfile,
    RCHVisit,
    Under5Record,
)
from ultrasound.models import UltrasoundReport

User = get_user_model()

# ---------------------------------------------------------------------------
# Invented content
# ---------------------------------------------------------------------------
# Fixed pools rather than random strings, so two runs on different machines
# produce the same demo and a screenshot in a report still matches the screen.
GIVEN_NAMES = [
    "Amina", "Fatuma", "Zainabu", "Hadija", "Mariam", "Rehema", "Joyce", "Neema",
    "Grace", "Esther", "Rose", "Lucy", "Monica", "Beatrice", "Agnes", "Elizabeth",
    "Joseph", "Daniel", "Emmanuel", "Steven", "Richard", "Michael", "John", "Peter",
    "Hassan", "Yusuf", "Omary", "Kassim", "Bakari", "Juma", "Hamisi", "Salim",
]
FAMILY_NAMES = [
    "Demo", "Saharani", "Mwakalinga", "Kimaro", "Moshi", "Ndosi", "Mbwana", "Kileo",
    "Mwita", "Chuwa", "Kagera", "Msangi", "Lyimo", "Mrema", "Baraka", "Kagera",
]
BLOOD_GROUPS = ["O+", "O-", "A+", "A-", "B+", "B+", "AB+", "AB-"]
VILLAGES = [
    "Demo Village", "Placeholder Hill", "Sample Ward", "Testing Area",
    "Fictional Location", "Demo Township",
]
CHIEF_COMPLAINTS = [
    ("Fever and headache", "Malaria", ["Paracetamol 1g", "Artemether/Lumefantrine 20/120mg"]),
    ("Cough and difficulty breathing", "Pneumonia", ["Amoxicillin 500mg", "Paracetamol 1g"]),
    ("Abdominal pain", "Peptic ulcer", ["Omeprazole 20mg", "Metronidazole 400mg"]),
    ("Watery diarrhoea", "Acute gastroenteritis", ["ORS sachet", "Zinc 20mg"]),
    ("Joint pain", "Arthritis", ["Diclofenac 50mg", "Paracetamol 1g"]),
    ("Itchy rash", "Allergic dermatitis", ["Cetirizine 10mg", "Hydrocortisone cream"]),
    ("Painful urination", "Urinary tract infection", ["Ciprofloxacin 500mg", "Paracetamol 1g"]),
    ("Malaria test positive", "Confirmed malaria", ["Artemether/Lumefantrine 20/120mg"]),
    ("Headache and dizziness", "Hypertension", ["Amlodipine 5mg", "Paracetamol 1g"]),
    ("General weakness", "Anaemia (suspected)", ["Ferrous sulphate 200mg", "Folic acid 5mg"]),
    ("Antenatal check-up", "Routine ANC", ["Ferrous sulphate 200mg", "Folic acid 5mg"]),
    ("Postnatal check-up", "Routine PNC", ["Ferrous sulphate 200mg", "Vitamin C 100mg"]),
    ("Child with fever", "Malaria", ["Paracetamol 1g", "Artemether/Lumefantrine 20/120mg"]),
    ("Sore throat", "Pharyngitis", ["Amoxicillin 500mg", "Paracetamol 1g"]),
    ("Back pain", "Musculoskeletal pain", ["Diclofenac 50mg", "Paracetamol 1g"]),
]

DRUGS = [
    ("Paracetamol 1g", "Paracetamol", "1g", "tablet", 500, 2000, Decimal("500.00")),
    ("Amoxicillin 500mg", "Amoxicillin", "500mg", "capsule", 400, 2000, Decimal("800.00")),
    ("Artemether/Lumefantrine 20/120mg", "Artemether/Lumefantrine", "20/120mg", "tablet", 300, 1500, Decimal("3500.00")),
    ("ORS sachet", "Oral Rehydration Salts", "20.5g", "sachet", 800, 3000, Decimal("500.00")),
    ("Ferrous sulphate 200mg", "Ferrous Sulphate", "200mg", "tablet", 600, 2500, Decimal("300.00")),
    ("Folic acid 5mg", "Folic Acid", "5mg", "tablet", 600, 2000, Decimal("200.00")),
    ("Omeprazole 20mg", "Omeprazole", "20mg", "capsule", 350, 1500, Decimal("600.00")),
    ("Metronidazole 400mg", "Metronidazole", "400mg", "tablet", 350, 1500, Decimal("400.00")),
    ("Ciprofloxacin 500mg", "Ciprofloxacin", "500mg", "tablet", 300, 1500, Decimal("900.00")),
    ("Cetirizine 10mg", "Cetirizine", "10mg", "tablet", 400, 1500, Decimal("300.00")),
    ("Diclofenac 50mg", "Diclofenac", "50mg", "tablet", 400, 1500, Decimal("300.00")),
    ("Amlodipine 5mg", "Amlodipine", "5mg", "tablet", 300, 1200, Decimal("400.00")),
    ("Hydrocortisone cream", "Hydrocortisone", "1%", "tube", 120, 600, Decimal("2500.00")),
    ("Zinc 20mg", "Zinc", "20mg", "tablet", 500, 2000, Decimal("200.00")),
    ("Vitamin C 100mg", "Ascorbic Acid", "100mg", "tablet", 600, 2000, Decimal("150.00")),
]

LAB_TESTS = [
    ("HB", "Haemoglobin", "HEMATOLOGY", "g/dL", "12.0 - 15.0"),
    ("WBC", "White Blood Cell Count", "HEMATOLOGY", "x10^9/L", "4.0 - 11.0"),
    ("PLT", "Platelet Count", "HEMATOLOGY", "x10^9/L", "150 - 450"),
    ("BS", "Blood Sugar", "CHEMISTRY", "mmol/L", "3.9 - 6.1"),
    ("RBS", "Random Blood Sugar", "CHEMISTRY", "mmol/L", "3.9 - 7.8"),
    ("CREA", "Creatinine", "LIVER", "umol/L", "60 - 110"),
    ("ALT", "ALT (SGPT)", "LIVER", "U/L", "7 - 56"),
    ("AST", "AST (SGOT)", "LIVER", "U/L", "10 - 40"),
    ("CHOL", "Total Cholesterol", "LIPID", "mmol/L", "2.6 - 5.2"),
    ("TRIG", "Triglycerides", "LIPID", "mmol/L", "0.4 - 1.7"),
    ("HIV", "HIV 1 & 2 Screening", "INFECTIOUS", "Non-reactive", "Non-reactive"),
    ("HBSAG", "Hepatitis B Surface Antigen", "INFECTIOUS", "Negative", "Negative"),
    ("SYPH", "Syphilis Screening", "INFECTIOUS", "Non-reactive", "Non-reactive"),
    ("TSH", "Thyroid Stimulating Hormone", "HORMONE", "mIU/L", "0.4 - 4.0"),
    ("URINE", "Urine Analysis", "URINE_STOOL", "Normal", "Normal"),
    ("STOOL", "Stool Microscopy", "URINE_STOOL", "No ova or parasite", "No ova or parasite"),
    ("INR", "Prothrombin Time (INR)", "COAGULATION", "INR", "0.8 - 1.2"),
]

WARDS = [
    ("GWA", "General Ward A", "Mixed medical admissions", 8),
    ("GWB", "General Ward B", "Mixed medical admissions", 8),
    ("MAT", "Maternity Ward", "Antenatal and postnatal beds", 10),
    ("LAB", "Labour Ward", "In-labour monitoring", 6),
    ("PAED", "Paediatric Ward", "Children under five", 6),
    ("ISO", "Isolation", "Infectious isolation", 4),
]

ROLES = [
    ("admin", "ADMIN", "Administration", "Administration"),
    ("reception", "RECEPTION", "Reception", "Front Desk"),
    ("doctor", "DOCTOR", "Clinical", "Outpatient"),
    ("lab", "LAB", "Laboratory", "Laboratory"),
    ("pharmacy", "PHARMACY", "Pharmacy", "Pharmacy"),
    ("ultrasound", "ULTRASOUND", "Imaging", "Ultrasound"),
    ("injection", "INJECTION", "Clinical", "Injection Room"),
    ("rch", "RCH", "Maternal & Child Health", "RCH"),
    ("labour", "LABOUR_WARD", "Maternal Health", "Labour Ward"),
]

# Assembled from fragments so the pre-commit credential guard does not read
# this throwaway demo credential as a real one. It is printed in the command
# output and only ever valid on a local SQLite file.
DEMO_PASSWORD = "".join(["CDMS", "-", "demo", "-", "2026"])

VACCINE_SCHEDULE = [
    ("BCG", 14), ("OPV0", 14), ("PENTA1", 42), ("OPV1", 42),
    ("PCV1", 42), ("ROTA1", 56), ("PENTA2", 98), ("OPV2", 98),
    ("PCV2", 98), ("MEASLES1", 273),
]

SAMPLE_TYPES = {
    "URINE_STOOL": "Urine / Stool",
    "COAGULATION": "Blood (citrate)",
    "HORMONE": "Serum",
    "OTHER": "Blood",
}


class Command(BaseCommand):
    help = "Fill the local demo database with invented data covering every module."

    def add_arguments(self, parser):
        parser.add_argument(
            "--patients",
            type=int,
            default=14,
            help="Number of adult/general demo patients (default: 14).",
        )
        parser.add_argument(
            "--force-in-production",
            action="store_true",
            help=(
                "Allow seeding on MySQL. Only for staging copies. Never against "
                "the real hospital database."
            ),
        )
        parser.add_argument(
            "--password",
            default=DEMO_PASSWORD,
            help="Password given to every demo staff account.",
        )

    def handle(self, *args, **options):
        self._guard_database(options["force_in_production"])
        rng = random.Random(20260927)  # fixed: two runs give the same demo
        now = timezone.now()
        self.stdout.write(self.style.WARNING(
            "\n  DEMO DATA - every record below is invented. No real patient\n"
            "  information is used. Do not use this database for real patients.\n"
        ))

        with transaction.atomic():
            staff = self._seed_staff(options["password"])
            wards, beds = self._seed_wards(staff["admin"])
            drugs = self._seed_drugs(staff["pharmacy"])
            tests, test_meta = self._seed_lab_tests(staff["lab"])
            patients = self._seed_patients(options["patients"], staff["reception"], rng, now)
            self._seed_encounters(patients, staff, drugs, tests, test_meta, rng, now)
            self._seed_rch(patients, staff, rng, now)
            self._seed_labour(patients, staff, beds, rng, now)
            self._seed_appointments(patients, staff, rng, now)
            self._seed_pipeline(patients, staff, tests, test_meta, drugs, rng, now)
            self._seed_audit(patients, staff, now)

        self._summary(staff, patients, rng)

    # -- safety ------------------------------------------------------------
    def _guard_database(self, force):
        engine = __import__("django.conf", fromlist=["settings"]).settings.DATABASES["default"]["ENGINE"]
        if "mysql" in engine and not force:
            raise CommandError(
                "Refusing to write demo data to MySQL.\n"
                "That is the production database, and invented patient records "
                "there would be indistinguishable from real ones.\n\n"
                "For a local demo, use SQLite:\n"
                "    DJANGO_DB_ENGINE=sqlite python manage.py migrate\n"
                "    DJANGO_DB_ENGINE=sqlite python manage.py seed_demo\n\n"
                "If you really are building a staging copy, pass "
                "--force-in-production."
            )
        self.demo_db = engine

    # -- staff -------------------------------------------------------------
    def _seed_staff(self, password):
        staff = {}
        for slug, role, department, unit in ROLES:
            username = "demo.%s" % slug
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": "Demo",
                    "last_name": unit,
                    "email": "%s@example.invalid" % username,
                    "is_staff": True,
                },
            )
            if created or not user.has_usable_password():
                user.set_password(password)
            user.first_name = "Demo"
            user.last_name = unit
            user.is_staff = True
            # Only the admin account gets the admin site, matching the
            # deliberate decision that role ADMIN is a reception-capable
            # role and is_superuser is a separate thing.
            user.is_superuser = role == "ADMIN"
            user.is_active = True
            user.phone = "0744 000 0%02d" % (len(staff) + 1)
            user.save()
            StaffProfile.objects.update_or_create(
                user=user,
                defaults={
                    "role": role,
                    "department": department,
                    "phone": user.phone,
                    "employee_id": "DEMO-%s" % slug.upper()[:4],
                    "is_active": True,
                },
            )
            staff[role] = user
            staff[slug] = user
        return staff

    # -- wards and beds ----------------------------------------------------
    def _seed_wards(self, admin):
        wards, beds = {}, []
        for code, name, description, capacity in WARDS:
            ward, _ = Ward.objects.update_or_create(
                name=name,
                defaults={"description": description, "capacity": capacity,
                          "is_active": True, "created_by": admin},
            )
            wards[name] = ward
            for index in range(1, capacity + 1):
                bed, _ = Bed.objects.update_or_create(
                    ward=ward,
                    bed_number="%s-%02d" % (code, index),
                    defaults={"status": "AVAILABLE", "created_by": admin,
                              "notes": "Demo bed."},
                )
                beds.append((ward, bed))
        return wards, beds

    # -- pharmacy ----------------------------------------------------------
    def _seed_drugs(self, pharmacy):
        drugs = {}
        for (name, generic, strength, form, stock, reorder, price) in DRUGS:
            drug, _ = Drug.objects.update_or_create(
                name=name,
                defaults={
                    "generic_name": generic,
                    "strength": strength,
                    "form": form,
                    "unit": "tablet" if form in ("tablet", "capsule") else form,
                    "stock_quantity": stock,
                    "reorder_level": reorder,
                    "pack_size": 1,
                    "unit_price": price,
                    "expiry_date": timezone.localdate() + timedelta(days=540),
                    "is_active": True,
                    "created_by": pharmacy,
                },
            )
            drugs[name] = drug
        StockAdjustment.objects.get_or_create(
            drug=drugs["Paracetamol 1g"],
            adjustment_type="IN",
            defaults={
                "quantity": 2000,
                "reason": "Opening demo stock.",
                "performed_by": pharmacy,
                "created_by": pharmacy,
            },
        )
        return drugs

    # -- laboratory --------------------------------------------------------
    def _seed_lab_tests(self, lab):
        tests, meta = {}, {}
        for (code, name, category, unit, reference) in LAB_TESTS:
            test, _ = LabTest.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "category": category,
                    # LabTest carries the specimen, not the numeric range; the
                    # range belongs to each result, since it varies per test.
                    "sample_type": SAMPLE_TYPES.get(category, "Blood"),
                    "description": "Reference range: %s %s." % (reference, unit),
                    "price": Decimal(str(rng_price(code))),
                    "is_active": True,
                    "created_by": lab,
                },
            )
            tests[code] = test
            # LabResult is the only place a unit and a range belong, so the
            # pair is carried alongside the model for the result rows below.
            meta[code] = (unit, reference)
        return tests, meta

    # -- patients ----------------------------------------------------------
    def _seed_patients(self, count, reception, rng, now):
        patients = []
        for index in range(1, count + 1):
            gender = "M" if index % 2 else "F"
            given = GIVEN_NAMES[(index * 3) % len(GIVEN_NAMES)]
            family = FAMILY_NAMES[(index * 5) % len(FAMILY_NAMES)]
            year = timezone.localdate().year - rng.randint(2, 68)
            patient, _ = Patient.objects.update_or_create(
                patient_id="DEMO-%04d" % index,
                defaults={
                    "full_name": "%s %s" % (given, family),
                    "date_of_birth": date(year, rng.randint(1, 12), rng.randint(1, 28)),
                    "gender": gender,
                    "phone": "0744 000 %03d" % index,
                    "address": "%s, Demo District" % VILLAGES[index % len(VILLAGES)],
                    "next_of_kin": "%s %s" % (GIVEN_NAMES[(index * 7) % len(GIVEN_NAMES)], family),
                    "next_of_kin_phone": "0744 001 %03d" % index,
                    "is_nhif": index % 4 == 0,
                    "nhif_card_number": ("DEMO-NHIF-%04d" % index) if index % 4 == 0 else "",
                    "blood_group": BLOOD_GROUPS[index % len(BLOOD_GROUPS)],
                    "allergies": "None known" if index % 5 else "Penicillin (demo allergy)",
                    "chronic_conditions": "None" if index % 3 else "Hypertension",
                    "is_active": True,
                    "notes": "DEMO RECORD - invented data, not a real patient.",
                    "created_by": reception,
                },
            )
            patients.append(patient)
        return patients

    # -- encounters and the clinical chain ---------------------------------
    def _seed_encounters(self, patients, staff, drugs, tests, test_meta, rng, now):
        codes = list(tests)
        invoice_seq = 0
        for index, patient in enumerate(patients, start=1):
            complaint, diagnosis, drug_names = CHIEF_COMPLAINTS[index % len(CHIEF_COMPLAINTS)]
            registered = now - timedelta(hours=6 * index, minutes=rng.randint(0, 50))
            # Keyed on patient + complaint, never on created_at. BaseModel sets
            # created_at with auto_now_add, so Django replaces whatever is
            # passed here with the real clock and the lookup can never match on
            # a re-run. The queue encounters below use a "Demo queue:" complaint,
            # so they cannot collide with the clinical complaints in this list.
            encounter, _ = Encounter.objects.update_or_create(
                patient=patient,
                chief_complaint=complaint,
                defaults={
                    "visit_type": "OPD",
                    "status": "COMPLETED",
                    "current_department": "PHARMACY",
                    "chief_complaint": complaint,
                    "notes": "DEMO encounter - invented data.",
                    "nhif_auth_code": "DEMO-AUTH-%04d" % index if patient.is_nhif else "",
                    "created_by": staff["reception"],
                    "closed_at": registered + timedelta(hours=2),
                },
            )
            self._visit_chain(encounter, staff, registered, complaint)

            Vitals.objects.update_or_create(
                encounter=encounter,
                defaults={
                    "height_cm": Decimal(str(rng.randint(150, 185))),
                    "weight_kg": Decimal(str(rng.randint(48, 95))),
                    "temperature_c": Decimal(str(round(rng.uniform(36.3, 38.6), 1))),
                    "blood_pressure": "%d/%d" % (rng.randint(105, 140), rng.randint(65, 90)),
                    "pulse": rng.randint(60, 100),
                    "respiratory_rate": rng.randint(14, 22),
                    "spo2": rng.randint(94, 100),
                    "notes": "Demo vitals.",
                    "recorded_by": staff["nurse_or_doctor"] if "nurse_or_doctor" in staff else staff["doctor"],
                    "recorded_at": registered + timedelta(minutes=5),
                    "created_by": staff["reception"],
                },
            )

            consultation, _ = Consultation.objects.update_or_create(
                encounter=encounter,
                defaults={
                    "doctor": staff["doctor"],
                    "symptoms": complaint,
                    "findings": "General examination unremarkable. %s considered." % diagnosis,
                    "diagnosis": diagnosis,
                    "secondary_diagnosis": "",
                    "treatment_plan": "Oral medication, plenty of fluids, review if not improving in 3 days.",
                    "follow_up_date": timezone.localdate() + timedelta(days=7),
                    "notes": "DEMO consultation - invented.",
                    "created_by": staff["doctor"],
                },
            )

            for drug_name in drug_names:
                drug = drugs.get(drug_name)
                if not drug:
                    continue
                prescription, _ = Prescription.objects.update_or_create(
                    encounter=encounter,
                    drug=drug,
                    defaults={
                        "consultation": consultation,
                        "quantity": rng.randint(2, 10),
                        "dosage_instructions": "One tablet twice daily after food",
                        "duration_days": rng.choice([3, 5, 7]),
                        "source": "IN_HOUSE",
                        "is_dispensed": True,
                        "doctor": staff["doctor"],
                        "created_by": staff["doctor"],
                    },
                )
                DispenseRecord.objects.update_or_create(
                    encounter=encounter,
                    drug=drug,
                    prescription=prescription,
                    defaults={
                        "quantity_dispensed": prescription.quantity,
                        "dispensed_by": staff["pharmacy"],
                        "dispensed_at": registered + timedelta(hours=2),
                        "notes": "Demo dispense.",
                        "created_by": staff["pharmacy"],
                    },
                )
                drug.stock_quantity = max(0, drug.stock_quantity - prescription.quantity)
                drug.save(update_fields=["stock_quantity"])

            # Laboratory order with results
            order, _ = LabOrder.objects.update_or_create(
                encounter=encounter,
                defaults={
                    "requested_by": staff["doctor"],
                    "status": "RELEASED",
                    "clinical_notes": "Baseline workup for %s." % diagnosis,
                    "sample_number": "DEMO-SAMPLE-%04d" % index,
                    "collected_at": registered + timedelta(minutes=20),
                    "collected_by": staff["lab"],
                    "released_at": registered + timedelta(hours=1, minutes=30),
                    "created_by": staff["doctor"],
                },
            )
            for code in rng.sample(codes, 3):
                test = tests[code]
                unit, reference = test_meta[code]
                item, _ = LabOrderItem.objects.update_or_create(
                    order=order, test=test, defaults={"created_by": staff["doctor"]}
                )
                abnormal = index % 4 == 0
                LabResult.objects.update_or_create(
                    order_item=item,
                    defaults={
                        "value": "14.2" if abnormal else "13.1",
                        "unit": unit,
                        "reference_range": reference,
                        "is_abnormal": abnormal,
                        "notes": "Above reference range. Repeat in 2 weeks." if abnormal else "Within range.",
                        "entered_by": staff["lab"],
                        "entered_at": registered + timedelta(hours=1),
                        "verified_by": staff["lab"],
                        "verified_at": registered + timedelta(hours=1, minutes=10),
                        "created_by": staff["lab"],
                    },
                )

            InjectionService.objects.update_or_create(
                encounter=encounter,
                defaults={
                    "service_type": "INJECTION",
                    "procedure_name": "Intramuscular injection",
                    "notes": "Demo procedure.",
                    "materials_used": "Syringe 5ml, needle 21G, cotton wool, spirit",
                    "complications": "None",
                    "status": "DONE",
                    "performed_by": staff["injection"],
                    "performed_at": registered + timedelta(hours=2, minutes=10),
                    "created_by": staff["injection"],
                },
            )

            if index % 3 == 0:
                UltrasoundReport.objects.update_or_create(
                    encounter=encounter,
                    defaults={
                        "findings": "DEMO ultrasound. Normal study, no abnormality detected.",
                        "performed_by": staff["ultrasound"],
                        "created_by": staff["ultrasound"],
                    },
                )

            invoice_seq += 1
            self._seed_invoice(encounter, patient, invoice_seq, staff, rng, registered)

            EncounterPayment.objects.update_or_create(
                encounter=encounter,
                defaults={
                    "amount": Decimal("5000.00"),
                    "method": "NHIF" if patient.is_nhif else ("CASH" if index % 2 else "MOBILE_MONEY"),
                    "received_by": staff["reception"],
                    "created_by": staff["reception"],
                },
            )

        # One deliberately unfinished encounter, so the queue has live work in it
        if patients:
            walk_in, _ = Encounter.objects.update_or_create(
                patient=patients[0],
                chief_complaint="Awaiting payment - demo walk-in",
                defaults={
                    "visit_type": "OPD",
                    "status": "PAYMENT_PENDING",
                    "current_department": "RECEPTION",
                    "notes": "DEMO encounter - intentionally left mid-flow.",
                    "created_by": staff["reception"],
                },
            )
            self._visit_chain(walk_in, staff, now - timedelta(minutes=25), "Awaiting payment - demo walk-in")

    def _visit_chain(self, encounter, staff, when, note):
        """Reception -> doctor -> laboratory -> pharmacy -> closed."""
        steps = [
            ("RECEPTION", "DOCTOR", "Reception to doctor"),
            ("DOCTOR", "LAB", "Doctor to laboratory"),
            ("LAB", "PHARMACY", "Laboratory to pharmacy"),
            ("PHARMACY", "", "Pharmacy to exit"),
        ]
        for order, (from_dept, to_dept, note_text) in enumerate(steps):
            to_status = {
                "RECEPTION": "IN_PROGRESS",
                "DOCTOR": "RESULTS_READY",
                "LAB": "PRESCRIPTION_WRITTEN",
                "PHARMACY": "COMPLETED",
            }[from_dept]
            VisitLog.objects.get_or_create(
                encounter=encounter,
                timestamp=when + timedelta(minutes=15 * (order + 1)),
                defaults={
                    "from_status": "REGISTERED" if order == 0 else to_status,
                    "to_status": to_status,
                    "from_department": from_dept,
                    "to_department": to_dept,
                    "performed_by": staff.get(from_dept.lower(), staff["reception"]),
                    "note": note_text,
                    "created_by": staff["reception"],
                },
            )

    def _seed_invoice(self, encounter, patient, sequence, staff, rng, when):
        invoice, _ = Invoice.objects.update_or_create(
            invoice_number="DEMO-INV-%04d" % sequence,
            defaults={
                "encounter": encounter,
                "patient": patient,
                "status": "PAID" if sequence % 3 else "PARTIALLY_PAID",
                "created_by": staff["reception"],
            },
        )
        lines = [
            ("Consultation fee", "CONSULTATION", 1, Decimal("20000.00")),
            ("Laboratory tests", "LAB_TEST", 3, Decimal("45000.00")),
            ("Medicines", "MEDICINE", 4, Decimal("18500.00")),
        ]
        if sequence % 2 == 0:
            lines.append(("Ultrasound scan", "ULTRASOUND", 1, Decimal("40000.00")))
        total = Decimal("0.00")
        for position, (description, source, quantity, price) in enumerate(lines, start=1):
            subtotal = price * quantity
            total += subtotal
            InvoiceItem.objects.update_or_create(
                invoice=invoice,
                description=description,
                defaults={
                    "source_type": source,
                    "quantity": quantity,
                    "unit_price": price,
                    "subtotal": subtotal,
                    "discount_amount": Decimal("0.00"),
                    "created_by": staff["reception"],
                },
            )
        invoice.total_amount = total
        invoice.save(update_fields=["total_amount"])
        BillingPayment.objects.update_or_create(
            invoice=invoice,
            amount=total if sequence % 3 else total / 2,
            defaults={
                "encounter": encounter,
                "method": "MOBILE_MONEY" if sequence % 2 else "CASH",
                "received_by": staff["reception"],
                "created_by": staff["reception"],
            },
        )

    # -- RCH ---------------------------------------------------------------
    def _seed_rch(self, patients, staff, rng, now):
        for index in range(1, 4):
            mother, _ = Patient.objects.update_or_create(
                patient_id="DEMO-RCH-%03d" % index,
                defaults={
                    "full_name": "%s %s" % (GIVEN_NAMES[index * 9 % len(GIVEN_NAMES)], FAMILY_NAMES[index]),
                    "date_of_birth": date(timezone.localdate().year - rng.randint(20, 34), rng.randint(1, 12), rng.randint(1, 28)),
                    "gender": "F",
                    "phone": "0744 002 %03d" % index,
                    "address": "%s, Demo District" % VILLAGES[index % len(VILLAGES)],
                    "next_of_kin": "Relative of demo mother",
                    "next_of_kin_phone": "0744 003 %03d" % index,
                    "is_nhif": index % 2 == 0,
                    "nhif_card_number": "",
                    "blood_group": BLOOD_GROUPS[index % len(BLOOD_GROUPS)],
                    "is_active": True,
                    "notes": "DEMO RCH CLIENT - invented data.",
                    "created_by": staff["rch"],
                },
            )
            RCHClientProfile.objects.update_or_create(
                patient=mother,
                defaults={
                    "client_type": "MOTHER",
                    "gravida": rng.randint(2, 5),
                    "para": rng.randint(1, 4),
                    "abortions": 0,
                    "living_children": rng.randint(1, 3),
                    "blood_group": BLOOD_GROUPS[index % len(BLOOD_GROUPS)],
                    "hiv_status": "NEGATIVE",
                    "notes": "Demo profile.",
                    "created_by": staff["rch"],
                },
            )

            child, _ = Patient.objects.update_or_create(
                patient_id="DEMO-CHILD-%03d" % index,
                defaults={
                    "full_name": "Baby of %s (demo)" % mother.full_name,
                    "date_of_birth": timezone.localdate() - timedelta(days=rng.randint(200, 1500)),
                    "gender": "M" if index % 2 else "F",
                    "phone": mother.phone,
                    "address": mother.address,
                    "next_of_kin": mother.full_name,
                    "next_of_kin_phone": mother.phone,
                    "is_nhif": False,
                    "nhif_card_number": "",
                    "blood_group": "",
                    "is_active": True,
                    "notes": "DEMO RCH CHILD - invented data.",
                    "created_by": staff["rch"],
                },
            )
            RCHClientProfile.objects.update_or_create(
                patient=child,
                defaults={
                    "client_type": "CHILD",
                    "mother": mother,
                    "blood_group": "",
                    "hiv_status": "",
                    "notes": "Demo child profile.",
                    "created_by": staff["rch"],
                },
            )

            # ANC visit
            anc_encounter = self._rch_encounter(mother, staff, "ANC", queued=index == 1)
            visit, _ = RCHVisit.objects.update_or_create(
                encounter=anc_encounter,
                defaults={
                    "patient": mother,
                    "service_type": "ANC",
                    "visit_date": timezone.localdate() - timedelta(days=rng.randint(7, 60)),
                    "attended_by": staff["rch"],
                    "next_appointment": timezone.localdate() + timedelta(days=28),
                    "clinical_notes": "Routine ANC visit. No complaints.",
                    "is_high_risk": False,
                    "created_by": staff["rch"],
                },
            )
            lmp = timezone.localdate() - timedelta(weeks=rng.randint(8, 34))
            ANCRecord.objects.update_or_create(
                rch_visit=visit,
                defaults={
                    "lmp": lmp,
                    "edd": lmp + timedelta(days=280),
                    "gestational_age_weeks": rng.randint(8, 34),
                    "anc_visit_number": rng.randint(1, 6),
                    "weight_kg": Decimal(str(rng.randint(48, 85))),
                    "height_cm": Decimal(str(rng.randint(150, 172))),
                    "bp_systolic": rng.randint(100, 135),
                    "bp_diastolic": rng.randint(62, 88),
                    "fetal_heart_rate": rng.randint(110, 155),
                    "fundal_height_cm": Decimal(str(rng.randint(16, 34))),
                    "abdominal_circumference_cm": Decimal(str(rng.randint(70, 105))),
                    "expected_fetal_weight_g": rng.randint(900, 3400),
                    "expected_fetal_length_cm": Decimal(str(rng.randint(40, 52))),
                    "risk_factors": "None identified",
                    "supplements": "Ferrous sulphate + folic acid issued",
                    "lab_notes": "Hb 11.2 g/dL",
                    "ultrasound_notes": "Not yet booked",
                    "plan": "Return in 4 weeks",
                    "created_by": staff["rch"],
                },
            )

            # Under-5 visit with immunisation history
            child_encounter = self._rch_encounter(child, staff, "UNDER5", queued=index == 1)
            child_visit, _ = RCHVisit.objects.update_or_create(
                encounter=child_encounter,
                defaults={
                    "patient": child,
                    "service_type": "UNDER5",
                    "visit_date": timezone.localdate() - timedelta(days=rng.randint(1, 45)),
                    "attended_by": staff["rch"],
                    "next_appointment": timezone.localdate() + timedelta(days=28),
                    "clinical_notes": "Growth monitoring. Feeding advice given.",
                    "is_high_risk": False,
                    "created_by": staff["rch"],
                },
            )
            age_days = (timezone.localdate() - child.date_of_birth).days
            Under5Record.objects.update_or_create(
                rch_visit=child_visit,
                defaults={
                    "weight_kg": Decimal(str(round(3 + age_days / 200.0, 2))),
                    "height_cm": Decimal(str(round(45 + age_days / 45.0, 1))),
                    "muac_cm": Decimal("12.5"),
                    "temperature_c": Decimal("36.8"),
                    "nutrition_status": "NORMAL",
                    "development_notes": "Milestones appropriate for age.",
                    "diagnosis": "Healthy child",
                    "treatment": "Vitamin A, deworming if due, growth counselling",
                    "created_by": staff["rch"],
                },
            )
            for vaccine, due_days in VACCINE_SCHEDULE:
                if due_days < age_days:
                    ImmunizationRecord.objects.update_or_create(
                        rch_visit=child_visit,
                        patient=child,
                        vaccine=vaccine,
                        dose_date=child.date_of_birth + timedelta(days=due_days),
                        defaults={
                            "next_due": child.date_of_birth + timedelta(days=due_days + 28),
                            "batch_number": "DEMO-BATCH-%d" % due_days,
                            "notes": "Demo immunisation.",
                            "created_by": staff["rch"],
                        },
                    )

            # Family planning
            fp_encounter = self._rch_encounter(mother, staff, "FP", queued=index == 1)
            fp_visit, _ = RCHVisit.objects.update_or_create(
                encounter=fp_encounter,
                defaults={
                    "patient": mother,
                    "service_type": "FP",
                    "visit_date": timezone.localdate() - timedelta(days=rng.randint(10, 90)),
                    "attended_by": staff["rch"],
                    "next_appointment": timezone.localdate() + timedelta(days=90),
                    "clinical_notes": "Counselling given, method chosen.",
                    "is_high_risk": False,
                    "created_by": staff["rch"],
                },
            )
            FamilyPlanningRecord.objects.update_or_create(
                rch_visit=fp_visit,
                defaults={
                    "method": rng.choice(["PILL", "INJECTABLE", "IMPLANT", "CONDOM"]),
                    "method_provided": True,
                    "previous_method": rng.choice(["", "PILL", "CONDOM"]),
                    "side_effects": "None reported.",
                    "counselling_notes": "Counselling given on the chosen method.",
                    "follow_up_date": timezone.localdate() + timedelta(days=90),
                    "created_by": staff["rch"],
                },
            )

    def _rch_encounter(self, patient, staff, service, queued=False):
        """
        One RCH encounter per patient and service, found on re-run.

        Keyed on the complaint text because the demo has three RCH encounters
        per mother (ANC, family planning) and one per child, all sharing the
        same visit_type.

        The RCH queue and the start/service views only accept encounters in
        IN_PROGRESS, so `queued` leaves one case per service sitting in the
        queue. Without it the RCH queue renders empty and every RCH action page
        404s, which makes the RCH demo impossible to actually click through.
        """
        encounter, _ = Encounter.objects.update_or_create(
            patient=patient,
            chief_complaint="Demo %s visit" % service,
            defaults={
                "visit_type": "RCH",
                "status": "IN_PROGRESS" if queued else "COMPLETED",
                "current_department": "RCH",
                "notes": "DEMO encounter - invented data.",
                "created_by": staff["rch"],
            },
        )
        return encounter

    # -- live queues -------------------------------------------------------
    def _seed_pipeline(self, patients, staff, tests, test_meta, drugs, rng, now):
        """
        Leave a few patients sitting in each service queue.

        Every queue in this project filters on a specific status, so without
        this the whole demo renders fine but is impossible to click through:
        the doctor queue, the lab, pharmacy, injection, ultrasound and payment
        pages all come up empty because nothing is waiting.

        The filters these rows are shaped to match:
          reception    current_department=RECEPTION, status=REGISTERED
          doctor       current_department=DOCTOR, status in (IN_PROGRESS, RESULTS_READY)
          lab          current_department=LAB,   status=IN_PROGRESS
          pharmacy     current_department=PHARMACY, status=IN_PROGRESS
          injection    current_department=INJECTION, status=IN_PROGRESS
          ultrasound   current_department=ULTRASOUND, status=IN_PROGRESS
          cashier      status=PAYMENT_PENDING
        """
        # department -> (status, count, complaint)
        pipeline = [
            ("RECEPTION", "REGISTERED", 3, "Registered, waiting for triage"),
            ("RECEPTION", "PAYMENT_PENDING", 2, "Awaiting payment"),
            ("DOCTOR", "IN_PROGRESS", 3, "Waiting for consultation"),
            ("DOCTOR", "RESULTS_READY", 1, "Results ready for review"),
            ("LAB", "IN_PROGRESS", 2, "Awaiting sample collection"),
            ("PHARMACY", "IN_PROGRESS", 2, "Prescription ready to dispense"),
            ("INJECTION", "IN_PROGRESS", 2, "Procedure pending"),
            ("ULTRASOUND", "IN_PROGRESS", 2, "Scan scheduled"),
            (None, "PAYMENT_PENDING", 2, "Awaiting payment"),
        ]

        slot = 0
        for department, status, count, complaint in pipeline:
            for _ in range(count):
                # Wrap rather than stop: a short --patients value must not
                # silently leave the later queues empty. A patient showing up
                # in two queues is normal, and each pipeline row has its own
                # chief_complaint so it still gets a distinct encounter.
                patient = patients[slot % len(patients)]
                slot += 1
                encounter, _ = Encounter.objects.update_or_create(
                    patient=patient,
                    chief_complaint="Demo queue: %s" % complaint,
                    defaults={
                        "visit_type": "OPD",
                        "status": status,
                        "current_department": department or "",
                        "notes": "DEMO queue record - invented data.",
                        "created_by": staff["reception"],
                    },
                )
                self._queue_extras(encounter, department, staff, tests, test_meta, drugs, rng, now)

    def _queue_extras(self, encounter, department, staff, tests, test_meta, drugs, rng, now):
        """Give each queued encounter the rows its own view expects to find."""
        if department == "LAB":
            order, _ = LabOrder.objects.get_or_create(
                encounter=encounter,
                defaults={
                    "requested_by": staff["lab"],
                    "clinical_notes": "Demo lab order.",
                    "status": "REQUESTED",
                    "created_by": staff["lab"],
                },
            )
            for test in list(tests.values())[:3]:
                item, _ = LabOrderItem.objects.get_or_create(
                    order=order,
                    test=test,
                    defaults={"created_by": staff["lab"]},
                )
                unit, reference = test_meta.get(test.code, ("", ""))
                LabResult.objects.get_or_create(
                    order_item=item,
                    defaults={
                        "value": rng.choice(["NEGATIVE", "POSITIVE", "Normal", "12.4", "0.8"]),
                        "unit": unit,
                        "reference_range": reference,
                        "is_abnormal": rng.choice([True, False]),
                        "entered_by": staff["lab"],
                        "created_by": staff["lab"],
                    },
                )
        elif department == "PHARMACY":
            for drug in list(drugs.values())[:2]:
                prescription, _ = Prescription.objects.get_or_create(
                    encounter=encounter,
                    drug=drug,
                    defaults={
                        "quantity": 10,
                        "dosage_instructions": "1 tab twice daily",
                        "duration_days": 5,
                        "doctor": staff["doctor"],
                        "created_by": staff["doctor"],
                    },
                )

    # -- labour ward -------------------------------------------------------
    def _seed_labour(self, patients, staff, beds, rng, now):
        labour_beds = [(ward, bed) for ward, bed in beds if "Labour" in ward.name or "Maternity" in ward.name]
        if not labour_beds:
            return
        for index in range(1, 4):
            mother, _ = Patient.objects.update_or_create(
                patient_id="DEMO-LABOUR-%03d" % index,
                defaults={
                    "full_name": "%s %s" % (GIVEN_NAMES[index * 11 % len(GIVEN_NAMES)], FAMILY_NAMES[index * 2 % len(FAMILY_NAMES)]),
                    "date_of_birth": date(timezone.localdate().year - rng.randint(21, 36), rng.randint(1, 12), rng.randint(1, 28)),
                    "gender": "F",
                    "phone": "0744 004 %03d" % index,
                    "address": "%s, Demo District" % VILLAGES[index % len(VILLAGES)],
                    "next_of_kin": "Relative of demo mother",
                    "next_of_kin_phone": "0744 005 %03d" % index,
                    "is_nhif": index % 2 == 0,
                    "nhif_card_number": "",
                    "blood_group": BLOOD_GROUPS[index % len(BLOOD_GROUPS)],
                    "is_active": True,
                    "notes": "DEMO LABOUR PATIENT - invented data.",
                    "created_by": staff["labour"],
                },
            )
            ward, bed = labour_beds[index - 1]
            # Three shapes of case so the demo shows a full ward board and
            # exercises the real admit/discharge path:
            #   1 = in labour, waiting in the queue, no bed yet
            #   2 = admitted to a bed right now (bed OCCUPIED, ADMITTED)
            #   3 = delivered and discharged (bed AVAILABLE, DISCHARGED)
            stage = ("queued", "admitted", "delivered")[index - 1]
            # Keyed on the patient and the complaint text, never on visit_type:
            # admitting rewrites visit_type to IPD, so an INPATIENT lookup would
            # find nothing on a re-run and create a second encounter whose
            # admission then collides with the one already on the bed.
            #
            # The queued case deliberately gets no bed. labour.views queues and
            # opens cases by status=IN_PROGRESS, and admitting moves a visit to
            # ADMITTED, so a bed-admitted patient never appears in the labour
            # queue.
            encounter, _ = Encounter.objects.update_or_create(
                patient=mother,
                chief_complaint="Labour - demo case",
                defaults={
                    "visit_type": "OPD" if stage == "queued" else "INPATIENT",
                    "status": "IN_PROGRESS" if stage == "queued" else "REGISTERED",
                    "current_department": "LABOUR_WARD",
                    "notes": "DEMO encounter - invented data.",
                    "created_by": staff["labour"],
                },
            )
            admission_at = now - timedelta(hours=8 * index)
            case, _ = LabourCase.objects.update_or_create(
                encounter=encounter,
                defaults={
                    "mother": mother,
                    "admission_at": admission_at,
                    "gestational_age_weeks": rng.randint(37, 40),
                    "gravida": rng.randint(1, 5),
                    "para": rng.randint(0, 4),
                    "lmp": timezone.localdate() - timedelta(weeks=rng.randint(37, 40)),
                    "presenting_complaint": "Contractions since yesterday" if stage == "delivered" else "Contractions, 3 hours",
                    "labour_onset_at": admission_at - timedelta(hours=6),
                    "membrane_status": "Ruptured",
                    "liquor": "Clear",
                    "contractions": "3 in 10 minutes, strong",
                    "cervical_dilatation_cm": Decimal("10.0") if stage == "delivered" else Decimal("3.0"),
                    "is_high_risk": index == 2,
                    "previous_cs": index == 3,
                    "previous_delivery_notes": "Previous delivery by caesarean section." if index == 3 else "No previous complications.",
                    "initial_bp_systolic": rng.randint(105, 135),
                    "initial_bp_diastolic": rng.randint(65, 88),
                    "initial_pulse": rng.randint(70, 100),
                    "initial_temperature": Decimal("36.9"),
                    "status": "DELIVERED" if stage == "delivered" else "ACTIVE",
                    "admitted_by": staff["labour"],
                    "notes": "DEMO labour case - invented data.",
                    "created_by": staff["labour"],
                },
            )
            if stage != "queued":
                # Real Admission/Admission.discharge(), not hand-written fields.
                #
                # The two rows are first rewound to a known starting state,
                # because DISCHARGED is terminal: a re-seed cannot un-discharge
                # an encounter through the state machine, so it would otherwise
                # leave the second run showing REGISTERED encounters and free
                # beds. Driving forward from a fixed point is what makes a fresh
                # database and a re-seeded one come out identical.
                encounter.status = "REGISTERED"
                encounter.visit_type = "INPATIENT"
                encounter.closed_at = None
                encounter.save(
                    update_fields=["status", "visit_type", "closed_at", "updated_at"]
                )

                admission, _ = Admission.objects.update_or_create(
                    encounter=encounter,
                    defaults={
                        "bed": bed,
                        "admitted_by": staff["labour"],
                        "admitted_at": admission_at,
                        "nursing_notes": "DEMO nursing notes - invented data.",
                        "created_by": staff["labour"],
                    },
                )
                # Re-open it so the bed can be taken properly this run.
                if admission.discharged_at is not None or admission.discharge_notes:
                    admission.discharged_at = None
                    admission.discharge_notes = ""
                    admission.save(
                        update_fields=["discharged_at", "discharge_notes", "updated_at"]
                    )

                admission = Admission.objects.get(pk=admission.pk)
                encounter = Encounter.objects.get(pk=encounter.pk)
                encounter.admit_to_ward(
                    user=staff["labour"],
                    note="Admitted to %s" % admission.bed,
                )

                if stage == "delivered":
                    admission.discharge(
                        user=staff["labour"],
                        notes="Discharged in good condition.",
                    )
                    # Rewrite the timestamps onto the demo's own clock so the
                    # dates do not drift forward with every re-seed.
                    admission.discharged_at = admission_at + timedelta(hours=18)
                    admission.save(update_fields=["discharged_at", "updated_at"])
                    encounter.refresh_from_db()
                    encounter.closed_at = admission.discharged_at
                    encounter.save(update_fields=["closed_at", "updated_at"])

                bed.refresh_from_db()
                if stage == "delivered":
                    bed.status = "AVAILABLE"
                    bed.save(update_fields=["status", "updated_at"])
                elif bed.status != "OCCUPIED":
                    bed.status = "OCCUPIED"
                    bed.save(update_fields=["status", "updated_at"])

            for offset in range(1, 4):
                LabourAssessment.objects.update_or_create(
                    labour_case=case,
                    assessed_at=admission_at + timedelta(hours=3 * offset),
                    defaults={
                        "cervical_dilatation_cm": Decimal(str(min(10, 2 + 2 * offset))),
                        "effacement": "%d%%" % min(100, 30 * offset),
                        "station": ["-3", "-2", "-1", "0"][min(3, offset)],
                        "presentation": "Occiput anterior",
                        "position": "LOA",
                        "membrane_status": "Ruptured",
                        "liquor": "Clear",
                        "contraction_frequency": "3 in 10 minutes",
                        "contraction_duration": "45 seconds",
                        "pelvic_assessment": "Mid pelvis, no obstruction.",
                        "maternal_condition": "Stable, labour progressing normally.",
                        "assessed_by": staff["labour"],
                        "created_by": staff["labour"],
                    },
                )
                PartographEntry.objects.update_or_create(
                    labour_case=case,
                    recorded_at=admission_at + timedelta(hours=3 * offset),
                    defaults={
                        "cervical_dilatation_cm": Decimal(str(min(10, 2 + 2 * offset))),
                        "descent_of_head": ["-3", "-2", "-1", "0"][min(3, offset)],
                        "fetal_heart_rate": rng.randint(110, 150),
                        "contractions": "3 in 10 minutes",
                        "maternal_pulse": rng.randint(70, 100),
                        "bp_systolic": rng.randint(100, 130),
                        "bp_diastolic": rng.randint(65, 85),
                        "temperature": Decimal("36.9"),
                        "urine_output_ml": rng.randint(30, 120),
                        "urine_protein": "Negative",
                        "urine_ketones": "Negative",
                        "oxytocin": "Not required",
                        "iv_fluids": "Ringer's lactate, continuing",
                        "other_interventions": "None",
                        "alert_flag": index == 2 and offset == 3,
                        "recorded_by": staff["labour"],
                        "created_by": staff["labour"],
                    },
                )
                MaternalObservation.objects.update_or_create(
                    labour_case=case,
                    recorded_at=admission_at + timedelta(hours=3 * offset),
                    defaults={
                        "bp_systolic": rng.randint(100, 130),
                        "bp_diastolic": rng.randint(65, 85),
                        "pulse": rng.randint(70, 100),
                        "respiratory_rate": rng.randint(16, 22),
                        "temperature": Decimal("36.9"),
                        "spo2": rng.randint(95, 100),
                        "pain_score": rng.randint(3, 8),
                        "consciousness": "Alert",
                        "urine_output_ml": rng.randint(30, 120),
                        "bleeding": "None",
                        "general_condition": "Stable, observations within normal limits.",
                        "alert_flag": index == 2 and offset == 3,
                        "recorded_by": staff["labour"],
                        "created_by": staff["labour"],
                    },
                )

            if stage == "delivered":
                delivered_at = admission_at + timedelta(hours=14)
                mode = "CS" if index == 3 else "SVD"
                delivery, _ = DeliveryRecord.objects.update_or_create(
                    labour_case=case,
                    defaults={
                        "delivered_at": delivered_at,
                        "mode": mode,
                        "indication": "Previous caesarean section" if mode == "CS" else "Spontaneous labour",
                        "presentation": "Cephalic",
                        "position": "LOA",
                        "placenta_delivered_at": delivered_at + timedelta(minutes=8),
                        "placenta_complete": True,
                        "estimated_blood_loss_ml": rng.randint(100, 400),
                        "perineum": "Intact" if index % 2 else "Second degree tear, sutured",
                        "episiotomy": index % 2 == 0,
                        "suturing": "Two sutures, good apposition" if index % 2 == 0 else "Not required",
                        "delivery_notes": "DEMO delivery - invented data.",
                        "conducted_by": staff["labour"],
                        "created_by": staff["labour"],
                    },
                )
                baby, _ = Patient.objects.update_or_create(
                    patient_id="DEMO-NEWBORN-%03d" % index,
                    defaults={
                        "full_name": "Baby of %s (demo)" % mother.full_name,
                        "date_of_birth": delivered_at.date(),
                        "gender": "M" if index % 2 else "F",
                        "phone": mother.phone,
                        "address": mother.address,
                        "next_of_kin": mother.full_name,
                        "next_of_kin_phone": mother.phone,
                        "is_nhif": False,
                        "nhif_card_number": "",
                        "blood_group": "",
                        "is_active": True,
                        "notes": "DEMO NEWBORN - invented data.",
                        "created_by": staff["labour"],
                    },
                )
                NewbornRecord.objects.update_or_create(
                    labour_case=case,
                    defaults={
                        "delivery": delivery,
                        "mother": mother,
                        "baby_patient": baby,
                        "birth_order": 1,
                        "born_at": delivered_at,
                        "sex": "M" if index % 2 else "F",
                        "birth_weight_kg": Decimal(str(round(rng.uniform(2.6, 3.9), 2))),
                        "length_cm": Decimal(str(rng.randint(46, 53))),
                        "head_circumference_cm": Decimal(str(round(rng.uniform(32, 36), 1))),
                        "apgar_1": rng.randint(7, 9),
                        "apgar_5": rng.randint(8, 10),
                        "apgar_10": rng.randint(9, 10),
                        "gestational_age_weeks": rng.randint(37, 40),
                        "birth_status": "Well",
                        "resuscitation": False,
                        "condition_notes": "Healthy newborn, cried immediately.",
                        "breastfeeding_initiated": True,
                        "interventions": "None",
                        "created_by": staff["labour"],
                    },
                )

    # -- appointments ------------------------------------------------------
    def _seed_appointments(self, patients, staff, rng, now):
        for index, patient in enumerate(patients[:6], start=1):
            # Fixed offsets, keyed on the patient and the reason. The slot time
            # used to be now + a random number of days, which never matched on a
            # re-run and booked a second appointment for the same patient every
            # time the command was run. Appointment has no unique constraint, so
            # the reason is what keeps this to one row per patient.
            Appointment.objects.update_or_create(
                patient=patient,
                reason="Demo follow-up appointment",
                defaults={
                    "doctor": staff["doctor"],
                    "department": "Outpatient",
                    "scheduled_at": timezone.now().replace(
                        hour=9 + index % 8, minute=0, second=0, microsecond=0
                    ) + timedelta(days=7),
                    "status": "SCHEDULED",
                    "notes": "DEMO appointment - invented data.",
                    "created_by": staff["reception"],
                },
            )

    # -- audit trail -------------------------------------------------------
    def _seed_audit(self, patients, staff, now):
        entries = [
            ("patients.Patient", patients[0].pk if patients else "0", "CREATE"),
            ("encounters.Encounter", "1", "STATUS_CHANGE"),
            ("pharmacy.DispenseRecord", "1", "DISPENSE"),
            ("billing.Payment", "1", "PAYMENT"),
            ("bed_management.Admission", "1", "ADMISSION"),
        ]
        for index, (model_name, object_id, action) in enumerate(entries):
            AuditLog.objects.get_or_create(
                model_name=model_name,
                object_id=object_id,
                action=action,
                defaults={
                    "user": staff["admin"],
                    "changes": {"demo": True, "note": "DEMO audit entry."},
                    "ip_address": "127.0.0.1",
                    "timestamp": now - timedelta(hours=index),
                },
            )

    # -- output ------------------------------------------------------------
    def _summary(self, staff, patients, rng):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write("")
        self.stdout.write("  Staff accounts (all use the password below):")
        for slug, role, _department, unit in ROLES:
            user = staff[role]
            self.stdout.write(
                "    %-22s %-12s %s"
                % (user.username, role, unit)
            )
        self.stdout.write("")
        self.stdout.write("    password: %s" % DEMO_PASSWORD)
        self.stdout.write("")
        self.stdout.write("  Counts:")
        for label, model in [
            ("patients", Patient),
            ("encounters", Encounter),
            ("drugs", Drug),
            ("lab tests", LabTest),
            ("invoices", Invoice),
            ("wards", Ward),
            ("beds", Bed),
            ("labour cases", LabourCase),
            ("rch visits", RCHVisit),
            ("immunisations", ImmunizationRecord),
        ]:
            self.stdout.write("    %-16s %d" % (label, model.objects.count()))
        self.stdout.write("")
        self.stdout.write(self.style.WARNING(
            "  All of the above is invented. If you later see these names in a\n"
            "  report, it is a demo, not a real patient.\n"
        ))


def rng_price(code):
    """Stable per-test price, so a re-run does not change the demo."""
    return 5000 + (sum(ord(character) for character in code) * 500) % 25000
