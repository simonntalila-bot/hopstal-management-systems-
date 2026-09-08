"""
laboratory/views.py
===================
Lab staff workflow:
1. Queue – all paid patients with current_department=LAB
2. Collect sample
3. Enter results
4. Finish options:
   - Release to Doctor
   - Complete & print (lab-only / walk-away with report)
   - Send to Pharmacy (payment first unless NHIF)

Lab-only visits (no LabOrder yet) appear as orphan_visits.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.utils import timezone

from accounts.decorators import lab_required
from encounters.models import Encounter
from .models import LabOrder, LabOrderItem, LabResult, LabTest


def _ctx(request):
    p = request.user.staff_profile
    return {
        "display_name": p.display_name,
        "role_display": p.get_role_display(),
        "role": p.role,
    }


def _append_interpretation(order, encounter, interpretation):
    """Store lab interpretation on order notes and encounter notes."""
    if not interpretation:
        return
    tag = f"[Lab interpretation] {interpretation}"
    if order.clinical_notes:
        if tag not in order.clinical_notes:
            order.clinical_notes = f"{order.clinical_notes}\n{tag}".strip()
    else:
        order.clinical_notes = tag
    if encounter.notes:
        if interpretation not in encounter.notes:
            encounter.notes = f"{encounter.notes}\n[Lab] {interpretation}".strip()
    else:
        encounter.notes = f"[Lab] {interpretation}"


@login_required
@lab_required
def lab_queue(request):
    """Paid LAB visits: with orders and lab-only (no order yet)."""
    visits = (
        Encounter.objects.filter(
            status="IN_PROGRESS",
            current_department="LAB",
        )
        .select_related("patient")
        .order_by("created_at")
    )

    orders = (
        LabOrder.objects.filter(
            encounter__status="IN_PROGRESS",
            encounter__current_department="LAB",
            status__in=[
                "REQUESTED",
                "SAMPLE_COLLECTED",
                "IN_PROGRESS",
                "RESULT_ENTERED",
            ],
        )
        .select_related("encounter", "encounter__patient", "requested_by")
        .prefetch_related("items__test")
        .order_by("created_at")
    )

    order_encounter_ids = set(orders.values_list("encounter_id", flat=True))
    orphan_visits = [v for v in visits if v.id not in order_encounter_ids]

    context = _ctx(request)
    context.update({
        "visits": visits,
        "orders": orders,
        "orphan_visits": orphan_visits,
    })
    return render(request, "laboratory/lab_queue.html", context)


@login_required
@lab_required
def collect_sample(request, order_id):
    """Assign sample number and mark sample collected."""
    order = get_object_or_404(
        LabOrder.objects.select_related("encounter", "encounter__patient")
        .prefetch_related("items__test"),
        pk=order_id,
    )

    if order.status in ["RELEASED", "CANCELLED"]:
        messages.warning(request, "This order is already closed.")
        return redirect("laboratory:lab_queue")

    if request.method == "POST":
        sample_number = request.POST.get("sample_number", "").strip()
        if not sample_number:
            messages.error(request, "Sample number is required.")
            return redirect("laboratory:collect_sample", order_id=order.pk)

        with transaction.atomic():
            order.sample_number = sample_number
            order.status = "SAMPLE_COLLECTED"
            order.collected_at = timezone.now()
            order.collected_by = request.user
            order.save()

        messages.success(request, f"Sample collected: {order.sample_number}")
        return redirect("laboratory:enter_results", order_id=order.pk)

    year = timezone.localdate().year
    count = (
        LabOrder.objects.filter(sample_number__startswith=f"LB-{year}-").count()
        + 1
    )
    suggested = f"LB-{year}-{count:06d}"

    context = _ctx(request)
    context.update({
        "order": order,
        "patient": order.encounter.patient,
        "items": list(order.items.select_related("test").all()),
        "suggested_sample_number": suggested,
    })
    return render(request, "laboratory/collect_sample.html", context)


@login_required
@lab_required
def enter_results(request, order_id):
    """
    Enter results, then:
    - save_draft
    - release_doctor
    - complete_print  (lab-only / patient takes report)
    - send_pharmacy   (pay-first unless NHIF)
    """
    order = get_object_or_404(
        LabOrder.objects.select_related("encounter", "encounter__patient")
        .prefetch_related("items__test", "items__result"),
        pk=order_id,
    )

    if order.status in ["RELEASED", "CANCELLED"]:
        messages.warning(request, "This order is already closed.")
        return redirect("laboratory:lab_queue")

    items = list(order.items.select_related("test").all())
    encounter = order.encounter

    if request.method == "POST":
        action = request.POST.get("action")
        interpretation = request.POST.get("interpretation", "").strip()
        results_to_save = []
        all_have_values = True

        for item in items:
            prefix = f"item_{item.pk}_"
            value = request.POST.get(prefix + "value", "").strip()
            unit = request.POST.get(prefix + "unit", "").strip()
            reference_range = request.POST.get(
                prefix + "reference_range", ""
            ).strip()
            is_abnormal = request.POST.get(prefix + "is_abnormal") == "on"
            notes = request.POST.get(prefix + "notes", "").strip()

            result, _ = LabResult.objects.get_or_create(order_item=item)
            result.value = value
            result.unit = unit
            result.reference_range = reference_range
            result.is_abnormal = is_abnormal
            result.notes = notes
            result.entered_by = request.user
            result.entered_at = timezone.now()
            results_to_save.append(result)

            if not value:
                all_have_values = False

        # ----- Draft -----
        if action == "save_draft":
            with transaction.atomic():
                for r in results_to_save:
                    r.save()
                order.status = "RESULT_ENTERED"
                if interpretation:
                    _append_interpretation(order, encounter, interpretation)
                    order.save()
                    encounter.save(update_fields=["notes", "updated_at"])
                else:
                    order.save(update_fields=["status", "updated_at"])
            messages.success(request, "Results saved as draft.")
            return redirect("laboratory:enter_results", order_id=order.pk)

        # Shared: need all values for final actions
        final_actions = ("release_doctor", "release", "complete_print", "send_pharmacy")
        if action in final_actions and not all_have_values:
            with transaction.atomic():
                for r in results_to_save:
                    r.save()
                order.status = "RESULT_ENTERED"
                order.save(update_fields=["status", "updated_at"])
            messages.error(
                request, "Enter a result for every test before finishing."
            )
            return redirect("laboratory:enter_results", order_id=order.pk)

        # ----- Release to Doctor -----
        if action in ("release_doctor", "release"):
            with transaction.atomic():
                for r in results_to_save:
                    r.verified_by = request.user
                    r.verified_at = timezone.now()
                    r.save()
                order.status = "RELEASED"
                order.released_at = timezone.now()
                _append_interpretation(order, encounter, interpretation)
                order.save()
                encounter.status = "RESULTS_READY"
                encounter.current_department = "DOCTOR"
                encounter.save(
                    update_fields=[
                        "status",
                        "current_department",
                        "notes",
                        "updated_at",
                    ]
                )
            messages.success(request, "Results released to Doctor.")
            return redirect("laboratory:lab_queue")

        # ----- Complete & print (patient takes results) -----
        if action == "complete_print":
            with transaction.atomic():
                for r in results_to_save:
                    r.verified_by = request.user
                    r.verified_at = timezone.now()
                    r.save()
                order.status = "RELEASED"
                order.released_at = timezone.now()
                _append_interpretation(order, encounter, interpretation)
                order.save()
                encounter.transition_to("COMPLETED", user=request.user)
            messages.success(
                request, "Results finalized. Print the report for the patient."
            )
            return redirect("laboratory:print_results", order_id=order.pk)

        # ----- Send to Pharmacy -----
        if action == "send_pharmacy":
            with transaction.atomic():
                for r in results_to_save:
                    r.verified_by = request.user
                    r.verified_at = timezone.now()
                    r.save()
                order.status = "RELEASED"
                order.released_at = timezone.now()
                _append_interpretation(order, encounter, interpretation)
                order.save()

                # Ensure we can move to payment pending / pharmacy
                if encounter.status not in ("IN_PROGRESS", "PAYMENT_PENDING"):
                    encounter.status = "IN_PROGRESS"
                    encounter.save(update_fields=["status", "updated_at"])

                encounter.mark_payment_pending(
                    target_department="PHARMACY",
                    user=request.user,
                )

            encounter.refresh_from_db()
            if encounter.status == "PAYMENT_PENDING":
                messages.success(
                    request,
                    "Results saved. Patient is on Payment Pending for Pharmacy.",
                )
            else:
                messages.success(
                    request,
                    "Results saved. Patient released to Pharmacy "
                    "(NHIF or direct release).",
                )
            return redirect("laboratory:print_results", order_id=order.pk)

    for item in items:
        item.existing_result = LabResult.objects.filter(order_item=item).first()

    context = _ctx(request)
    context.update({
        "order": order,
        "patient": order.encounter.patient,
        "items": items,
    })
    return render(request, "laboratory/enter_results.html", context)


@login_required
@lab_required
def print_results(request, order_id):
    """Printable lab report for patient or records."""
    order = get_object_or_404(
        LabOrder.objects.select_related("encounter", "encounter__patient")
        .prefetch_related("items__test"),
        pk=order_id,
    )
    items = list(order.items.select_related("test").all())
    for item in items:
        item.existing_result = LabResult.objects.filter(order_item=item).first()

    context = _ctx(request)
    context.update({
        "order": order,
        "patient": order.encounter.patient,
        "items": items,
        "clinic_name": "Argentina Dispensary",
        "printed_at": timezone.now(),
    })
    return render(request, "laboratory/print_results.html", context)


@login_required
@lab_required
def lab_only_start(request, encounter_id):
    """
    Lab-only visit: select tests → create order → collect sample.
    """
    encounter = get_object_or_404(
        Encounter.objects.select_related("patient"),
        pk=encounter_id,
        status="IN_PROGRESS",
        current_department="LAB",
    )
    patient = encounter.patient
    lab_tests = LabTest.objects.filter(is_active=True).order_by(
        "category", "name"
    )

    existing = (
        LabOrder.objects.filter(
            encounter=encounter,
            status__in=[
                "REQUESTED",
                "SAMPLE_COLLECTED",
                "IN_PROGRESS",
                "RESULT_ENTERED",
            ],
        )
        .order_by("-created_at")
        .first()
    )
    if existing:
        if existing.status == "REQUESTED":
            return redirect("laboratory:collect_sample", order_id=existing.pk)
        return redirect("laboratory:enter_results", order_id=existing.pk)

    if request.method == "POST":
        test_ids = request.POST.getlist("lab_tests")
        clinical_notes = request.POST.get("lab_clinical_notes", "").strip()
        if not test_ids:
            messages.error(request, "Select at least one test.")
            return redirect(
                "laboratory:lab_only_start", encounter_id=encounter.pk
            )

        with transaction.atomic():
            order = LabOrder.objects.create(
                encounter=encounter,
                requested_by=request.user,
                clinical_notes=clinical_notes or "Lab-only visit",
                created_by=request.user,
                status="REQUESTED",
            )
            for tid in test_ids:
                test = LabTest.objects.filter(pk=tid, is_active=True).first()
                if test:
                    LabOrderItem.objects.create(
                        order=order,
                        test=test,
                        created_by=request.user,
                    )

        messages.success(request, "Lab order created. Collect sample next.")
        return redirect("laboratory:collect_sample", order_id=order.pk)

    context = _ctx(request)
    context.update({
        "encounter": encounter,
        "patient": patient,
        "lab_tests": lab_tests,
    })
    return render(request, "laboratory/lab_only_start.html", context)