"""
pharmacy/views.py
=================
Queue, dispense (incl. pharmacy-only add items), inventory, stock adjust.
Role: PHARMACY (+ ADMIN)
"""

from datetime import timedelta, datetime

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from accounts.decorators import pharmacy_required
from encounters.models import Encounter
from consultations.models import Prescription
from .models import Drug, DispenseRecord, StockAdjustment


def _ctx(request):
    p = request.user.staff_profile
    return {
        "display_name": p.display_name,
        "role_display": p.get_role_display(),
        "role": p.role,
    }


@login_required
@pharmacy_required
def pharmacy_queue(request):
    visits = (
        Encounter.objects.filter(
            status="IN_PROGRESS",
            current_department="PHARMACY",
        )
        .select_related("patient")
        .prefetch_related("prescriptions__drug")
        .order_by("created_at")
    )
    context = _ctx(request)
    context["visits"] = visits
    return render(request, "pharmacy/pharmacy_queue.html", context)


@login_required
@pharmacy_required
def dispense(request, encounter_id):
    """
    Dispense in-house prescriptions.
    Pharmacy-only visits: staff can add medicines here before dispensing.
    """
    encounter = get_object_or_404(
        Encounter.objects.select_related("patient"),
        pk=encounter_id,
    )

    if encounter.current_department != "PHARMACY":
        messages.error(request, "This visit is not assigned to Pharmacy.")
        return redirect("pharmacy:pharmacy_queue")

    if encounter.status == "PAYMENT_PENDING":
        messages.error(request, "Payment is still pending for this visit.")
        return redirect("pharmacy:pharmacy_queue")

    if encounter.status not in ("IN_PROGRESS", "RESULTS_READY"):
        messages.error(
            request,
            f"Cannot dispense while visit status is {encounter.status}.",
        )
        return redirect("pharmacy:pharmacy_queue")

    # ----- Add OTC / pharmacy-only line -----
    if request.method == "POST" and request.POST.get("action") == "add_item":
        drug_id = request.POST.get("drug_id")
        instructions = request.POST.get("instructions", "").strip()
        try:
            qty = int(request.POST.get("quantity") or "1")
            if qty < 1:
                raise ValueError("Quantity must be at least 1.")
            drug = Drug.objects.get(pk=drug_id, is_active=True)
            if getattr(drug, "is_expired", False):
                raise ValueError(f"{drug.name} is expired.")
            if drug.stock_quantity < qty:
                raise ValueError(
                    f"Insufficient stock for {drug.name} "
                    f"(available {drug.stock_quantity})."
                )
            Prescription.objects.create(
                encounter=encounter,
                drug=drug,
                quantity=qty,
                dosage_instructions=instructions,
                source=Prescription.SOURCE_IN_HOUSE,
                doctor=None,
                created_by=request.user,
            )
            messages.success(request, f"Added {drug.name} ×{qty}.")
        except Drug.DoesNotExist:
            messages.error(request, "Invalid or inactive medicine.")
        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Could not add medicine: {e}")
        return redirect("pharmacy:dispense", encounter_id=encounter.pk)

    # In-house only
    prescriptions = list(
        Prescription.objects.filter(
            encounter=encounter,
            source=Prescription.SOURCE_IN_HOUSE,
        ).select_related("drug")
    )

    # ----- Dispense selected -----
    if request.method == "POST" and request.POST.get("action") == "dispense":
        selected_ids = request.POST.getlist("prescription_ids")
        if not selected_ids:
            messages.error(request, "Select at least one medicine to dispense.")
            return redirect("pharmacy:dispense", encounter_id=encounter.pk)

        try:
            with transaction.atomic():
                dispensed_names = []
                for rx_id in selected_ids:
                    rx = (
                        Prescription.objects.select_related("drug")
                        .select_for_update()
                        .get(
                            pk=rx_id,
                            encounter=encounter,
                            source=Prescription.SOURCE_IN_HOUSE,
                        )
                    )
                    drug = Drug.objects.select_for_update().get(pk=rx.drug_id)
                    qty = int(rx.quantity or 1)

                    if not drug.is_active:
                        raise ValueError(
                            f"{drug.name} is inactive and cannot be dispensed."
                        )
                    if getattr(drug, "is_expired", False):
                        raise ValueError(
                            f"{drug.name} is expired and cannot be dispensed."
                        )
                    if qty < 1:
                        raise ValueError(f"Invalid quantity for {drug.name}.")
                    if drug.stock_quantity < qty:
                        raise ValueError(
                            f"Insufficient stock for {drug.name}. "
                            f"Available: {drug.stock_quantity}, needed: {qty}."
                        )
                    if DispenseRecord.objects.filter(prescription=rx).exists():
                        raise ValueError(
                            f"{drug.name} was already dispensed on this visit."
                        )

                    drug.stock_quantity = F("stock_quantity") - qty
                    drug.save(update_fields=["stock_quantity", "updated_at"])
                    drug.refresh_from_db(fields=["stock_quantity"])

                    DispenseRecord.objects.create(
                        encounter=encounter,
                        prescription=rx,
                        drug=drug,
                        quantity_dispensed=qty,
                        dispensed_by=request.user,
                        created_by=request.user,
                    )
                    if hasattr(rx, "is_dispensed"):
                        rx.is_dispensed = True
                        rx.save(update_fields=["is_dispensed"])

                    dispensed_names.append(f"{drug.name} ×{qty}")

                encounter.transition_to("COMPLETED", user=request.user)

            messages.success(
                request,
                f"Dispensed: {', '.join(dispensed_names)}. Visit completed.",
            )
            return redirect("pharmacy:pharmacy_queue")

        except Prescription.DoesNotExist:
            messages.error(request, "One of the selected items is invalid.")
        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Dispense failed: {e}")

        return redirect("pharmacy:dispense", encounter_id=encounter.pk)

    for rx in prescriptions:
        qty = rx.quantity or 1
        rx.already_dispensed = DispenseRecord.objects.filter(prescription=rx).exists()
        rx.can_dispense = (
            not rx.already_dispensed
            and rx.drug.is_active
            and rx.drug.stock_quantity >= qty
            and not getattr(rx.drug, "is_expired", False)
        )

    drugs = Drug.objects.filter(is_active=True).order_by("name")

    context = _ctx(request)
    context.update({
        "encounter": encounter,
        "patient": encounter.patient,
        "prescriptions": prescriptions,
        "drugs": drugs,
    })
    return render(request, "pharmacy/dispense.html", context)


@login_required
@pharmacy_required
def inventory(request):
    show = request.GET.get("show", "active")
    qs = Drug.objects.all().order_by("name")
    if show == "active":
        qs = qs.filter(is_active=True)
    elif show == "inactive":
        qs = qs.filter(is_active=False)

    drugs = list(qs)
    today = timezone.localdate()
    soon = today + timedelta(days=90)

    low_count = expired_count = expiring_count = 0
    for d in drugs:
        if not d.is_active:
            continue
        if d.stock_quantity <= d.reorder_level:
            low_count += 1
        if d.expiry_date and d.expiry_date < today:
            expired_count += 1
        elif d.expiry_date and today <= d.expiry_date <= soon:
            expiring_count += 1

    context = _ctx(request)
    context.update({
        "drugs": drugs,
        "show": show,
        "low_count": low_count,
        "expired_count": expired_count,
        "expiring_count": expiring_count,
        "today": today,
        "soon": soon,
    })
    return render(request, "pharmacy/inventory.html", context)


@login_required
@pharmacy_required
def toggle_drug_active(request, drug_id):
    if request.method != "POST":
        return redirect("pharmacy:inventory")
    drug = get_object_or_404(Drug, pk=drug_id)
    drug.is_active = not drug.is_active
    drug.save(update_fields=["is_active", "updated_at"])
    messages.success(
        request,
        f"{drug.name} {'activated' if drug.is_active else 'deactivated'}.",
    )
    return redirect("pharmacy:inventory")


@login_required
@pharmacy_required
def stock_adjust(request, drug_id):
    drug = get_object_or_404(Drug, pk=drug_id)

    if request.method == "POST":
        adj_type = request.POST.get("adjustment_type", "IN")
        reason = request.POST.get("reason", "").strip()
        expiry_raw = request.POST.get("expiry_date", "").strip()

        try:
            qty = int(request.POST.get("quantity", "0"))
            if qty <= 0:
                raise ValueError("Quantity must be greater than zero.")
        except (TypeError, ValueError):
            messages.error(request, "Enter a valid quantity.")
            return redirect("pharmacy:stock_adjust", drug_id=drug.pk)

        try:
            with transaction.atomic():
                drug = Drug.objects.select_for_update().get(pk=drug.pk)
                if adj_type == "IN":
                    drug.stock_quantity += qty
                elif adj_type == "OUT":
                    if drug.stock_quantity < qty:
                        raise ValueError("Not enough stock to remove.")
                    drug.stock_quantity -= qty
                elif adj_type == "ADJUST":
                    drug.stock_quantity = qty
                else:
                    raise ValueError("Invalid adjustment type.")

                update_fields = ["stock_quantity", "updated_at"]
                if expiry_raw:
                    drug.expiry_date = datetime.strptime(expiry_raw, "%Y-%m-%d").date()
                    update_fields.append("expiry_date")

                drug.save(update_fields=update_fields)

                StockAdjustment.objects.create(
                    drug=drug,
                    adjustment_type=adj_type,
                    quantity=qty,
                    reason=reason,
                    performed_by=request.user,
                    created_by=request.user,
                )

            messages.success(
                request,
                f"{drug.name} stock updated. Current: {drug.stock_quantity}.",
            )
            return redirect("pharmacy:inventory")
        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Stock update failed: {e}")

        return redirect("pharmacy:stock_adjust", drug_id=drug.pk)

    context = _ctx(request)
    context["drug"] = drug
    return render(request, "pharmacy/stock_adjust.html", context)