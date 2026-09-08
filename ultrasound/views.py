"""
ultrasound/views.py
===================
Ultrasound queue + service.
On return to doctor: RESULTS_READY + DOCTOR so consultation shows reports.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction

from accounts.decorators import role_required
from encounters.models import Encounter
from .models import UltrasoundReport

DEPT = "ULTRASOUND"


def _ctx(request):
    p = request.user.staff_profile
    return {
        "display_name": p.display_name,
        "role_display": p.get_role_display(),
        "role": p.role,
    }


@login_required
@role_required("ULTRASOUND", "ADMIN")
def queue(request):
    visits = (
        Encounter.objects.filter(status="IN_PROGRESS", current_department=DEPT)
        .select_related("patient")
        .order_by("created_at")
    )
    ctx = _ctx(request)
    ctx["visits"] = visits
    return render(request, "ultrasound/queue.html", ctx)


@login_required
@role_required("ULTRASOUND", "ADMIN")
def service(request, encounter_id):
    """
    Capture findings + optional image.
    Actions:
      - save_only: stay on ultrasound queue
      - return_doctor: RESULTS_READY → Doctor (reports visible on consult)
      - complete: close visit (no doctor follow-up)
    """
    encounter = get_object_or_404(
        Encounter.objects.select_related("patient"),
        pk=encounter_id,
        status="IN_PROGRESS",
        current_department=DEPT,
    )
    patient = encounter.patient
    reports = encounter.ultrasound_reports.all().order_by("-created_at")

    if request.method == "POST":
        action = request.POST.get("action") or "save_only"
        findings = (
            request.POST.get("findings")
            or request.POST.get("notes")
            or ""
        ).strip()
        image = request.FILES.get("image")

        if action in ("return_doctor", "complete") and not findings and not image:
            if not reports.exists():
                messages.error(
                    request,
                    "Add findings and/or an image before returning to doctor or completing.",
                )
                return redirect("ultrasound:service", encounter_id=encounter.pk)

        try:
            with transaction.atomic():
                created = None
                if findings or image:
                    created = UltrasoundReport.objects.create(
                        encounter=encounter,
                        findings=findings,
                        image=image if image else None,
                        performed_by=request.user,
                        created_by=request.user,
                    )
                    if findings:
                        note_line = f"[Ultrasound] {findings}"
                        existing = (encounter.notes or "").strip()
                        if note_line not in existing:
                            encounter.notes = (
                                f"{existing}\n{note_line}".strip()
                                if existing
                                else note_line
                            )
                            encounter.save(
                                update_fields=["notes", "updated_at"]
                            )

                if action == "return_doctor":
                    # Same pattern as lab: doctor queue + results panel
                    encounter.status = "RESULTS_READY"
                    encounter.current_department = "DOCTOR"
                    encounter.save(
                        update_fields=[
                            "status",
                            "current_department",
                            "updated_at",
                        ]
                    )
                    messages.success(
                        request,
                        "Ultrasound report saved. Patient sent to Doctor "
                        "(results ready).",
                    )
                    return redirect("ultrasound:queue")

                if action == "complete":
                    encounter.transition_to("COMPLETED", user=request.user)
                    messages.success(
                        request,
                        "Ultrasound completed. Visit closed.",
                    )
                    return redirect("ultrasound:queue")

                # save_only
                if created:
                    messages.success(request, "Report saved.")
                else:
                    messages.info(request, "Nothing new to save.")
                return redirect("ultrasound:service", encounter_id=encounter.pk)

        except Exception as e:
            messages.error(request, f"Could not save ultrasound: {e}")
            return redirect("ultrasound:service", encounter_id=encounter.pk)

    ctx = _ctx(request)
    ctx.update({
        "encounter": encounter,
        "patient": patient,
        "reports": reports,
    })
    return render(request, "ultrasound/service.html", ctx)