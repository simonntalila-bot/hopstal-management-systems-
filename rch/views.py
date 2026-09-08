"""
rch/views.py
============
Phase A: queue, service type selection, ANC / PNC / Under-5 / FP / Immunization.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.utils import timezone

from accounts.decorators import role_required
from encounters.models import Encounter
from patients.models import Patient
from .models import (
    RCHClientProfile,
    RCHVisit,
    ANCRecord,
    Under5Record,
    ImmunizationRecord,
    FamilyPlanningRecord,
    PNCRecord,
)

DEPT = "RCH"


def _ctx(request):
    p = request.user.staff_profile
    return {
        "display_name": p.display_name,
        "role_display": p.get_role_display(),
        "role": p.role,
    }


def _get_or_create_profile(patient, user):
    profile, _ = RCHClientProfile.objects.get_or_create(
        patient=patient,
        defaults={"created_by": user},
    )
    return profile


@login_required
@role_required("RCH", "ADMIN")
def queue(request):
    visits = (
        Encounter.objects.filter(status="IN_PROGRESS", current_department=DEPT)
        .select_related("patient")
        .order_by("created_at")
    )
    ctx = _ctx(request)
    ctx["visits"] = visits
    return render(request, "rch/queue.html", ctx)


@login_required
@role_required("RCH", "ADMIN")
def service_start(request, encounter_id):
    """Choose RCH service type for this paid visit."""
    encounter = get_object_or_404(
        Encounter.objects.select_related("patient"),
        pk=encounter_id,
        status="IN_PROGRESS",
        current_department=DEPT,
    )
    patient = encounter.patient
    profile = _get_or_create_profile(patient, request.user)

    # Resume if visit already typed
    if hasattr(encounter, "rch_visit"):
        return redirect("rch:service_form", encounter_id=encounter.pk)

    if request.method == "POST":
        service_type = request.POST.get("service_type", "").upper()
        allowed = {c[0] for c in RCHVisit.SERVICE_CHOICES}
        if service_type not in allowed:
            messages.error(request, "Select a valid service type.")
            return redirect("rch:service_start", encounter_id=encounter.pk)

        with transaction.atomic():
            RCHVisit.objects.create(
                encounter=encounter,
                patient=patient,
                service_type=service_type,
                visit_date=timezone.localdate(),
                attended_by=request.user,
                created_by=request.user,
            )
        return redirect("rch:service_form", encounter_id=encounter.pk)

    ctx = _ctx(request)
    ctx.update({
        "encounter": encounter,
        "patient": patient,
        "profile": profile,
        "service_choices": RCHVisit.SERVICE_CHOICES,
    })
    return render(request, "rch/service_start.html", ctx)


@login_required
@role_required("RCH", "ADMIN")
def service_form(request, encounter_id):
    """Route to the correct clinical form for this RCH visit."""
    encounter = get_object_or_404(
        Encounter.objects.select_related("patient", "rch_visit"),
        pk=encounter_id,
        status="IN_PROGRESS",
        current_department=DEPT,
    )
    if not hasattr(encounter, "rch_visit"):
        return redirect("rch:service_start", encounter_id=encounter.pk)

    rch_visit = encounter.rch_visit
    st = rch_visit.service_type

    if st == RCHVisit.ANC:
        return _anc_form(request, encounter, rch_visit)
    if st == RCHVisit.PNC:
        return _pnc_form(request, encounter, rch_visit)
    if st == RCHVisit.UNDER5:
        return _under5_form(request, encounter, rch_visit)
    if st == RCHVisit.IMMUNIZATION:
        return _imm_form(request, encounter, rch_visit)
    if st == RCHVisit.FP:
        return _fp_form(request, encounter, rch_visit)

    # NUTRITION / OTHER – notes only
    return _notes_only_form(request, encounter, rch_visit)


def _finish_actions(request, encounter, rch_visit):
    """Shared POST finish: return doctor or complete."""
    action = request.POST.get("action")
    rch_visit.clinical_notes = request.POST.get("clinical_notes", rch_visit.clinical_notes)
    rch_visit.is_high_risk = request.POST.get("is_high_risk") == "on"
    next_appt = request.POST.get("next_appointment") or None
    rch_visit.next_appointment = next_appt or None
    rch_visit.attended_by = request.user
    rch_visit.save()

    if action == "return_doctor":
        encounter.status = "IN_PROGRESS"
        encounter.current_department = "DOCTOR"
        encounter.save(update_fields=["status", "current_department", "updated_at"])
        messages.success(request, "RCH record saved. Patient returned to Doctor.")
        return redirect("rch:queue")

    if action == "complete":
        encounter.transition_to("COMPLETED", user=request.user)
        messages.success(request, "RCH visit completed.")
        return redirect("rch:queue")

    messages.success(request, "Saved.")
    return redirect("rch:service_form", encounter_id=encounter.pk)


def _anc_form(request, encounter, rch_visit):
    patient = encounter.patient
    profile = _get_or_create_profile(patient, request.user)
    anc, _ = ANCRecord.objects.get_or_create(rch_visit=rch_visit)

    if request.method == "POST":
        # Profile obstetric
        for field in ("gravida", "para", "abortions", "living_children"):
            val = request.POST.get(field)
            if val is not None and val != "":
                setattr(profile, field, int(val))
        if request.POST.get("hiv_status") is not None:
            profile.hiv_status = request.POST.get("hiv_status", "")
        profile.save()

        # ANC fields
        def dec(name):
            v = request.POST.get(name)
            return v if v not in (None, "") else None

        anc.lmp = dec("lmp")
        anc.edd = dec("edd")
        ga = dec("gestational_age_weeks")
        anc.gestational_age_weeks = int(ga) if ga else None
        n = dec("anc_visit_number")
        anc.anc_visit_number = int(n) if n else None
        anc.weight_kg = dec("weight_kg")
        anc.height_cm = dec("height_cm")
        s, d = dec("bp_systolic"), dec("bp_diastolic")
        anc.bp_systolic = int(s) if s else None
        anc.bp_diastolic = int(d) if d else None
        fhr = dec("fetal_heart_rate")
        anc.fetal_heart_rate = int(fhr) if fhr else None

        # Fetal / abdominal measurements
        anc.fundal_height_cm = dec("fundal_height_cm")
        anc.abdominal_circumference_cm = dec("abdominal_circumference_cm")
        efw = dec("expected_fetal_weight_g")
        anc.expected_fetal_weight_g = int(efw) if efw else None
        anc.expected_fetal_length_cm = dec("expected_fetal_length_cm")

        anc.risk_factors = request.POST.get("risk_factors", "")
        anc.supplements = request.POST.get("supplements", "")
        anc.lab_notes = request.POST.get("lab_notes", "")
        anc.ultrasound_notes = request.POST.get("ultrasound_notes", "")
        anc.plan = request.POST.get("plan", "")
        anc.save()

        return _finish_actions(request, encounter, rch_visit)

    ctx = _ctx(request)
    ctx.update({
        "encounter": encounter,
        "patient": patient,
        "profile": profile,
        "rch_visit": rch_visit,
        "anc": anc,
        "service_label": "Antenatal care",
    })
    return render(request, "rch/anc_form.html", ctx)


def _pnc_form(request, encounter, rch_visit):
    patient = encounter.patient
    pnc, _ = PNCRecord.objects.get_or_create(rch_visit=rch_visit)

    if request.method == "POST":
        def dec(name):
            v = request.POST.get(name)
            return v if v not in (None, "") else None

        d = dec("days_postpartum")
        pnc.days_postpartum = int(d) if d else None
        s, di = dec("mother_bp_systolic"), dec("mother_bp_diastolic")
        pnc.mother_bp_systolic = int(s) if s else None
        pnc.mother_bp_diastolic = int(di) if di else None
        pnc.mother_condition = request.POST.get("mother_condition", "")
        pnc.bleeding = request.POST.get("bleeding", "")
        pnc.breastfeeding = request.POST.get("breastfeeding", "")
        pnc.baby_condition = request.POST.get("baby_condition", "")
        pnc.baby_weight_kg = dec("baby_weight_kg")
        pnc.counselling = request.POST.get("counselling", "")
        pnc.save()
        return _finish_actions(request, encounter, rch_visit)

    ctx = _ctx(request)
    ctx.update({
        "encounter": encounter,
        "patient": patient,
        "rch_visit": rch_visit,
        "pnc": pnc,
        "service_label": "Postnatal care",
    })
    return render(request, "rch/pnc_form.html", ctx)


def _under5_form(request, encounter, rch_visit):
    patient = encounter.patient
    under5, _ = Under5Record.objects.get_or_create(rch_visit=rch_visit)

    if request.method == "POST":
        def dec(name):
            v = request.POST.get(name)
            return v if v not in (None, "") else None

        under5.weight_kg = dec("weight_kg")
        under5.height_cm = dec("height_cm")
        under5.muac_cm = dec("muac_cm")
        under5.temperature_c = dec("temperature_c")
        under5.nutrition_status = request.POST.get("nutrition_status", "")
        under5.development_notes = request.POST.get("development_notes", "")
        under5.diagnosis = request.POST.get("diagnosis", "")
        under5.treatment = request.POST.get("treatment", "")
        under5.save()
        return _finish_actions(request, encounter, rch_visit)

    ctx = _ctx(request)
    ctx.update({
        "encounter": encounter,
        "patient": patient,
        "rch_visit": rch_visit,
        "under5": under5,
        "service_label": "Under-5 / child health",
    })
    return render(request, "rch/under5_form.html", ctx)


def _fp_form(request, encounter, rch_visit):
    patient = encounter.patient
    fp, _ = FamilyPlanningRecord.objects.get_or_create(rch_visit=rch_visit)

    if request.method == "POST":
        fp.method = request.POST.get("method", "")
        fp.method_provided = request.POST.get("method_provided") == "on"
        fp.previous_method = request.POST.get("previous_method", "")
        fp.side_effects = request.POST.get("side_effects", "")
        fp.counselling_notes = request.POST.get("counselling_notes", "")
        fu = request.POST.get("follow_up_date") or None
        fp.follow_up_date = fu or None
        fp.save()
        return _finish_actions(request, encounter, rch_visit)

    ctx = _ctx(request)
    ctx.update({
        "encounter": encounter,
        "patient": patient,
        "rch_visit": rch_visit,
        "fp": fp,
        "method_choices": FamilyPlanningRecord.METHOD_CHOICES,
        "service_label": "Family planning",
    })
    return render(request, "rch/fp_form.html", ctx)


def _imm_form(request, encounter, rch_visit):
    patient = encounter.patient
    doses = rch_visit.immunizations.all()

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add_vaccine":
            vaccine = request.POST.get("vaccine", "")
            if not vaccine:
                messages.error(request, "Select a vaccine.")
                return redirect("rch:service_form", encounter_id=encounter.pk)
            ImmunizationRecord.objects.create(
                rch_visit=rch_visit,
                patient=patient,
                vaccine=vaccine,
                vaccine_other=request.POST.get("vaccine_other", ""),
                dose_date=request.POST.get("dose_date") or timezone.localdate(),
                next_due=request.POST.get("next_due") or None,
                batch_number=request.POST.get("batch_number", ""),
                notes=request.POST.get("imm_notes", ""),
                created_by=request.user,
            )
            messages.success(request, "Vaccine recorded.")
            return redirect("rch:service_form", encounter_id=encounter.pk)

        return _finish_actions(request, encounter, rch_visit)

    ctx = _ctx(request)
    ctx.update({
        "encounter": encounter,
        "patient": patient,
        "rch_visit": rch_visit,
        "doses": doses,
        "vaccine_choices": ImmunizationRecord.VACCINE_CHOICES,
        "service_label": "Immunization",
        "history": ImmunizationRecord.objects.filter(patient=patient).order_by("-dose_date")[:20],
    })
    return render(request, "rch/imm_form.html", ctx)


def _notes_only_form(request, encounter, rch_visit):
    patient = encounter.patient
    if request.method == "POST":
        return _finish_actions(request, encounter, rch_visit)

    ctx = _ctx(request)
    ctx.update({
        "encounter": encounter,
        "patient": patient,
        "rch_visit": rch_visit,
        "service_label": rch_visit.get_service_type_display(),
    })
    return render(request, "rch/notes_form.html", ctx)