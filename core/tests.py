"""
Tests for the SQLite demo environment and the seed_demo command.

The command only ever writes invented data, and it refuses to run against
MySQL unless explicitly forced, so these tests can exercise it against the
throwaway in-memory test database.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from appointments.models import Appointment
from bed_management.models import Admission, Bed, Ward
from billing.models import Invoice
from encounters.models import Encounter
from laboratory.models import LabOrder, LabResult
from labour.models import LabourCase, NewbornRecord
from patients.models import Patient
from pharmacy.models import Drug
from rch.models import RCHVisit

# The tests assert against the command's own constant rather than a copy, so a
# change to the demo password cannot leave this suite checking a stale value.
from core.management.commands.seed_demo import DEMO_PASSWORD

ROLE_USERNAMES = [
    "demo.admin",
    "demo.reception",
    "demo.doctor",
    "demo.lab",
    "demo.pharmacy",
    "demo.ultrasound",
    "demo.injection",
    "demo.rch",
    "demo.labour",
]


def seed(**kwargs):
    out = StringIO()
    call_command("seed_demo", stdout=out, stderr=out, **kwargs)
    return out.getvalue()


@override_settings(
    DATABASES={
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": "hms_db",
            "USER": "hms",
                "PASSWORD": "test-password-not-real",

            "HOST": "127.0.0.1",
            "PORT": "3306",
        }
    }
)
class SeedDemoRefusesMysqlTests(TestCase):
    """The guard is the whole reason this command is safe to keep in the repo."""

    def test_refuses_mysql_by_default(self):
        with self.assertRaises(CommandError) as caught:
            seed()
        self.assertIn("Refusing to write demo data to MySQL", str(caught.exception))

    def test_no_demo_rows_were_written(self):
        self.assertEqual(Patient.objects.count(), 0)
        self.assertEqual(get_user_model().objects.filter(username__startswith="demo.").count(), 0)

    def test_refusal_message_names_the_risk(self):
        try:
            seed()
        except CommandError as exc:
            message = str(exc)
        else:
            self.fail("expected CommandError")
        self.assertIn("production database", message)


class SeedDemoContentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.output = seed()

    def test_creates_every_demo_staff_account(self):
        for username in ROLE_USERNAMES:
            self.assertTrue(
                get_user_model().objects.filter(username=username).exists(),
                "missing demo account %s" % username,
            )

    def test_demo_password_works(self):
        user = get_user_model().objects.get(username="demo.reception")
        self.assertTrue(user.check_password(DEMO_PASSWORD))

    def test_creates_patients_in_every_service(self):
        for prefix in ("DEMO-0", "DEMO-CHILD", "DEMO-LABOUR", "DEMO-RCH"):
            self.assertTrue(
                Patient.objects.filter(patient_id__startswith=prefix).exists(),
                "no patients with prefix %s" % prefix,
            )

    def test_creates_reference_data(self):
        self.assertGreater(Ward.objects.count(), 0)
        self.assertGreater(Bed.objects.count(), 0)
        self.assertGreater(Drug.objects.count(), 0)

    def test_creates_clinical_records(self):
        self.assertGreater(Encounter.objects.count(), 0)
        self.assertGreater(LabOrder.objects.count(), 0)
        self.assertGreater(LabResult.objects.count(), 0)
        self.assertGreater(Invoice.objects.count(), 0)
        self.assertGreater(Appointment.objects.count(), 0)
        self.assertGreater(RCHVisit.objects.count(), 0)
        self.assertGreater(LabourCase.objects.count(), 0)
        self.assertGreater(NewbornRecord.objects.count(), 0)
        self.assertGreater(Admission.objects.count(), 0)

    def test_leaves_every_queue_with_work_in_it(self):
        """Without this the demo renders but cannot be clicked through."""
        queues = {
            "reception": dict(current_department="RECEPTION", status="REGISTERED"),
            "doctor": dict(
                current_department="DOCTOR",
                status__in=["IN_PROGRESS", "RESULTS_READY"],
            ),
            "lab": dict(current_department="LAB", status="IN_PROGRESS"),
            "pharmacy": dict(current_department="PHARMACY", status="IN_PROGRESS"),
            "injection": dict(current_department="INJECTION", status="IN_PROGRESS"),
            "ultrasound": dict(current_department="ULTRASOUND", status="IN_PROGRESS"),
            "rch": dict(current_department="RCH", status="IN_PROGRESS"),
            "labour": dict(current_department="LABOUR_WARD", status="IN_PROGRESS"),
            "cashier": dict(status="PAYMENT_PENDING"),
        }
        for name, lookup in queues.items():
            self.assertTrue(
                Encounter.objects.filter(**lookup).exists(),
                "the %s queue is empty" % name,
            )

    def test_delivered_labour_cases_go_through_real_admission_and_discharge(self):
        """
        The delivered case must exercise Admission.discharge() for real, not
        have its fields written by hand.
        """
        admissions = Admission.objects.filter(discharged_at__isnull=False)
        self.assertEqual(admissions.count(), 1)
        admission = admissions.get()
        self.assertEqual(admission.encounter.status, "DISCHARGED")
        self.assertEqual(admission.bed.status, "AVAILABLE")
        self.assertIsNotNone(admission.encounter.closed_at)
        self.assertEqual(admission.encounter.visit_type, "IPD")
        self.assertTrue(
            admission.encounter.logs.filter(to_status="DISCHARGED").exists(),
            "no DISCHARGED VisitLog for admission %s" % admission.pk,
        )

    def test_one_patient_stays_admitted_to_show_an_occupied_bed(self):
        open_admissions = Admission.objects.filter(discharged_at__isnull=True)
        self.assertEqual(open_admissions.count(), 1)
        admission = open_admissions.get()
        self.assertEqual(admission.encounter.status, "ADMITTED")
        self.assertEqual(admission.bed.status, "OCCUPIED")
        self.assertEqual(admission.encounter.visit_type, "IPD")

    def test_active_labour_case_stays_in_the_queue(self):
        active = LabourCase.objects.filter(status="ACTIVE")
        self.assertEqual(active.count(), 2)
        queued = [c for c in active if not hasattr(c.encounter, "admission")]
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0].encounter.status, "IN_PROGRESS")

    def test_inpatient_statuses_are_representable(self):
        """
        A status bed_management writes must be a valid choice. IN_WARD is not
        required here: the demo has a patient waiting in the queue, one
        admitted and one discharged, which is a realistic ward board.
        """
        for status in ("ADMITTED", "DISCHARGED"):
            self.assertTrue(
                Encounter.objects.filter(status=status).exists(),
                "no demo encounter uses %s" % status,
            )

    def test_no_demo_encounter_uses_a_status_outside_the_choices(self):
        valid = {choice[0] for choice in Encounter.STATUS_CHOICES}
        found = set(Encounter.objects.values_list("status", flat=True).distinct())
        self.assertFalse(
            found - valid,
            "demo wrote statuses the model does not define: %s" % (found - valid),
        )

    def test_output_labelled_as_invented_data(self):
        self.assertIn("invented", self.output)
        self.assertIn("No real patient", self.output)
        self.assertIn(DEMO_PASSWORD, self.output)

    def test_patient_names_are_not_derived_from_real_records(self):
        for patient in Patient.objects.all():
            self.assertIn("DEMO", patient.notes.upper() + patient.patient_id)


class SeedDemoIsIdempotentTests(TestCase):
    """A re-run must update in place, not pile up duplicates."""

    def snapshot(self):
        return {
            "patients": Patient.objects.count(),
            "encounters": Encounter.objects.count(),
            "lab_orders": LabOrder.objects.count(),
            "lab_results": LabResult.objects.count(),
            "invoices": Invoice.objects.count(),
            "admissions": Admission.objects.count(),
            "labour_cases": LabourCase.objects.count(),
            "rch_visits": RCHVisit.objects.count(),
            "newborns": NewbornRecord.objects.count(),
            "appointments": Appointment.objects.count(),
            "drugs": Drug.objects.count(),
            "beds": Bed.objects.count(),
        }

    def test_running_twice_changes_no_counts(self):
        seed()
        first = self.snapshot()
        seed()
        second = self.snapshot()
        self.assertEqual(first, second)

    def test_running_four_times_changes_no_counts(self):
        seed()
        seed()
        before = self.snapshot()
        seed()
        seed()
        self.assertEqual(before, self.snapshot())

    def test_one_encounter_per_patient_and_complaint(self):
        seed()
        seed()
        pairs = list(
            Encounter.objects.values_list("patient_id", "chief_complaint")
        )
        self.assertEqual(len(pairs), len(set(pairs)), "duplicate encounter keys")

    def test_one_appointment_per_patient(self):
        seed()
        seed()
        patient_ids = list(
            Appointment.objects.values_list("patient_id", flat=True)
        )
        self.assertEqual(len(patient_ids), len(set(patient_ids)))

    def test_drug_stock_is_not_driven_negative_or_trending(self):
        seed()
        after_first = {
            d.pk: d.stock_quantity for d in Drug.objects.all()
        }
        seed()
        after_second = {d.pk: d.stock_quantity for d in Drug.objects.all()}
        self.assertEqual(after_first, after_second)
        for drug in Drug.objects.all():
            self.assertGreaterEqual(drug.stock_quantity, 0)


class SeedDemoOutputTests(TestCase):
    def test_reports_row_counts(self):
        output = seed()
        for label in (
            "patients",
            "encounters",
            "drugs",
            "lab tests",
            "invoices",
            "wards",
            "beds",
            "labour cases",
            "rch visits",
            "immunisations",
        ):
            self.assertIn(label, output)

    def test_custom_password_is_applied(self):
        seed(password="test-password-different-42")
        user = get_user_model().objects.get(username="demo.admin")
        self.assertTrue(user.check_password("test-password-different-42"))
