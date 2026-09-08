"""
patients/views.py
=================
Patient registration, search, full clinical profile, documents, start-visit.

Reception: register, search, start visit, upload docs
Doctor / Pharmacy / RCH / Lab / Ultrasound / Injection / Labour / Admin:
  search list + view full profile + complete medical history
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction

from accounts.decorators import reception_required
from encounters.models import Encounter
from .models import Patient, PatientDocument
from .forms import PatientRegistrationForm, PatientSearchForm

# Roles allowed to open full patient profile
PROFILE_ROLES = {
    "RECEPTION",
    "DOCTOR",
    "PHARMACY",
    "RCH",
    "LAB",
    "ULTRASOUND",
    "INJECTION",
    "LABOUR_WARD",
    "ADMIN",
}

# Roles allowed to search / list patients (view only)
LIST_ROLES = {
    "RECEPTION",
    "DOCTOR",
    "PHARMACY",
    "RCH",
    "LAB",
    "ULTRASOUND",
    "INJECTION",
    "LABOUR_WARD",
    "ADMIN",
}


def _staff_ctx(request):
    p = request.user.staff_profile
    return {
        "display_name": p.display_name,
        "role_display": p.get_role_display(),
        "role": p.role,
    }


def _require_profile_access(request):
    role = getattr(getattr(request.user, "staff_profile", None), "role", None)
    return role in PROFILE_ROLES


def _build_visit_history(patient, limit=40):
    """
    Build full medical history list for the profile page.
    Each item: encounter + consultation + Rx + lab + ultrasound + payments + notes.
    """
    from consultations.models import Consultation

    prefetch = [
        "prescriptions__drug",
        "lab_orders__items__test",
        "lab_orders__items__result",
        "ultrasound_reports",
    ]

    recent_encounters = list(
        patient.encounters.select_related()
        .prefetch_related(*prefetch)
        .order_by("-created_at")[:limit]
    )

    consult_map = {
        c.encounter_id: c
        for c in Consultation.objects.filter(encounter__patient=patient)
        .select_related("doctor")
    }

    history = []
    for enc in recent_encounters:
        payments = []
        if hasattr(enc, "visit_payments"):
            try:
                payments = list(enc.visit_payments.all())
            except Exception:
                payments = []
        if not payments and hasattr(enc, "payments"):
            try:
                payments = list(enc.payments.all())
            except Exception:
                payments = []

        history.append({
            "encounter": enc,
            "consultation": consult_map.get(enc.pk),
            "prescriptions": list(enc.prescriptions.all()),
            "lab_orders": list(enc.lab_orders.all()),
            "ultrasound": list(enc.ultrasound_reports.all()),
            "payments": payments,
            "notes": (enc.notes or "").strip(),
        })

    return history, recent_encounters


@login_required
def patient_list(request):
    """
    Search / list patients.
    Reception + Admin: can register (template uses can_register).
    Doctor and other clinical roles: search + open full history.
    """
    role = getattr(getattr(request.user, "staff_profile", None), "role", None)
    if role not in LIST_ROLES:
        messages.error(request, "You do not have access to the patient list.")
        return redirect("dashboard:home")

    form = PatientSearchForm(request.GET or None)
    patients = Patient.objects.filter(is_active=True).order_by("-created_at")[:50]

    if form.is_valid() and form.cleaned_data.get("q"):
        patients = Patient.objects.search(form.cleaned_data["q"])

    context = _staff_ctx(request)
    context.update({
        "patients": patients,
        "form": form,
        "can_register": role in ("RECEPTION", "ADMIN"),
    })
    return render(request, "patients/patient_list.html", context)


@login_required
@reception_required
def patient_register(request):
    """Register a new patient (Reception / Admin only)."""
    if request.method == "POST":
        form = PatientRegistrationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                patient = form.save(commit=False)
                patient.created_by = request.user
                patient.save()

            messages.success(
                request,
                f"Patient {patient.full_name} registered successfully. "
                f"ID: {patient.patient_id}",
            )
            return redirect("patients:patient_detail", pk=patient.pk)
    else:
        form = PatientRegistrationForm()

    context = _staff_ctx(request)
    context["form"] = form
    return render(request, "patients/patient_register.html", context)


@login_required
def patient_detail(request, pk):
    """
    Full patient profile + permanent medical history.

    Visible to: Reception, Doctor, Pharmacy, RCH, Lab, Ultrasound,
                Injection, Labour, Admin.
    Document upload + Start visit: Reception / Admin only.
    """
    if not _require_profile_access(request):
        messages.error(request, "You do not have access to patient profiles.")
        return redirect("dashboard:home")

    patient = get_object_or_404(Patient, pk=pk)
    role = request.user.staff_profile.role
    can_manage = role in ("RECEPTION", "ADMIN")

    documents = patient.documents.select_related("uploaded_by").order_by("-created_at")
    history, recent_encounters = _build_visit_history(patient)

    if request.method == "POST" and request.POST.get("action") == "upload_document":
        if not can_manage:
            messages.error(request, "Only Reception can upload documents.")
            return redirect("patients:patient_detail", pk=patient.pk)

        title = request.POST.get("title", "").strip()
        notes = request.POST.get("notes", "").strip()
        file = request.FILES.get("document")
        if not title or not file:
            messages.error(request, "Title and file are required.")
        else:
            PatientDocument.objects.create(
                patient=patient,
                title=title,
                document=file,
                notes=notes,
                uploaded_by=request.user,
                created_by=request.user,
            )
            messages.success(request, "Document attached.")
        return redirect("patients:patient_detail", pk=patient.pk)

    context = _staff_ctx(request)
    context.update({
        "patient": patient,
        "documents": documents,
        "recent_encounters": recent_encounters,
        "history": history,
        "can_manage": can_manage,
    })
    return render(request, "patients/patient_detail.html", context)


@login_required
@reception_required
def start_visit(request, pk):
    """
    Start a new visit → PAYMENT_PENDING for target department.
    """
    patient = get_object_or_404(Patient, pk=pk)

    target_department = (request.GET.get("department") or "DOCTOR").upper()
    allowed = [
        "DOCTOR",
        "LAB",
        "ULTRASOUND",
        "INJECTION",
        "RCH",
        "MINOR_SURGERY",
        "LABOUR_WARD",
        "PHARMACY",
    ]
    if target_department not in allowed:
        target_department = "DOCTOR"

    with transaction.atomic():
        encounter = Encounter.objects.create(
            patient=patient,
            visit_type="OPD",
            status="REGISTERED",
            current_department=target_department,
            created_by=request.user,
        )
        encounter.mark_payment_pending(
            target_department=target_department,
            user=request.user,
        )

    messages.success(
        request,
        f"Visit started for {patient.full_name}. "
        f"Payment required before {target_department.replace('_', ' ').title()}.",
    )
    return redirect("encounters:payment_pending_queue")