"""
injection/views.py
==================
Two services under one module:
  - Injection room   → department INJECTION
  - Minor surgery    → department MINOR_SURGERY
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.utils import timezone

from accounts.decorators import role_required
from encounters.models import Encounter
from .models import InjectionService


def _ctx(request):
    p = request.user.staff_profile
    return {
        "display_name": p.display_name,
        "role_display": p.get_role_display(),
        "role": p.role,
    }


INJECTION_TYPES = [
    ("INJECTION", "Injection / IM-IV"),
    ("DRESSING", "Wound dressing"),
    ("OTHER", "Other"),
]

SURGERY_TYPES = [
    ("MINOR_SURGERY", "Minor surgery"),
    ("SUTURE", "Suturing"),
    ("INCISION_DRAINAGE", "Incision & drainage"),
    ("OTHER", "Other procedure"),
]


def _queue(request, dept, title):
    visits = (
        Encounter.objects.filter(status="IN_PROGRESS", current_department=dept)
        .select_related("patient")
        .order_by("created_at")
    )
    ctx = _ctx(request)
    ctx.update({
        "visits": visits,
        "dept": dept,
        "page_heading": title,
    })
    return render(request, "injection/queue.html", ctx)


def _service(request, encounter_id, dept, service_types, label, queue_name, template):
    encounter = get_object_or_404(
        Encounter.objects.select_related("patient"),
        pk=encounter_id,
        status="IN_PROGRESS",
        current_department=dept,
    )
    patient = encounter.patient
    past = encounter.injection_services.all().order_by("-performed_at")

    if request.method == "POST":
        action = request.POST.get("action") or "complete"
        service_type = (request.POST.get("service_type") or service_types[0][0]).strip()
        procedure_name = (request.POST.get("procedure_name") or "").strip()
        notes = (request.POST.get("notes") or "").strip()
        materials = (request.POST.get("materials_used") or "").strip()
        complications = (request.POST.get("complications") or "").strip()

        valid = {c[0] for c in service_types}
        if service_type not in valid:
            service_type = service_types[0][0]

        if dept == "MINOR_SURGERY" and not procedure_name and not notes:
            messages.error(request, "Enter procedure name or clinical notes.")
            return redirect(request.path)

        with transaction.atomic():
            InjectionService.objects.create(
                encounter=encounter,
                service_type=service_type,
                procedure_name=procedure_name,
                notes=notes,
                materials_used=materials,
                complications=complications,
                performed_by=request.user,
                performed_at=timezone.now(),
                created_by=request.user,
                status="DONE",
            )
            tag = dict(InjectionService.SERVICE_TYPES).get(service_type, service_type)
            line = f"\n[{label}] {tag}: {procedure_name or notes or 'Done'}"
            encounter.notes = (encounter.notes or "") + line
            encounter.save(update_fields=["notes", "updated_at"])

            if action == "return_doctor":
                encounter.status = "IN_PROGRESS"
                encounter.current_department = "DOCTOR"
                encounter.save(
                    update_fields=["status", "current_department", "updated_at"]
                )
                messages.success(request, f"{label} recorded. Returned to Doctor.")
                return redirect(queue_name)

            if action == "save":
                messages.success(request, "Saved. Patient still on this list.")
                return redirect(request.path)

            encounter.transition_to("COMPLETED", user=request.user)
            messages.success(request, f"{label} completed. Visit closed.")
            return redirect(queue_name)

    ctx = _ctx(request)
    ctx.update({
        "encounter": encounter,
        "patient": patient,
        "past": past,
        "service_types": service_types,
        "dept": dept,
        "label": label,
        "queue_url_name": queue_name,
        "is_surgery": dept == "MINOR_SURGERY",
    })
    return render(request, template, ctx)


@login_required
@role_required("INJECTION", "ADMIN")
def queue(request):
    return _queue(request, "INJECTION", "Injection room queue")


@login_required
@role_required("INJECTION", "ADMIN")
def service(request, encounter_id):
    return _service(
        request,
        encounter_id,
        "INJECTION",
        INJECTION_TYPES,
        "Injection",
        "injection:queue",
        "injection/service.html",
    )


@login_required
@role_required("INJECTION", "ADMIN")
def surgery_queue(request):
    return _queue(request, "MINOR_SURGERY", "Minor surgery queue")


@login_required
@role_required("INJECTION", "ADMIN")
def surgery_service(request, encounter_id):
    return _service(
        request,
        encounter_id,
        "MINOR_SURGERY",
        SURGERY_TYPES,
        "Minor surgery",
        "injection:surgery_queue",
        "injection/surgery_service.html",
    )