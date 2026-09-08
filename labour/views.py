"""
labour/views.py
===============
Phase A: queue, labour case workspace (admission through referral).
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
    LabourCase,
    LabourAssessment,
    PartographEntry,
    MaternalObservation,
    FetalObservation,
    LabourMedication,
    DeliveryRecord,
    NewbornRecord,
    LabourComplication,
    PostDeliveryCare,
    LabourReferral,
)

DEPT = "LABOUR_WARD"


def _ctx(request):
    p = request.user.staff_profile
    return {
        "display_name": p.display_name,
        "role_display": p.get_role_display(),
        "role": p.role,
    }


def _prefill_from_rch(mother):
    """Pull obstetric data from RCH profile / latest ANC if available."""
    data = {}
    profile = getattr(mother, "rch_profile", None)
    if profile:
        data["gravida"] = profile.gravida
        data["para"] = profile.para
    try:
        from rch.models import RCHVisit, ANCRecord
        last_anc_visit = (
            RCHVisit.objects.filter(patient=mother, service_type="ANC")
            .order_by("-visit_date")
            .first()
        )
        if last_anc_visit and hasattr(last_anc_visit, "anc"):
            anc = last_anc_visit.anc
            data["lmp"] = anc.lmp
            data["edd"] = anc.edd
            data["gestational_age_weeks"] = anc.gestational_age_weeks
    except Exception:
        pass
    return data


@login_required
@role_required("LABOUR_WARD", "ADMIN")
def queue(request):
    visits = (
        Encounter.objects.filter(status="IN_PROGRESS", current_department=DEPT)
        .select_related("patient")
        .order_by("created_at")
    )
    ctx = _ctx(request)
    ctx["visits"] = visits
    return render(request, "labour/queue.html", ctx)


@login_required
@role_required("LABOUR_WARD", "ADMIN")
def case_open(request, encounter_id):
    """
    Open existing LabourCase or show admission form to create one.
    """
    encounter = get_object_or_404(
        Encounter.objects.select_related("patient"),
        pk=encounter_id,
        status="IN_PROGRESS",
        current_department=DEPT,
    )
    mother = encounter.patient

    if hasattr(encounter, "labour_case"):
        return redirect("labour:case_workspace", case_id=encounter.labour_case.pk)

    prefill = _prefill_from_rch(mother)

    if request.method == "POST":
        def num(name):
            v = request.POST.get(name)
            return int(v) if v not in (None, "") else None

        def dec(name):
            v = request.POST.get(name)
            return v if v not in (None, "") else None

        with transaction.atomic():
            case = LabourCase.objects.create(
                encounter=encounter,
                mother=mother,
                admission_at=timezone.now(),
                gestational_age_weeks=num("gestational_age_weeks"),
                gravida=num("gravida"),
                para=num("para"),
                lmp=dec("lmp") or None,
                edd=dec("edd") or None,
                presenting_complaint=request.POST.get("presenting_complaint", ""),
                labour_onset_at=dec("labour_onset_at") or None,
                membrane_status=request.POST.get("membrane_status", ""),
                liquor=request.POST.get("liquor", ""),
                contractions=request.POST.get("contractions", ""),
                cervical_dilatation_cm=dec("cervical_dilatation_cm"),
                is_high_risk=request.POST.get("is_high_risk") == "on",
                previous_cs=request.POST.get("previous_cs") == "on",
                previous_delivery_notes=request.POST.get("previous_delivery_notes", ""),
                initial_bp_systolic=num("initial_bp_systolic"),
                initial_bp_diastolic=num("initial_bp_diastolic"),
                initial_pulse=num("initial_pulse"),
                initial_temperature=dec("initial_temperature"),
                admitted_by=request.user,
                notes=request.POST.get("notes", ""),
                created_by=request.user,
                status=LabourCase.STATUS_ACTIVE,
            )
        messages.success(request, "Labour admission recorded.")
        return redirect("labour:case_workspace", case_id=case.pk)

    ctx = _ctx(request)
    ctx.update({
        "encounter": encounter,
        "mother": mother,
        "prefill": prefill,
    })
    return render(request, "labour/admission.html", ctx)


@login_required
@role_required("LABOUR_WARD", "ADMIN")
def case_workspace(request, case_id):
    """
    Main labour workspace with tabbed sections via ?tab=
    """
    case = get_object_or_404(
        LabourCase.objects.select_related("mother", "encounter"),
        pk=case_id,
    )
    tab = request.GET.get("tab", "overview")

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add_assessment":
            _add_assessment(request, case)
        elif action == "add_partograph":
            _add_partograph(request, case)
        elif action == "add_maternal_obs":
            _add_maternal_obs(request, case)
        elif action == "add_fetal_obs":
            _add_fetal_obs(request, case)
        elif action == "add_medication":
            _add_medication(request, case)
        elif action == "save_delivery":
            _save_delivery(request, case)
        elif action == "add_newborn":
            _add_newborn(request, case)
        elif action == "add_complication":
            _add_complication(request, case)
        elif action == "add_post_care":
            _add_post_care(request, case)
        elif action == "add_referral":
            _add_referral(request, case)
        elif action == "complete_case":
            return _complete_case(request, case)
        elif action == "return_doctor":
            return _return_doctor(request, case)

        return redirect(f"{request.path}?tab={tab}")

    delivery = getattr(case, "delivery", None)
    ctx = _ctx(request)
    ctx.update({
        "case": case,
        "mother": case.mother,
        "encounter": case.encounter,
        "tab": tab,
        "assessments": case.assessments.all()[:20],
        "partograph": case.partograph_entries.all(),
        "maternal_obs": case.maternal_obs.all()[:20],
        "fetal_obs": case.fetal_obs.all()[:20],
        "medications": case.medications.all()[:30],
        "delivery": delivery,
        "newborns": case.newborns.all(),
        "complications": case.complications.all(),
        "post_care": case.post_delivery_care.all()[:10],
        "referrals": case.referrals.all(),
        "mode_choices": DeliveryRecord.MODE_CHOICES,
    })
    return render(request, "labour/workspace.html", ctx)


# ----- helpers -----

def _num(post, name):
    v = post.get(name)
    return int(v) if v not in (None, "") else None


def _dec(post, name):
    v = post.get(name)
    return v if v not in (None, "") else None


def _add_assessment(request, case):
    LabourAssessment.objects.create(
        labour_case=case,
        assessed_at=timezone.now(),
        cervical_dilatation_cm=_dec(request.POST, "cervical_dilatation_cm"),
        effacement=request.POST.get("effacement", ""),
        station=request.POST.get("station", ""),
        presentation=request.POST.get("presentation", ""),
        position=request.POST.get("position", ""),
        membrane_status=request.POST.get("membrane_status", ""),
        liquor=request.POST.get("liquor", ""),
        contraction_frequency=request.POST.get("contraction_frequency", ""),
        contraction_duration=request.POST.get("contraction_duration", ""),
        pelvic_assessment=request.POST.get("pelvic_assessment", ""),
        maternal_condition=request.POST.get("maternal_condition", ""),
        assessed_by=request.user,
    )
    messages.success(request, "Assessment saved.")


def _add_partograph(request, case):
    PartographEntry.objects.create(
        labour_case=case,
        recorded_at=timezone.now(),
        cervical_dilatation_cm=_dec(request.POST, "cervical_dilatation_cm"),
        descent_of_head=request.POST.get("descent_of_head", ""),
        fetal_heart_rate=_num(request.POST, "fetal_heart_rate"),
        contractions=request.POST.get("contractions", ""),
        maternal_pulse=_num(request.POST, "maternal_pulse"),
        bp_systolic=_num(request.POST, "bp_systolic"),
        bp_diastolic=_num(request.POST, "bp_diastolic"),
        temperature=_dec(request.POST, "temperature"),
        urine_output_ml=_num(request.POST, "urine_output_ml"),
        urine_protein=request.POST.get("urine_protein", ""),
        urine_ketones=request.POST.get("urine_ketones", ""),
        oxytocin=request.POST.get("oxytocin", ""),
        iv_fluids=request.POST.get("iv_fluids", ""),
        other_interventions=request.POST.get("other_interventions", ""),
        alert_flag=request.POST.get("alert_flag") == "on",
        recorded_by=request.user,
    )
    messages.success(request, "Partograph entry added.")


def _add_maternal_obs(request, case):
    MaternalObservation.objects.create(
        labour_case=case,
        recorded_at=timezone.now(),
        bp_systolic=_num(request.POST, "bp_systolic"),
        bp_diastolic=_num(request.POST, "bp_diastolic"),
        pulse=_num(request.POST, "pulse"),
        respiratory_rate=_num(request.POST, "respiratory_rate"),
        temperature=_dec(request.POST, "temperature"),
        spo2=_num(request.POST, "spo2"),
        pain_score=_num(request.POST, "pain_score"),
        consciousness=request.POST.get("consciousness", ""),
        urine_output_ml=_num(request.POST, "urine_output_ml"),
        bleeding=request.POST.get("bleeding", ""),
        general_condition=request.POST.get("general_condition", ""),
        alert_flag=request.POST.get("alert_flag") == "on",
        recorded_by=request.user,
    )
    messages.success(request, "Maternal observation saved.")


def _add_fetal_obs(request, case):
    FetalObservation.objects.create(
        labour_case=case,
        recorded_at=timezone.now(),
        fetal_heart_rate=_num(request.POST, "fetal_heart_rate"),
        fetal_movement=request.POST.get("fetal_movement", ""),
        presentation=request.POST.get("presentation", ""),
        position=request.POST.get("position", ""),
        station=request.POST.get("station", ""),
        liquor=request.POST.get("liquor", ""),
        distress_notes=request.POST.get("distress_notes", ""),
        alert_flag=request.POST.get("alert_flag") == "on",
        recorded_by=request.user,
    )
    messages.success(request, "Fetal observation saved.")


def _add_medication(request, case):
    name = request.POST.get("drug_name", "").strip()
    if not name:
        messages.error(request, "Drug name is required.")
        return
    LabourMedication.objects.create(
        labour_case=case,
        given_at=timezone.now(),
        drug_name=name,
        dose=request.POST.get("dose", ""),
        route=request.POST.get("route", ""),
        indication=request.POST.get("indication", ""),
        administered_by=request.user,
    )
    messages.success(request, "Medication recorded.")


def _save_delivery(request, case):
    delivery, _ = DeliveryRecord.objects.get_or_create(labour_case=case)
    delivery.delivered_at = _dec(request.POST, "delivered_at") or timezone.now()
    delivery.mode = request.POST.get("mode") or DeliveryRecord.MODE_SVD
    delivery.indication = request.POST.get("indication", "")
    delivery.presentation = request.POST.get("presentation", "")
    delivery.position = request.POST.get("position", "")
    delivery.placenta_delivered_at = _dec(request.POST, "placenta_delivered_at") or None
    pc = request.POST.get("placenta_complete")
    delivery.placenta_complete = True if pc == "yes" else (False if pc == "no" else None)
    delivery.estimated_blood_loss_ml = _num(request.POST, "estimated_blood_loss_ml")
    delivery.perineum = request.POST.get("perineum", "")
    delivery.episiotomy = request.POST.get("episiotomy") == "on"
    delivery.suturing = request.POST.get("suturing", "")
    delivery.delivery_notes = request.POST.get("delivery_notes", "")
    delivery.conducted_by = request.user
    delivery.save()
    case.status = LabourCase.STATUS_DELIVERED
    case.save(update_fields=["status", "updated_at"])
    messages.success(request, "Delivery record saved.")


def _add_newborn(request, case):
    delivery = getattr(case, "delivery", None)
    order = case.newborns.count() + 1
    NewbornRecord.objects.create(
        labour_case=case,
        delivery=delivery,
        mother=case.mother,
        birth_order=order,
        born_at=_dec(request.POST, "born_at") or timezone.now(),
        sex=request.POST.get("sex") or NewbornRecord.SEX_U,
        birth_weight_kg=_dec(request.POST, "birth_weight_kg"),
        length_cm=_dec(request.POST, "length_cm"),
        head_circumference_cm=_dec(request.POST, "head_circumference_cm"),
        apgar_1=_num(request.POST, "apgar_1"),
        apgar_5=_num(request.POST, "apgar_5"),
        apgar_10=_num(request.POST, "apgar_10"),
        gestational_age_weeks=_num(request.POST, "gestational_age_weeks"),
        birth_status=request.POST.get("birth_status", ""),
        resuscitation=request.POST.get("resuscitation") == "on",
        condition_notes=request.POST.get("condition_notes", ""),
        breastfeeding_initiated=(
            True if request.POST.get("breastfeeding_initiated") == "yes"
            else (False if request.POST.get("breastfeeding_initiated") == "no" else None)
        ),
        interventions=request.POST.get("interventions", ""),
    )
    messages.success(request, f"Newborn #{order} recorded.")


def _add_complication(request, case):
    desc = request.POST.get("description", "").strip()
    if not desc:
        messages.error(request, "Description is required.")
        return
    LabourComplication.objects.create(
        labour_case=case,
        category=request.POST.get("category", ""),
        description=desc,
        recorded_by=request.user,
    )
    messages.success(request, "Complication recorded.")


def _add_post_care(request, case):
    PostDeliveryCare.objects.create(
        labour_case=case,
        mother_bp_systolic=_num(request.POST, "mother_bp_systolic"),
        mother_bp_diastolic=_num(request.POST, "mother_bp_diastolic"),
        mother_pulse=_num(request.POST, "mother_pulse"),
        bleeding=request.POST.get("bleeding", ""),
        uterus=request.POST.get("uterus", ""),
        pain=request.POST.get("pain", ""),
        perineum_wound=request.POST.get("perineum_wound", ""),
        mother_medications=request.POST.get("mother_medications", ""),
        breastfeeding=request.POST.get("breastfeeding", ""),
        mother_condition=request.POST.get("mother_condition", ""),
        baby_feeding=request.POST.get("baby_feeding", ""),
        baby_temperature=_dec(request.POST, "baby_temperature"),
        baby_notes=request.POST.get("baby_notes", ""),
        disposition=request.POST.get("disposition", ""),
        recorded_by=request.user,
    )
    messages.success(request, "Post-delivery care recorded.")


def _add_referral(request, case):
    reason = request.POST.get("reason", "").strip()
    if not reason:
        messages.error(request, "Referral reason is required.")
        return
    LabourReferral.objects.create(
        labour_case=case,
        reason=reason,
        receiving_facility=request.POST.get("receiving_facility", ""),
        maternal_condition=request.POST.get("maternal_condition", ""),
        fetal_newborn_condition=request.POST.get("fetal_newborn_condition", ""),
        treatment_given=request.POST.get("treatment_given", ""),
        transport=request.POST.get("transport", ""),
        notes=request.POST.get("notes", ""),
        referred_by=request.user,
    )
    case.status = LabourCase.STATUS_REFERRED
    case.save(update_fields=["status", "updated_at"])
    messages.success(request, "Referral recorded.")


def _complete_case(request, case):
    case.status = LabourCase.STATUS_CLOSED
    case.save(update_fields=["status", "updated_at"])
    case.encounter.transition_to("COMPLETED", user=request.user)
    messages.success(request, "Labour case closed. Visit completed.")
    return redirect("labour:queue")


def _return_doctor(request, case):
    enc = case.encounter
    enc.status = "IN_PROGRESS"
    enc.current_department = "DOCTOR"
    enc.save(update_fields=["status", "current_department", "updated_at"])
    messages.success(request, "Patient returned to Doctor.")
    return redirect("labour:queue")