"""
Tests for the bed workflow.

The admit/discharge path used to be broken: Admission.save() wrote an
encounter status the state machine did not define, and discharge() then
raised, having already freed the bed and stamped discharged_at. A second
patient could then be admitted to that bed with no error at all.

See docs/KNOWN_ISSUES.md (DISCHARGE_BUG). The fix puts the inpatient statuses
back on the encounter state machine and makes the bed bookkeeping atomic, so
these tests pin the corrected behaviour.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import StaffProfile
from bed_management.models import Admission, Bed, Ward
from encounters.models import Encounter
from patients.models import Patient


class BedWorkflowTestBase(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="ward.clerk", password="test-password-ward-clerk"
        )
        # accounts.signals creates the profile on user creation, so only the
        # role needs setting here.
        StaffProfile.objects.filter(user=user).update(role="ADMIN")
        self.user = user

        self.ward = Ward.objects.create(
            name="Ward Test",
            description="Created by the bed workflow tests.",
            capacity=4,
            is_active=True,
            created_by=user,
        )
        self.bed = Bed.objects.create(
            ward=self.ward,
            bed_number="W-01",
            status="AVAILABLE",
            created_by=user,
        )

    def new_bed(self, number):
        return Bed.objects.create(
            ward=self.ward,
            bed_number=number,
            status="AVAILABLE",
            created_by=self.user,
        )

    def make_patient(self, patient_id, name, gender="F"):
        return Patient.objects.create(
            patient_id=patient_id,
            full_name=name,
            gender=gender,
            is_active=True,
            created_by=self.user,
        )

    def make_encounter(self, patient, status="IN_PROGRESS", complaint="Ward test"):
        return Encounter.objects.create(
            patient=patient,
            visit_type="OPD",
            status=status,
            current_department="DOCTOR",
            chief_complaint=complaint,
            created_by=self.user,
        )

    def admit(self, patient=None, status="IN_PROGRESS", bed=None, complaint="Ward test"):
        patient = patient or self.make_patient("WARD-0001", "First Patient")
        bed = bed or self.bed
        encounter = self.make_encounter(patient, status=status, complaint=complaint)
        admission = Admission.objects.create(
            encounter=encounter,
            bed=bed,
            admitted_by=self.user,
            created_by=self.user,
        )
        return encounter, admission


class InpatientStatusIsPartOfTheStateMachineTests(BedWorkflowTestBase):
    """The three statuses bed_management needs must exist on the encounter."""

    def test_inpatient_statuses_are_valid_choices(self):
        choices = [choice[0] for choice in Encounter.STATUS_CHOICES]
        for status in ("ADMITTED", "IN_WARD", "DISCHARGED"):
            self.assertIn(status, choices)

    def test_every_valid_transition_target_is_a_real_choice(self):
        choices = {choice[0] for choice in Encounter.STATUS_CHOICES}
        for source, targets in Encounter.VALID_TRANSITIONS.items():
            self.assertIn(source, choices, "%s is not a real status" % source)
            for target in targets:
                self.assertIn(
                    target,
                    choices,
                    "%s -> %s targets a status that is not a choice" % (source, target),
                )

    def test_every_status_is_reachable_from_registered(self):
        """No status may be stranded with no way of being entered."""
        seen = {"REGISTERED"}
        frontier = ["REGISTERED"]
        while frontier:
            current = frontier.pop()
            for target in Encounter.VALID_TRANSITIONS.get(current, set()):
                if target not in seen:
                    seen.add(target)
                    frontier.append(target)
        for status in [choice[0] for choice in Encounter.STATUS_CHOICES]:
            self.assertIn(status, seen, "%s cannot be reached from REGISTERED" % status)


class AdmissionTests(BedWorkflowTestBase):
    def test_admission_marks_bed_occupied(self):
        self.admit()
        self.bed.refresh_from_db()
        self.assertEqual(self.bed.status, "OCCUPIED")

    def test_admission_moves_encounter_to_admitted(self):
        encounter, _ = self.admit()
        encounter.refresh_from_db()
        self.assertEqual(encounter.status, "ADMITTED")
        self.assertIn(
            encounter.status, [choice[0] for choice in Encounter.STATUS_CHOICES]
        )

    def test_admission_sets_visit_type_to_ipd(self):
        encounter, _ = self.admit()
        encounter.refresh_from_db()
        self.assertEqual(encounter.visit_type, "IPD")
        self.assertTrue(encounter.is_inpatient())

    def test_admission_reopens_a_closed_encounter(self):
        """Admitting a completed outpatient visit must clear closed_at."""
        encounter, _ = self.admit(status="COMPLETED")
        encounter.refresh_from_db()
        self.assertIsNone(encounter.closed_at, "an admitted patient is not closed")

    def test_admission_writes_a_visit_log(self):
        encounter, _ = self.admit()
        self.assertTrue(
            encounter.logs.filter(to_status="ADMITTED").exists(),
            "no VisitLog recorded for the admission",
        )

    def test_admitting_from_each_plausible_status(self):
        """Admission must work from any state a patient can arrive in."""
        for index, status in enumerate(
            ["REGISTERED", "PAYMENT_PENDING", "IN_PROGRESS", "RESULTS_READY", "COMPLETED"],
            start=1,
        ):
            with self.subTest(status=status):
                bed = self.new_bed("W-1%d" % index)
                patient = self.make_patient(
                    "WARD-1%03d" % index, "Patient from %s" % status
                )
                encounter, admission = self.admit(
                    patient=patient, status=status, bed=bed,
                    complaint="from %s" % status,
                )
                encounter.refresh_from_db()
                self.assertEqual(encounter.status, "ADMITTED")
                self.assertIsNotNone(admission.discharged_at.__class__)  # sanity


class DischargeTests(BedWorkflowTestBase):
    def test_discharge_succeeds(self):
        _, admission = self.admit()
        admission.discharge(user=self.user, notes="Recovered, discharged.")
        admission.refresh_from_db()
        self.assertIsNotNone(admission.discharged_at)

    def test_discharge_frees_the_bed(self):
        _, admission = self.admit()
        admission.discharge(user=self.user, notes="Recovered")
        self.bed.refresh_from_db()
        self.assertEqual(self.bed.status, "AVAILABLE")

    def test_discharge_closes_the_encounter(self):
        encounter, admission = self.admit()
        admission.discharge(user=self.user, notes="Recovered")
        encounter.refresh_from_db()
        self.assertEqual(encounter.status, "DISCHARGED")
        self.assertIsNotNone(encounter.closed_at)
        self.assertNotIn(encounter.status, Encounter.INPATIENT_STATUSES)

    def test_discharged_visit_is_still_an_inpatient_visit(self):
        """Discharging ends the stay, it does not rewrite what the visit was."""
        encounter, admission = self.admit()
        admission.discharge(user=self.user, notes="Recovered")
        encounter.refresh_from_db()
        self.assertEqual(encounter.visit_type, "IPD")
        self.assertTrue(encounter.is_inpatient())
        self.assertFalse(Encounter.objects.open().filter(pk=encounter.pk).exists())

    def test_discharge_stores_the_notes(self):
        _, admission = self.admit()
        admission.discharge(user=self.user, notes="Condition stable.")
        admission.refresh_from_db()
        self.assertEqual(admission.discharge_notes, "Condition stable.")

    def test_discharge_writes_a_visit_log(self):
        encounter, admission = self.admit()
        admission.discharge(user=self.user, notes="Recovered")
        self.assertTrue(encounter.logs.filter(to_status="DISCHARGED").exists())

    def test_bed_can_be_reused_after_a_real_discharge(self):
        """The flow that used to be impossible: free the bed, then reuse it."""
        _, first = self.admit()
        first.discharge(user=self.user, notes="Recovered")

        self.bed.refresh_from_db()
        self.assertEqual(self.bed.status, "AVAILABLE")

        second_encounter, second_admission = self.admit(
            patient=self.make_patient("WARD-0002", "Second Patient", gender="M"),
            bed=self.bed,
            complaint="second stay",
        )
        self.bed.refresh_from_db()
        self.assertEqual(self.bed.status, "OCCUPIED")
        self.assertEqual(second_encounter.status, "ADMITTED")
        self.assertEqual(second_admission.bed_id, self.bed.pk)

    def test_double_discharge_is_refused(self):
        _, admission = self.admit()
        admission.discharge(user=self.user, notes="Recovered")
        with self.assertRaises(ValidationError):
            admission.discharge(user=self.user, notes="Again")

    def test_discharge_refused_when_visit_is_not_in_a_ward(self):
        """A discharge can no longer be half-written: nothing is saved."""
        patient = self.make_patient("WARD-0005", "Not Admitted")
        encounter = self.make_encounter(patient, status="IN_PROGRESS")
        admission = Admission.objects.create(
            encounter=encounter,
            bed=self.bed,
            admitted_by=self.user,
            created_by=self.user,
        )
        # Move the visit out of the ward behind the admission's back, which is
        # the situation the old code left behind.
        encounter.status = "COMPLETED"
        encounter.save(update_fields=["status", "updated_at"])

        with self.assertRaises(ValidationError):
            admission.discharge(user=self.user, notes="Should fail")

        admission.refresh_from_db()
        self.bed.refresh_from_db()
        encounter.refresh_from_db()

        self.assertIsNone(
            admission.discharged_at,
            "discharged_at was stamped even though the discharge failed",
        )
        self.assertEqual(
            self.bed.status, "OCCUPIED", "the bed was freed by a failed discharge"
        )
        self.assertEqual(encounter.status, "COMPLETED")


class InWardTests(BedWorkflowTestBase):
    def test_admitted_visit_can_move_into_the_ward(self):
        encounter, _ = self.admit()
        encounter.transition_to("IN_WARD", user=self.user, note="Moved into the ward")
        encounter.refresh_from_db()
        self.assertEqual(encounter.status, "IN_WARD")
        self.assertIsNone(encounter.closed_at)

    def test_visit_in_the_ward_can_be_discharged(self):
        encounter, admission = self.admit()
        encounter.transition_to("IN_WARD", user=self.user)
        admission.discharge(user=self.user, notes="Recovered")
        encounter.refresh_from_db()
        self.bed.refresh_from_db()
        self.assertEqual(encounter.status, "DISCHARGED")
        self.assertEqual(self.bed.status, "AVAILABLE")

    def test_cancelled_visit_cannot_be_admitted(self):
        """CANCELLED is still terminal."""
        encounter, _ = self.admit(status="REGISTERED")
        encounter.transition_to("CANCELLED", user=self.user, note="Cancelled")
        self.assertFalse(encounter.can_transition_to("ADMITTED"))
        with self.assertRaises(ValidationError):
            encounter.admit_to_ward(user=self.user)

    def test_discharged_visit_cannot_be_readmitted(self):
        _, admission = self.admit()
        admission.discharge(user=self.user, notes="Recovered")
        encounter = admission.encounter
        self.assertFalse(encounter.can_transition_to("ADMITTED"))
        self.assertFalse(encounter.can_transition_to("IN_WARD"))


class BedAvailabilityTests(BedWorkflowTestBase):
    def test_cannot_admit_second_patient_while_admission_is_open(self):
        self.admit()
        second = self.make_encounter(
            self.make_patient("WARD-0003", "Third Patient"), complaint="second claim"
        )
        with self.assertRaises(ValidationError) as caught:
            Admission.objects.create(
                encounter=second, bed=self.bed, admitted_by=self.user, created_by=self.user
            )
        self.assertIn("open admission", str(caught.exception))

    def test_cannot_admit_to_occupied_bed_that_has_no_admission_row(self):
        self.bed.status = "OCCUPIED"
        self.bed.save(update_fields=["status"])
        second = self.make_encounter(
            self.make_patient("WARD-0004", "Fourth Patient"), complaint="no row"
        )
        with self.assertRaises(ValidationError) as caught:
            Admission.objects.create(
                encounter=second, bed=self.bed, admitted_by=self.user, created_by=self.user
            )
        message = str(caught.exception)
        self.assertIn("not available", message)
        self.assertIn("OCCUPIED", message)


class WardCountTests(BedWorkflowTestBase):
    def test_ward_counts_track_the_beds(self):
        self.admit()
        self.ward.refresh_from_db()
        self.assertEqual(self.ward.occupied_count, 1)
        self.assertEqual(self.ward.available_count, 0)
