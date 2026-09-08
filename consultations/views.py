"""
consultations/views.py
======================
Doctor consultation workspace:
- notes / diagnosis
- vitals (per visit)
- prescriptions (in-house stock check + external PDF)
- lab requests (catalog + optional manual/custom tests)
- ultrasound results (when patient returns RESULTS_READY from US)
- referrals
- finish → PAYMENT_PENDING + PHARMACY when any in-house Rx exists
- NHIF patients skip payment and go straight to Pharmacy
"""

import re

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.utils import timezone

from accounts.decorators import doctor_required
from encounters.models import Encounter, Vitals
from laboratory.models import LabTest, LabOrder, LabOrderItem
from .models import Consultation, Prescription
from .forms import ConsultationForm, PrescriptionForm


def _get_or_create_custom_lab_test(name, user):
    """
    Manual test name from doctor → LabTest (category OTHER).
    Reuses an existing test with the same name (case-insensitive).
    """
    name = (name or "").strip()[:150]
    if not name:
        return None

    existing = LabTest.objects.filter(name__iexact=name).first()
    if existing:
        return existing

    code_base = re.sub(r"[^A-Z0-9]+", "", name.upper())[:12] or "CUSTOM"
    code = f"C-{code_base}"[:30]
    base = code
    n = 1
    while LabTest.objects.filter(code=code).exists():
        code = f"{base}{n}"[:30]
        n += 1

    kwargs = {
        "code": code,
        "name": name,
        "category": "OTHER",
        "sample_type": "",
        "description": "Custom test requested by doctor",
        "is_active": True,
    }
    field_names = {f.name for f in LabTest._meta.get_fields()}
    if "created_by" in field_names:
        kwargs["created_by"] = user

    return LabTest.objects.create(**kwargs)


@login_required
@doctor_required
def consultation_queue(request):
    """Redirect to shared doctor queue."""
    return redirect("encounters:doctor_queue")


@login_required
@doctor_required
def conduct_consultation(request, encounter_id):
    """
    Main consultation screen.
    Allows IN_PROGRESS and RESULTS_READY visits assigned to DOCTOR.
    """
    encounter = get_object_or_404(
        Encounter.objects.select_related("patient"),
        pk=encounter_id,
    )

    allowed = (
        encounter.current_department == "DOCTOR"
        and encounter.status in ["IN_PROGRESS", "RESULTS_READY"]
    )
    if not allowed:
        messages.warning(request, "This patient is not available for consultation.")
        return redirect("encounters:doctor_queue")

    patient = encounter.patient
    latest_vitals = encounter.vitals.order_by("-recorded_at").first()

    consultation, _ = Consultation.objects.get_or_create(
        encounter=encounter,
        defaults={"doctor": request.user, "created_by": request.user},
    )

    prescriptions = (
        Prescription.objects.filter(encounter=encounter)
        .select_related("drug")
        .order_by("created_at")
    )
    lab_tests = LabTest.objects.filter(is_active=True).order_by("category", "name")
    lab_orders = (
        LabOrder.objects.filter(encounter=encounter, status="RELEASED")
        .prefetch_related("items__test", "items__result")
        .order_by("-released_at")
    )

    ultrasound_reports = encounter.ultrasound_reports.all().order_by("-created_at")

    has_external_rx = prescriptions.filter(
        source=Prescription.SOURCE_EXTERNAL
    ).exists()

    consultation_form = ConsultationForm(instance=consultation)
    prescription_form = PrescriptionForm()

    if request.method == "POST":
        action = request.POST.get("action")

        if encounter.status == "RESULTS_READY" and action in [
            "save_consultation",
            "save_vitals",
            "add_prescription",
            "request_lab",
            "refer",
            "finish_consultation",
        ]:
            encounter.status = "IN_PROGRESS"
            encounter.save(update_fields=["status", "updated_at"])
            encounter.refresh_from_db()

        # ----- Save notes -----
        if action == "save_consultation":
            consultation_form = ConsultationForm(request.POST, instance=consultation)
            if consultation_form.is_valid():
                obj = consultation_form.save(commit=False)
                obj.doctor = request.user
                obj.save()
                messages.success(request, "Consultation notes saved.")
            else:
                messages.error(request, "Please correct the consultation form.")
            return redirect(
                "consultations:conduct_consultation", encounter_id=encounter.pk
            )

        # ----- Record vitals (this visit) -----
        elif action == "save_vitals":
            def dec(name):
                v = request.POST.get(name)
                return v if v not in (None, "") else None

            bp = (request.POST.get("blood_pressure") or "").strip()
            notes = (request.POST.get("vitals_notes") or "").strip()
            pulse = dec("pulse")
            spo2 = dec("spo2")
            rr = dec("respiratory_rate")

            # Require at least one measurement
            if not any([
                dec("temperature_c"),
                bp,
                pulse,
                spo2,
                dec("weight_kg"),
                dec("height_cm"),
                rr,
            ]):
                messages.error(request, "Enter at least one vital sign.")
                return redirect(
                    "consultations:conduct_consultation", encounter_id=encounter.pk
                )

            Vitals.objects.create(
                encounter=encounter,
                temperature_c=dec("temperature_c"),
                blood_pressure=bp,
                pulse=int(pulse) if pulse else None,
                spo2=int(spo2) if spo2 else None,
                weight_kg=dec("weight_kg"),
                height_cm=dec("height_cm"),
                respiratory_rate=int(rr) if rr else None,
                notes=notes,
                recorded_at=timezone.now(),
                recorded_by=request.user,
            )
            messages.success(request, "Vitals recorded for this visit.")
            return redirect(
                "consultations:conduct_consultation", encounter_id=encounter.pk
            )

        # ----- Add prescription -----
        elif action == "add_prescription":
            prescription_form = PrescriptionForm(request.POST)
            if prescription_form.is_valid():
                rx = prescription_form.save(commit=False)
                rx.encounter = encounter
                rx.consultation = consultation
                rx.doctor = request.user
                rx.created_by = request.user

                raw = (request.POST.get("source") or "").strip().upper()
                if raw == Prescription.SOURCE_EXTERNAL:
                    rx.source = Prescription.SOURCE_EXTERNAL
                else:
                    rx.source = Prescription.SOURCE_IN_HOUSE

                rx.save()

                if rx.source == Prescription.SOURCE_EXTERNAL:
                    messages.success(
                        request,
                        f"{rx.drug.name} ×{rx.quantity} saved as EXTERNAL PDF. "
                        f"Use Print external Rx when ready.",
                    )
                else:
                    messages.success(
                        request,
                        f"{rx.drug.name} ×{rx.quantity} saved as IN-HOUSE. "
                        f"Will go to Payment Pending → Pharmacy on finish.",
                    )
            else:
                messages.error(request, "Could not add medicine.")
                for err in prescription_form.non_field_errors():
                    messages.error(request, err)
                for field, errs in prescription_form.errors.items():
                    for e in errs:
                        if field == "__all__":
                            messages.error(request, e)
                        else:
                            messages.error(request, f"{field}: {e}")
            return redirect(
                "consultations:conduct_consultation", encounter_id=encounter.pk
            )

        # ----- Lab request (catalog + optional custom) -----
        elif action == "request_lab":
            test_ids = request.POST.getlist("lab_tests")
            clinical_notes = request.POST.get("lab_clinical_notes", "").strip()
            custom_raw = (request.POST.get("custom_lab_tests") or "").strip()

            custom_names = []
            if custom_raw:
                for part in custom_raw.replace(",", "\n").splitlines():
                    name = part.strip()
                    if name:
                        custom_names.append(name)

            if not test_ids and not custom_names:
                messages.error(
                    request,
                    "Select at least one catalog test or enter a custom test name.",
                )
                return redirect(
                    "consultations:conduct_consultation", encounter_id=encounter.pk
                )

            consultation_form = ConsultationForm(request.POST, instance=consultation)
            if consultation_form.is_valid():
                obj = consultation_form.save(commit=False)
                obj.doctor = request.user
                obj.save()

            added = 0
            with transaction.atomic():
                order = LabOrder.objects.create(
                    encounter=encounter,
                    requested_by=request.user,
                    clinical_notes=clinical_notes,
                    created_by=request.user,
                    status="REQUESTED",
                )

                for tid in test_ids:
                    test = LabTest.objects.filter(pk=tid, is_active=True).first()
                    if test:
                        LabOrderItem.objects.get_or_create(
                            order=order,
                            test=test,
                            defaults={"created_by": request.user},
                        )
                        added += 1

                for name in custom_names:
                    test = _get_or_create_custom_lab_test(name, request.user)
                    if test:
                        _, created = LabOrderItem.objects.get_or_create(
                            order=order,
                            test=test,
                            defaults={"created_by": request.user},
                        )
                        if created:
                            added += 1

                encounter.mark_payment_pending(
                    target_department="LAB",
                    user=request.user,
                )

            messages.success(
                request,
                f"Lab request created ({added} test(s)). "
                f"Patient sent to Reception for payment (or Pharmacy if NHIF).",
            )
            return redirect("encounters:doctor_queue")

        # ----- Refer -----
        elif action == "refer":
            target = (request.POST.get("target_department") or "").upper()
            allowed_depts = [
                "LAB",
                "ULTRASOUND",
                "INJECTION",
                "PHARMACY",
                "RCH",
                "MINOR_SURGERY",
                "LABOUR_WARD",
            ]
            if target not in allowed_depts:
                messages.error(request, "Invalid department.")
                return redirect(
                    "consultations:conduct_consultation", encounter_id=encounter.pk
                )

            consultation_form = ConsultationForm(request.POST, instance=consultation)
            if consultation_form.is_valid():
                obj = consultation_form.save(commit=False)
                obj.doctor = request.user
                obj.save()

            with transaction.atomic():
                encounter.mark_payment_pending(
                    target_department=target,
                    user=request.user,
                )

            messages.success(
                request,
                f"Patient referred to {target.replace('_', ' ').title()}. "
                f"Payment required at Reception unless NHIF.",
            )
            return redirect("encounters:doctor_queue")

        # ----- Finish consultation -----
        elif action == "finish_consultation":
            consultation_form = ConsultationForm(request.POST, instance=consultation)
            if consultation_form.is_valid():
                obj = consultation_form.save(commit=False)
                obj.doctor = request.user
                obj.save()

            try:
                with transaction.atomic():
                    Prescription.objects.filter(encounter=encounter).exclude(
                        source=Prescription.SOURCE_EXTERNAL
                    ).update(source=Prescription.SOURCE_IN_HOUSE)

                    in_house_qs = Prescription.objects.filter(
                        encounter=encounter,
                        source=Prescription.SOURCE_IN_HOUSE,
                    )
                    rx_count = in_house_qs.count()
                    has_in_house = rx_count > 0

                    if has_in_house:
                        if encounter.status == "RESULTS_READY":
                            encounter.status = "IN_PROGRESS"
                            encounter.save(update_fields=["status", "updated_at"])

                        if getattr(patient, "is_nhif", False):
                            encounter.release_to_department(
                                "PHARMACY",
                                user=request.user,
                                note=(
                                    "NHIF – payment bypassed; "
                                    "released to Pharmacy after consultation"
                                ),
                            )
                            messages.success(
                                request,
                                f"NHIF patient {patient.full_name}: {rx_count} "
                                f"medicine(s) sent to Pharmacy (payment skipped).",
                            )
                        else:
                            encounter.mark_payment_pending(
                                target_department="PHARMACY",
                                user=request.user,
                            )
                            encounter.refresh_from_db()
                            if encounter.status != "PAYMENT_PENDING":
                                if (
                                    encounter.status == "IN_PROGRESS"
                                    and encounter.current_department == "PHARMACY"
                                ):
                                    messages.success(
                                        request,
                                        f"{patient.full_name}: {rx_count} medicine(s) "
                                        f"released to Pharmacy.",
                                    )
                                else:
                                    messages.error(
                                        request,
                                        f"Expected PAYMENT_PENDING, got "
                                        f"{encounter.status} / "
                                        f"{encounter.current_department}.",
                                    )
                            else:
                                messages.success(
                                    request,
                                    f"Consultation done. {patient.full_name}: "
                                    f"{rx_count} medicine(s) → Payment Pending "
                                    f"(Pharmacy). Collect payment at Reception.",
                                )
                    else:
                        encounter.transition_to("COMPLETED", user=request.user)
                        if Prescription.objects.filter(
                            encounter=encounter,
                            source=Prescription.SOURCE_EXTERNAL,
                        ).exists():
                            messages.success(
                                request,
                                f"Consultation completed for {patient.full_name}. "
                                f"Print external Rx PDF if needed.",
                            )
                        else:
                            messages.warning(
                                request,
                                f"Consultation completed for {patient.full_name}. "
                                f"No in-house prescriptions on this visit.",
                            )
            except Exception as e:
                messages.error(request, f"Could not finish consultation: {e}")

            return redirect("encounters:doctor_queue")

    context = {
        "encounter": encounter,
        "patient": patient,
        "latest_vitals": latest_vitals,
        "consultation": consultation,
        "consultation_form": consultation_form,
        "prescription_form": prescription_form,
        "prescriptions": prescriptions,
        "has_external_rx": has_external_rx,
        "lab_tests": lab_tests,
        "lab_orders": lab_orders,
        "ultrasound_reports": ultrasound_reports,
        "display_name": request.user.staff_profile.display_name,
        "role_display": request.user.staff_profile.get_role_display(),
        "role": request.user.staff_profile.role,
    }
    return render(request, "consultations/conduct_consultation.html", context)


@login_required
@doctor_required
def external_rx_print(request, encounter_id):
    """Printable external prescription (browser Print → Save as PDF)."""
    encounter = get_object_or_404(
        Encounter.objects.select_related("patient"),
        pk=encounter_id,
    )
    external = (
        Prescription.objects.filter(
            encounter=encounter,
            source=Prescription.SOURCE_EXTERNAL,
        )
        .select_related("drug")
        .order_by("created_at")
    )

    if not external.exists():
        messages.warning(request, "No external prescriptions on this visit.")
        return redirect(
            "consultations:conduct_consultation", encounter_id=encounter.pk
        )

    context = {
        "encounter": encounter,
        "patient": encounter.patient,
        "prescriptions": external,
        "doctor": request.user,
        "clinic_name": "Argentina Dispensary",
    }
    return render(request, "consultations/external_rx_print.html", context)