"""
encounters/views.py
===================
Pay-first queues and payment collection for Reception,
plus Doctor queue of already-paid patients.
"""

from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction

from accounts.decorators import reception_required, doctor_required
from .models import Encounter, Payment


# ------------------------------------------------------------------
# Payment Pending Queue (Reception)
# ------------------------------------------------------------------
@login_required
@reception_required
def payment_pending_queue(request):
    """
    Visits waiting for payment before they can enter a department.
    """
    queue = (
        Encounter.objects.filter(status="PAYMENT_PENDING")
        .select_related("patient")
        .order_by("created_at")
    )

    context = {
        "queue": queue,
        "display_name": request.user.staff_profile.display_name,
        "role_display": request.user.staff_profile.get_role_display(),
        "role": request.user.staff_profile.role,
    }
    return render(request, "encounters/payment_pending_queue.html", context)


@login_required
@reception_required
def collect_payment(request, encounter_id):
    """
    Collect Cash or Mobile Money payment, save the log,
    then release the visit to the target department.
    """
    encounter = get_object_or_404(
        Encounter.objects.select_related("patient"),
        pk=encounter_id,
        status="PAYMENT_PENDING",
    )

    if request.method == "POST":
        method = request.POST.get("payment_method", "CASH")
        reference = request.POST.get("reference", "").strip()
        amount_raw = request.POST.get("amount", "").strip()
        notes = request.POST.get("notes", "").strip()

        if method not in ["CASH", "MOBILE_MONEY"]:
            messages.error(request, "Invalid payment method.")
            return redirect("encounters:collect_payment", encounter_id=encounter.pk)

        try:
            amount = Decimal(amount_raw)
            if amount <= 0:
                raise InvalidOperation
        except (InvalidOperation, TypeError):
            messages.error(request, "Please enter a valid amount greater than 0.")
            return redirect("encounters:collect_payment", encounter_id=encounter.pk)

        if method == "MOBILE_MONEY" and not reference:
            messages.error(request, "Mobile Money reference is required.")
            return redirect("encounters:collect_payment", encounter_id=encounter.pk)

        try:
            with transaction.atomic():
                # Save permanent payment log
                Payment.objects.create(
                    encounter=encounter,
                    amount=amount,
                    method=method,
                    reference=reference,
                    received_by=request.user,
                    notes=notes,
                    created_by=request.user,
                )

                # Release patient to department
                encounter.mark_paid_and_release(user=request.user)

            messages.success(
                request,
                f"Payment of TZS {amount:,.0f} ({method}) recorded. "
                f"{encounter.patient.full_name} released to "
                f"{encounter.get_current_department_display()}."
            )
            return redirect("encounters:payment_pending_queue")

        except Exception as e:
            messages.error(request, str(e))
            return redirect("encounters:collect_payment", encounter_id=encounter.pk)

    context = {
        "encounter": encounter,
        "patient": encounter.patient,
        "display_name": request.user.staff_profile.display_name,
        "role_display": request.user.staff_profile.get_role_display(),
        "role": request.user.staff_profile.role,
    }
    return render(request, "encounters/collect_payment.html", context)


# ------------------------------------------------------------------
# Doctor Queue (already paid)
# ------------------------------------------------------------------
@login_required
@doctor_required
def doctor_queue(request):
    """
    Patients ready for doctor:
    - IN_PROGRESS + DOCTOR (normal consultation)
    - RESULTS_READY + DOCTOR (lab results returned)
    """
    queue = (
        Encounter.objects.filter(
            current_department="DOCTOR",
            status__in=["IN_PROGRESS", "RESULTS_READY"],
        )
        .select_related("patient")
        .order_by("created_at")
    )

    context = {
        "queue": queue,
        "display_name": request.user.staff_profile.display_name,
        "role_display": request.user.staff_profile.get_role_display(),
        "role": request.user.staff_profile.role,
    }
    return render(request, "encounters/doctor_queue.html", context)