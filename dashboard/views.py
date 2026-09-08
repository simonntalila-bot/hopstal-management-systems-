"""
dashboard/views.py
==================
Role homes, admin reports, doctor / lab / pharmacy monthly reports.
"""

import csv
import re
from collections import Counter
from datetime import datetime, time as dtime
from calendar import monthrange
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.utils import timezone

from accounts.decorators import role_required
from patients.models import Patient
from encounters.models import Encounter, VisitLog, Payment as VisitPayment
from laboratory.models import LabOrder


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _ctx(request):
    p = request.user.staff_profile
    return {
        "display_name": p.display_name,
        "role_display": p.get_role_display(),
        "role": p.role,
        "user": request.user,
    }


def _today():
    return timezone.localdate()


def _day_bounds(day=None):
    day = day or timezone.localdate()
    start = timezone.make_aware(datetime.combine(day, dtime.min))
    end = timezone.make_aware(datetime.combine(day, dtime.max))
    return start, end


def _payment_time_field():
    return "received_at" if hasattr(VisitPayment, "received_at") else "created_at"


def _revenue_stats(start=None, end=None):
    pay_field = _payment_time_field()
    qs = VisitPayment.objects.all()
    if start is not None and end is not None:
        qs = qs.filter(**{f"{pay_field}__range": (start, end)})
    elif start is not None:
        qs = qs.filter(**{f"{pay_field}__gte": start})
    total = qs.aggregate(total=Sum("amount"))["total"] or 0
    count = qs.count()
    return total, count


def _parse_date_range(request):
    today = timezone.localdate()
    raw_from = request.GET.get("from") or today.isoformat()
    raw_to = request.GET.get("to") or today.isoformat()
    try:
        d_from = datetime.strptime(raw_from, "%Y-%m-%d").date()
        d_to = datetime.strptime(raw_to, "%Y-%m-%d").date()
    except ValueError:
        d_from = d_to = today
    start = timezone.make_aware(datetime.combine(d_from, dtime.min))
    end = timezone.make_aware(datetime.combine(d_to, dtime.max))
    return d_from, d_to, start, end


def _payment_filter(start, end):
    field = _payment_time_field()
    return {f"{field}__range": (start, end)}


# ------------------------------------------------------------------
# Sex × age / keyword helpers
# ------------------------------------------------------------------
AGE_BANDS = [
    ("<1", 0, 0),
    ("1-4", 1, 4),
    ("5-9", 5, 9),
    ("10-14", 10, 14),
    ("15-19", 15, 19),
    ("20-24", 20, 24),
    ("25-29", 25, 29),
    ("30-34", 30, 34),
    ("35-39", 35, 39),
    ("40-44", 40, 44),
    ("45-49", 45, 49),
    (">=50", 50, 200),
]

DTC_KEYWORDS = [
    "diarrhoea", "diarrhea", "dtc", "gastroenteritis",
    "loose stool", "watery stool", "dysentery",
]

STI_KEYWORDS = [
    "sti", "std", "gonorrhoea", "gonorrhea", "syphilis", "chlamydia",
    "genital ulcer", "urethral discharge", "vaginal discharge",
    "trichomonas", "pid", "pelvic inflammatory",
]

MALARIA_KEYWORDS = [
    "malaria", "mrdt", "m.rdt", "rdt malaria", "bs for mps",
    "blood slide", "mps", "plasmodium", "malaria parasite",
]


def _age_band(age):
    if age is None:
        return "Unknown"
    for label, lo, hi in AGE_BANDS:
        if lo <= age <= hi:
            return label
    return "Unknown"


def _sex_label(gender):
    if gender == "M":
        return "M"
    if gender == "F":
        return "F"
    return "O"


def _text_matches(text, keywords):
    t = (text or "").lower()
    return any(k in t for k in keywords)


def _normalize_dx(text):
    t = (text or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t[:120] if t else ""


def _month_bounds(year, month):
    last = monthrange(year, month)[1]
    start = timezone.make_aware(datetime(year, month, 1, 0, 0, 0))
    end = timezone.make_aware(datetime(year, month, last, 23, 59, 59))
    return start, end


def _empty_sex_age_matrix():
    bands = [b[0] for b in AGE_BANDS] + ["Unknown"]
    return {
        "M": {b: 0 for b in bands},
        "F": {b: 0 for b in bands},
        "O": {b: 0 for b in bands},
    }


def _inc_matrix(matrix, patient):
    if patient is None:
        return
    sex = _sex_label(getattr(patient, "gender", None))
    band = _age_band(getattr(patient, "age", None))
    if sex not in matrix:
        sex = "O"
    if band not in matrix[sex]:
        band = "Unknown"
    matrix[sex][band] += 1


def _matrix_total(matrix):
    return sum(sum(bands.values()) for bands in matrix.values())


def _matrix_rows(matrix, band_labels):
    rows = []
    for sex in ("M", "F", "O"):
        cells = [matrix[sex].get(b, 0) for b in band_labels]
        rows.append({"sex": sex, "cells": cells, "total": sum(cells)})
    return rows


def _is_malaria_test(test):
    blob = f"{getattr(test, 'code', '')} {getattr(test, 'name', '')}".lower()
    return any(k in blob for k in MALARIA_KEYWORDS)


def _parse_year_month(request):
    today = timezone.localdate()
    try:
        year = int(request.GET.get("year") or today.year)
        month = int(request.GET.get("month") or today.month)
        if month < 1 or month > 12:
            month = today.month
    except (TypeError, ValueError):
        year, month = today.year, today.month
    return year, month, today


# ------------------------------------------------------------------
# Smart home
# ------------------------------------------------------------------
@login_required
def home(request):
    if not hasattr(request.user, "staff_profile") or not request.user.staff_profile:
        messages.error(request, "No staff profile assigned. Contact admin.")
        return redirect("login")

    role = request.user.staff_profile.role
    ROLE_HOME = {
        "ADMIN": "dashboard:admin_home",
        "RECEPTION": "dashboard:reception_home",
        "PHARMACY": "dashboard:pharmacy_home",
        "DOCTOR": "dashboard:doctor_home",
        "LAB": "dashboard:lab_home",
        "ULTRASOUND": "dashboard:ultrasound_home",
        "INJECTION": "dashboard:injection_home",
        "RCH": "dashboard:rch_home",
        "LABOUR_WARD": "dashboard:labour_home",
    }
    target = ROLE_HOME.get(role)
    if target:
        return redirect(target)
    return render(request, "dashboard/home.html", _ctx(request))


# ------------------------------------------------------------------
# Admin
# ------------------------------------------------------------------
@login_required
@role_required("ADMIN")
def admin_home(request):
    today = timezone.localdate()
    start, end = _day_bounds(today)

    total_patients = Patient.objects.filter(is_active=True).count()
    registered_today = Patient.objects.filter(created_at__range=(start, end)).count()
    visits_today = Encounter.objects.filter(created_at__range=(start, end)).count()
    payment_pending = Encounter.objects.filter(status="PAYMENT_PENDING").count()

    with_doctor = Encounter.objects.filter(
        current_department="DOCTOR",
        status__in=["IN_PROGRESS", "RESULTS_READY"],
    ).count()
    with_lab = Encounter.objects.filter(
        status="IN_PROGRESS", current_department="LAB"
    ).count()
    with_pharmacy = Encounter.objects.filter(
        status="IN_PROGRESS", current_department="PHARMACY"
    ).count()
    with_ultrasound = Encounter.objects.filter(
        status="IN_PROGRESS", current_department="ULTRASOUND"
    ).count()
    with_injection = Encounter.objects.filter(
        status="IN_PROGRESS", current_department="INJECTION"
    ).count()
    with_rch = Encounter.objects.filter(
        status="IN_PROGRESS", current_department="RCH"
    ).count()
    with_labour = Encounter.objects.filter(
        status="IN_PROGRESS", current_department="LABOUR_WARD"
    ).count()

    revenue_today, payment_count = _revenue_stats(start, end)
    month_start = timezone.make_aware(datetime(today.year, today.month, 1, 0, 0, 0))
    revenue_month, _ = _revenue_stats(start=month_start)
    revenue_all_time, payments_all_time = _revenue_stats()

    revenue_by_method = list(
        VisitPayment.objects.values("method")
        .annotate(total=Sum("amount"), n=Count("id"))
        .order_by("-total")
    )

    log_order = "-timestamp" if hasattr(VisitLog, "timestamp") else "-created_at"
    recent_logs = (
        VisitLog.objects.select_related("encounter__patient", "performed_by")
        .order_by(log_order)[:10]
    )

    context = _ctx(request)
    context.update({
        "today": today,
        "total_patients": total_patients,
        "registered_today": registered_today,
        "visits_today": visits_today,
        "payment_pending": payment_pending,
        "with_doctor": with_doctor,
        "with_lab": with_lab,
        "with_pharmacy": with_pharmacy,
        "with_ultrasound": with_ultrasound,
        "with_injection": with_injection,
        "with_rch": with_rch,
        "with_labour": with_labour,
        "revenue_today": revenue_today,
        "payment_count": payment_count,
        "revenue_month": revenue_month,
        "revenue_all_time": revenue_all_time,
        "payments_all_time": payments_all_time,
        "revenue_by_method": revenue_by_method,
        "recent_logs": recent_logs,
    })
    return render(request, "dashboard/admin_home.html", context)


@login_required
@role_required("ADMIN")
def platform_logs(request):
    log_order = "-timestamp" if hasattr(VisitLog, "timestamp") else "-created_at"
    pay_field = _payment_time_field()

    recent_logs = (
        VisitLog.objects.select_related("encounter__patient", "performed_by")
        .order_by(log_order)[:80]
    )
    recent_payments = (
        VisitPayment.objects.select_related("encounter__patient", "received_by")
        .order_by(f"-{pay_field}")[:40]
    )
    recent_lab = (
        LabOrder.objects.filter(status="RELEASED")
        .select_related("encounter__patient")
        .order_by("-released_at")[:25]
    )

    recent_dispenses = []
    try:
        from pharmacy.models import DispenseRecord
        recent_dispenses = list(
            DispenseRecord.objects.select_related(
                "drug", "encounter__patient", "dispensed_by"
            ).order_by("-dispensed_at")[:25]
        )
    except Exception:
        pass

    context = _ctx(request)
    context.update({
        "recent_logs": recent_logs,
        "recent_payments": recent_payments,
        "recent_lab": recent_lab,
        "recent_dispenses": recent_dispenses,
    })
    return render(request, "dashboard/platform_logs.html", context)


@login_required
@role_required("ADMIN")
def admin_reports(request):
    d_from, d_to, start, end = _parse_date_range(request)
    report = (request.GET.get("report") or "").strip().lower()
    fmt = (request.GET.get("format") or "").strip().lower()

    if report and fmt == "csv":
        return _export_report_csv(report, start, end, d_from, d_to)
    if report and fmt == "html":
        return _export_report_html(request, report, start, end, d_from, d_to)

    context = _ctx(request)
    context.update({
        "d_from": d_from,
        "d_to": d_to,
        "today": timezone.localdate(),
    })
    return render(request, "dashboard/admin_reports.html", context)


def _export_report_csv(report, start, end, d_from, d_to):
    response = HttpResponse(content_type="text/csv")
    filename = f"{report}_{d_from}_{d_to}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    w = csv.writer(response)
    pay_field = _payment_time_field()

    if report in ("revenue", "payments"):
        w.writerow([
            "Date", "Patient", "Patient ID", "Method",
            "Amount (TZS)", "Reference", "Received by",
        ])
        qs = (
            VisitPayment.objects.filter(**_payment_filter(start, end))
            .select_related("encounter__patient", "received_by")
            .order_by(f"-{pay_field}")
        )
        for p in qs:
            when = getattr(p, "received_at", None) or p.created_at
            pat = p.encounter.patient
            w.writerow([
                when.strftime("%Y-%m-%d %H:%M"),
                pat.full_name, pat.patient_id, p.method, p.amount,
                getattr(p, "reference", "") or "",
                str(p.received_by) if p.received_by else "",
            ])
        total = qs.aggregate(t=Sum("amount"))["t"] or 0
        w.writerow([])
        w.writerow(["TOTAL", "", "", "", total, "", ""])
    elif report == "visits":
        w.writerow(["Date", "Visit #", "Patient", "Patient ID", "Department", "Status"])
        qs = (
            Encounter.objects.filter(created_at__range=(start, end))
            .select_related("patient")
            .order_by("-created_at")
        )
        for e in qs:
            w.writerow([
                e.created_at.strftime("%Y-%m-%d %H:%M"), e.pk,
                e.patient.full_name, e.patient.patient_id,
                e.current_department, e.status,
            ])
    elif report == "stock":
        w.writerow([
            "Drug", "Strength", "Unit", "Stock", "Reorder level",
            "Unit price", "Active", "Expiry",
        ])
        try:
            from pharmacy.models import Drug
            for d in Drug.objects.all().order_by("name"):
                w.writerow([
                    d.name, d.strength or "", d.unit or "",
                    d.stock_quantity, d.reorder_level,
                    getattr(d, "unit_price", "") or "",
                    "Yes" if d.is_active else "No",
                    d.expiry_date.isoformat() if getattr(d, "expiry_date", None) else "",
                ])
        except Exception as ex:
            w.writerow([f"Error: {ex}"])
    else:
        w.writerow(["Unknown report type"])
    return response


def _export_report_html(request, report, start, end, d_from, d_to):
    rows = []
    title = report.replace("_", " ").title()
    total = None
    headers = ["Col1", "Col2", "Col3", "Col4"]
    pay_field = _payment_time_field()

    if report in ("revenue", "payments"):
        title = "Revenue / Payments"
        headers = ["When", "Patient", "Method", "Amount (TZS)"]
        qs = (
            VisitPayment.objects.filter(**_payment_filter(start, end))
            .select_related("encounter__patient", "received_by")
            .order_by(f"-{pay_field}")
        )
        total = qs.aggregate(t=Sum("amount"))["t"] or Decimal("0")
        for p in qs:
            when = getattr(p, "received_at", None) or p.created_at
            rows.append({
                "c1": when.strftime("%d %b %Y %H:%M"),
                "c2": p.encounter.patient.full_name,
                "c3": p.method,
                "c4": f"{p.amount:,.0f}",
            })
    elif report == "visits":
        title = "Visits"
        headers = ["When", "Patient", "Department", "Status"]
        qs = (
            Encounter.objects.filter(created_at__range=(start, end))
            .select_related("patient")
            .order_by("-created_at")
        )
        for e in qs:
            rows.append({
                "c1": e.created_at.strftime("%d %b %Y %H:%M"),
                "c2": e.patient.full_name,
                "c3": e.current_department,
                "c4": e.status,
            })
    elif report == "stock":
        title = "Pharmacy stock"
        headers = ["Drug", "Stock", "Reorder", "Unit price"]
        try:
            from pharmacy.models import Drug
            for d in Drug.objects.filter(is_active=True).order_by("name"):
                rows.append({
                    "c1": f"{d.name} {d.strength or ''}".strip(),
                    "c2": str(d.stock_quantity),
                    "c3": str(d.reorder_level),
                    "c4": str(getattr(d, "unit_price", "") or "—"),
                })
        except Exception:
            rows = []
    else:
        headers = ["Info", "", "", ""]
        rows = [{"c1": "Unknown report", "c2": "", "c3": "", "c4": ""}]

    context = _ctx(request)
    context.update({
        "title": title, "d_from": d_from, "d_to": d_to,
        "headers": headers, "rows": rows, "total": total,
        "clinic_name": "Argentina Dispensary",
    })
    return render(request, "dashboard/report_print.html", context)


# ------------------------------------------------------------------
# Doctor monthly report
# ------------------------------------------------------------------
@login_required
@role_required("DOCTOR", "ADMIN")
def doctor_report(request):
    year, month, today = _parse_year_month(request)
    start, end = _month_bounds(year, month)
    fmt = (request.GET.get("format") or "").strip().lower()

    from consultations.models import Consultation

    encounters = list(
        Encounter.objects.filter(created_at__range=(start, end))
        .select_related("patient")
        .order_by("created_at")
    )
    consults = list(
        Consultation.objects.filter(
            Q(encounter__created_at__range=(start, end))
            | Q(created_at__range=(start, end))
        )
        .select_related("encounter__patient", "doctor")
        .distinct()
    )

    matrix_visits = _empty_sex_age_matrix()
    matrix_patients = _empty_sex_age_matrix()
    matrix_dtc = _empty_sex_age_matrix()
    matrix_sti = _empty_sex_age_matrix()

    seen_patient_ids = set()
    for enc in encounters:
        pat = enc.patient
        _inc_matrix(matrix_visits, pat)
        if pat.pk not in seen_patient_ids:
            seen_patient_ids.add(pat.pk)
            _inc_matrix(matrix_patients, pat)

    dtc_case_rows, sti_case_rows = [], []
    disease_counter = Counter()

    for c in consults:
        pat = c.encounter.patient
        blob = " ".join([
            c.diagnosis or "",
            getattr(c, "secondary_diagnosis", None) or "",
            c.symptoms or "",
        ])
        primary = _normalize_dx(c.diagnosis) or _normalize_dx(
            getattr(c, "secondary_diagnosis", None)
        )
        if primary:
            disease_counter[primary] += 1

        if _text_matches(blob, DTC_KEYWORDS):
            _inc_matrix(matrix_dtc, pat)
            dtc_case_rows.append({
                "date": c.encounter.created_at,
                "patient": pat.full_name,
                "patient_id": pat.patient_id,
                "sex": _sex_label(pat.gender),
                "age": pat.age,
                "diagnosis": (c.diagnosis or "")[:200],
            })
        if _text_matches(blob, STI_KEYWORDS):
            _inc_matrix(matrix_sti, pat)
            sti_case_rows.append({
                "date": c.encounter.created_at,
                "patient": pat.full_name,
                "patient_id": pat.patient_id,
                "sex": _sex_label(pat.gender),
                "age": pat.age,
                "diagnosis": (c.diagnosis or "")[:200],
            })

    top_diseases = disease_counter.most_common(15)
    band_labels = [b[0] for b in AGE_BANDS] + ["Unknown"]
    summary = {
        "year": year,
        "month": month,
        "month_name": datetime(year, month, 1).strftime("%B %Y"),
        "total_visits": len(encounters),
        "unique_patients": len(seen_patient_ids),
        "opd_visits": len(encounters),
        "dtc_count": _matrix_total(matrix_dtc),
        "sti_count": _matrix_total(matrix_sti),
        "consult_count": len(consults),
    }

    if fmt == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="doctor_report_{year}_{month:02d}.csv"'
        )
        w = csv.writer(response)
        w.writerow(["Doctor monthly report", summary["month_name"]])
        w.writerow(["Total visits", summary["total_visits"]])
        w.writerow(["Patients", summary["unique_patients"]])
        w.writerow(["DTC", summary["dtc_count"]])
        w.writerow(["STI", summary["sti_count"]])
        w.writerow([])
        w.writerow(["Top diseases"])
        for i, (dx, n) in enumerate(top_diseases, 1):
            w.writerow([i, dx, n])
        return response

    context = _ctx(request)
    context.update({
        "summary": summary,
        "band_labels": band_labels,
        "visits_rows": _matrix_rows(matrix_visits, band_labels),
        "patients_rows": _matrix_rows(matrix_patients, band_labels),
        "dtc_matrix_rows": _matrix_rows(matrix_dtc, band_labels),
        "sti_matrix_rows": _matrix_rows(matrix_sti, band_labels),
        "dtc_case_rows": dtc_case_rows[:100],
        "sti_case_rows": sti_case_rows[:100],
        "top_diseases": top_diseases,
        "years": list(range(today.year, today.year - 5, -1)),
        "months": list(range(1, 13)),
        "clinic_name": "Argentina Dispensary",
    })
    if fmt == "html":
        return render(request, "dashboard/doctor_report_print.html", context)
    return render(request, "dashboard/doctor_report.html", context)


# ------------------------------------------------------------------
# Lab monthly report
# ------------------------------------------------------------------
@login_required
@role_required("LAB", "ADMIN")
def lab_report(request):
    year, month, today = _parse_year_month(request)
    start, end = _month_bounds(year, month)
    fmt = (request.GET.get("format") or "").strip().lower()

    from laboratory.models import LabOrderItem

    items = list(
        LabOrderItem.objects.filter(
            Q(order__created_at__range=(start, end))
            | Q(order__released_at__range=(start, end))
        )
        .select_related("test", "order", "order__encounter", "order__encounter__patient")
        .distinct()
    )

    matrix_patients = _empty_sex_age_matrix()
    matrix_tests = _empty_sex_age_matrix()
    matrix_malaria = _empty_sex_age_matrix()
    seen_patients = set()
    by_test = Counter()
    malaria_rows = []

    for item in items:
        pat = item.order.encounter.patient
        test = item.test
        _inc_matrix(matrix_tests, pat)
        if pat.pk not in seen_patients:
            seen_patients.add(pat.pk)
            _inc_matrix(matrix_patients, pat)
        key = f"{test.code} – {test.name}"
        by_test[key] += 1

        result = None
        try:
            result = item.result
        except Exception:
            result = None
        value = (result.value or "") if result else ""
        is_abnormal = bool(result.is_abnormal) if result else False

        if _is_malaria_test(test):
            _inc_matrix(matrix_malaria, pat)
            malaria_rows.append({
                "date": item.order.created_at,
                "patient": pat.full_name,
                "patient_id": pat.patient_id,
                "sex": _sex_label(pat.gender),
                "age": pat.age,
                "test": key,
                "value": value,
                "abnormal": is_abnormal,
            })

    malaria_positive = 0
    for r in malaria_rows:
        v = (r["value"] or "").lower()
        if r["abnormal"] or "positive" in v or v in ("pos", "+", "p", "reactive"):
            malaria_positive += 1

    band_labels = [b[0] for b in AGE_BANDS] + ["Unknown"]
    summary = {
        "year": year,
        "month": month,
        "month_name": datetime(year, month, 1).strftime("%B %Y"),
        "total_tests": len(items),
        "unique_patients": len(seen_patients),
        "malaria_tests": len(malaria_rows),
        "malaria_positive": malaria_positive,
        "orders_in_month": LabOrder.objects.filter(
            Q(created_at__range=(start, end)) | Q(released_at__range=(start, end))
        ).distinct().count(),
    }

    if fmt == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="lab_report_{year}_{month:02d}.csv"'
        )
        w = csv.writer(response)
        w.writerow(["Lab monthly report", summary["month_name"]])
        w.writerow(["Total tests", summary["total_tests"]])
        w.writerow(["Patients", summary["unique_patients"]])
        w.writerow(["Malaria tests", summary["malaria_tests"]])
        w.writerow(["Malaria positive", summary["malaria_positive"]])
        w.writerow([])
        w.writerow(["Test", "Count"])
        for name, n in by_test.most_common(30):
            w.writerow([name, n])
        return response

    context = _ctx(request)
    context.update({
        "summary": summary,
        "band_labels": band_labels,
        "tests_rows": _matrix_rows(matrix_tests, band_labels),
        "patients_rows": _matrix_rows(matrix_patients, band_labels),
        "malaria_matrix_rows": _matrix_rows(matrix_malaria, band_labels),
        "top_tests": by_test.most_common(30),
        "malaria_rows": malaria_rows[:100],
        "years": list(range(today.year, today.year - 5, -1)),
        "months": list(range(1, 13)),
        "clinic_name": "Argentina Dispensary",
    })
    if fmt == "html":
        return render(request, "dashboard/lab_report_print.html", context)
    return render(request, "dashboard/lab_report.html", context)


# ------------------------------------------------------------------
# Pharmacy monthly report
# ------------------------------------------------------------------
@login_required
@role_required("PHARMACY", "ADMIN")
def pharmacy_report(request):
    """
    Month: drugs dispensed + sex×age.
    Snapshot: low stock, out of stock, expiring (≤90 days).
    """
    year, month, today = _parse_year_month(request)
    start, end = _month_bounds(year, month)
    fmt = (request.GET.get("format") or "").strip().lower()

    from pharmacy.models import Drug, DispenseRecord

    dispenses = list(
        DispenseRecord.objects.filter(dispensed_at__range=(start, end))
        .select_related("drug", "encounter__patient", "dispensed_by")
        .order_by("-dispensed_at")
    )

    matrix_patients = _empty_sex_age_matrix()
    matrix_dispense = _empty_sex_age_matrix()
    seen_patients = set()
    by_drug_units = Counter()
    detail_rows = []

    for d in dispenses:
        pat = None
        if d.encounter_id:
            try:
                pat = d.encounter.patient
            except Exception:
                pat = None

        if pat is not None:
            _inc_matrix(matrix_dispense, pat)
            if pat.pk not in seen_patients:
                seen_patients.add(pat.pk)
                _inc_matrix(matrix_patients, pat)

        drug_label = str(d.drug)
        qty = d.quantity_dispensed or 0
        by_drug_units[drug_label] += qty

        detail_rows.append({
            "date": d.dispensed_at,
            "patient": pat.full_name if pat else "—",
            "patient_id": pat.patient_id if pat else "—",
            "sex": _sex_label(pat.gender) if pat else "O",
            "age": pat.age if pat else None,
            "drug": drug_label,
            "qty": qty,
        })

    drugs = list(Drug.objects.all().order_by("name"))
    low_stock = [
        d for d in drugs
        if d.is_active and d.stock_quantity <= (d.reorder_level or 0)
    ]
    out_stock = [d for d in drugs if d.is_active and d.stock_quantity <= 0]
    expiring = [
        d for d in drugs
        if d.is_active and d.expiry_date and (d.expiry_date - today).days <= 90
    ]

    band_labels = [b[0] for b in AGE_BANDS] + ["Unknown"]
    top_drugs = by_drug_units.most_common(30)

    summary = {
        "year": year,
        "month": month,
        "month_name": datetime(year, month, 1).strftime("%B %Y"),
        "dispense_events": len(dispenses),
        "unique_patients": len(seen_patients),
        "total_units": sum(by_drug_units.values()),
        "active_drugs": sum(1 for d in drugs if d.is_active),
        "low_stock_count": len(low_stock),
        "out_stock_count": len(out_stock),
        "expiring_count": len(expiring),
    }

    if fmt == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="pharmacy_report_{year}_{month:02d}.csv"'
        )
        w = csv.writer(response)
        w.writerow(["Pharmacy monthly report", summary["month_name"]])
        w.writerow(["Dispense events", summary["dispense_events"]])
        w.writerow(["Patients", summary["unique_patients"]])
        w.writerow(["Units dispensed", summary["total_units"]])
        w.writerow(["Low stock", summary["low_stock_count"]])
        w.writerow(["Out of stock", summary["out_stock_count"]])
        w.writerow(["Expiring ≤90 days", summary["expiring_count"]])
        w.writerow([])
        w.writerow(["Drug", "Units"])
        for name, units in top_drugs:
            w.writerow([name, units])
        w.writerow([])
        w.writerow(["Inventory"])
        w.writerow(["Drug", "Stock", "Reorder", "Active", "Expiry"])
        for d in drugs:
            w.writerow([
                f"{d.name} {d.strength or ''}".strip(),
                d.stock_quantity,
                d.reorder_level,
                "Yes" if d.is_active else "No",
                d.expiry_date.isoformat() if d.expiry_date else "",
            ])
        return response

    context = _ctx(request)
    context.update({
        "summary": summary,
        "band_labels": band_labels,
        "dispense_rows": _matrix_rows(matrix_dispense, band_labels),
        "patients_rows": _matrix_rows(matrix_patients, band_labels),
        "top_drugs": top_drugs,
        "detail_rows": detail_rows[:150],
        "low_stock": low_stock[:50],
        "out_stock": out_stock[:50],
        "expiring": expiring[:50],
        "years": list(range(today.year, today.year - 5, -1)),
        "months": list(range(1, 13)),
        "clinic_name": "Argentina Dispensary",
    })
    # Use same template for print if print file missing
    if fmt == "html":
        return render(request, "dashboard/pharmacy_report.html", context)
    return render(request, "dashboard/pharmacy_report.html", context)


# ------------------------------------------------------------------
# Role homes
# ------------------------------------------------------------------
@login_required
@role_required("RECEPTION", "ADMIN")
def reception_home(request):
    today = _today()
    start, end = _day_bounds(today)
    pay_field = _payment_time_field()
    revenue_today, payment_count = _revenue_stats(start, end)
    revenue_all_time, _ = _revenue_stats()
    recent_payments = (
        VisitPayment.objects.select_related("encounter__patient", "received_by")
        .order_by(f"-{pay_field}")[:10]
    )
    context = _ctx(request)
    context.update({
        "today": today,
        "registered_today": Patient.objects.filter(created_at__date=today).count(),
        "payment_pending": Encounter.objects.filter(status="PAYMENT_PENDING").count(),
        "total_patients": Patient.objects.filter(is_active=True).count(),
        "visits_today": Encounter.objects.filter(created_at__date=today).count(),
        "revenue_today": revenue_today,
        "payment_count": payment_count,
        "revenue_all_time": revenue_all_time,
        "recent_payments": recent_payments,
    })
    return render(request, "dashboard/reception_home.html", context)


@login_required
@role_required("PHARMACY", "ADMIN")
def pharmacy_home(request):
    waiting = Encounter.objects.filter(
        status="IN_PROGRESS", current_department="PHARMACY"
    ).count()
    low_stock = 0
    try:
        from pharmacy.models import Drug
        drugs = Drug.objects.filter(is_active=True)
        low_stock = sum(1 for d in drugs if d.stock_quantity <= (d.reorder_level or 0))
    except Exception:
        pass
    context = _ctx(request)
    context.update({"waiting": waiting, "low_stock": low_stock})
    return render(request, "dashboard/pharmacy_home.html", context)

# ------------------------------------------------------------------
# RCH monthly KPI report
# ------------------------------------------------------------------
@login_required
@role_required("RCH", "ADMIN")
def rch_report(request):
    """
    RCH KPIs for the selected month + sex × age on RCH visits.
    - Always counts Encounter with current_department=RCH
    - KPIs from visit notes keywords; optional rch.* models if present
    """
    year, month, today = _parse_year_month(request)
    start, end = _month_bounds(year, month)
    fmt = (request.GET.get("format") or "").strip().lower()

    rch_visits = list(
        Encounter.objects.filter(
            created_at__range=(start, end),
            current_department="RCH",
        ).select_related("patient")
    )

    matrix_visits = _empty_sex_age_matrix()
    matrix_patients = _empty_sex_age_matrix()
    seen = set()

    for e in rch_visits:
        _inc_matrix(matrix_visits, e.patient)
        if e.patient_id not in seen:
            seen.add(e.patient_id)
            _inc_matrix(matrix_patients, e.patient)

    kpis = {
        "rch_visits": len(rch_visits),
        "unique_clients": len(seen),
        "anc": 0,
        "pnc": 0,
        "fp": 0,
        "immunization": 0,
        "under5": 0,
    }

    for e in rch_visits:
        notes = (e.notes or "").lower()
        if any(x in notes for x in ("anc", "antenatal", "pregnancy")):
            kpis["anc"] += 1
        if any(x in notes for x in ("pnc", "postnatal", "post-natal")):
            kpis["pnc"] += 1
        if any(x in notes for x in ("family planning", "fp ", "contracept")):
            kpis["fp"] += 1
        if any(x in notes for x in ("immun", "vaccine", "vaccination")):
            kpis["immunization"] += 1
        age = e.patient.age
        if age is not None and age < 5:
            kpis["under5"] += 1

    # Optional dedicated RCH models (safe)
    try:
        from rch import models as rch_models
        for model_name, key in (
            ("ANCVisit", "anc"),
            ("ANCRegistration", "anc"),
            ("PNCVisit", "pnc"),
            ("FamilyPlanning", "fp"),
            ("Immunization", "immunization"),
        ):
            Model = getattr(rch_models, model_name, None)
            if Model is None:
                continue
            try:
                count = Model.objects.filter(created_at__range=(start, end)).count()
                if count:
                    kpis[key] = count
            except Exception:
                pass
    except Exception:
        pass

    band_labels = [b[0] for b in AGE_BANDS] + ["Unknown"]
    summary = {
        "year": year,
        "month": month,
        "month_name": datetime(year, month, 1).strftime("%B %Y"),
        **kpis,
    }

    if fmt == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="rch_report_{year}_{month:02d}.csv"'
        )
        w = csv.writer(response)
        w.writerow(["RCH KPI report", summary["month_name"]])
        for k, v in kpis.items():
            w.writerow([k, v])
        w.writerow([])
        w.writerow(["Sex × age – visits"])
        w.writerow(["Sex"] + band_labels + ["Total"])
        for sex in ("M", "F", "O"):
            row = [sex] + [matrix_visits[sex].get(b, 0) for b in band_labels]
            row.append(sum(matrix_visits[sex].values()))
            w.writerow(row)
        return response

    context = _ctx(request)
    context.update({
        "summary": summary,
        "kpis": kpis,
        "band_labels": band_labels,
        "visits_rows": _matrix_rows(matrix_visits, band_labels),
        "patients_rows": _matrix_rows(matrix_patients, band_labels),
        "years": list(range(today.year, today.year - 5, -1)),
        "months": list(range(1, 13)),
        "clinic_name": "Argentina Dispensary",
    })
    return render(request, "dashboard/rch_report.html", context)

# ------------------------------------------------------------------
# Labour monthly report
# ------------------------------------------------------------------
ABORTION_KEYWORDS = [
    "abortion", "miscarriage", "evacuate", "evacuation", "mva",
    "incomplete abortion", "post abort", "pac ",
]


@login_required
@role_required("LABOUR_WARD", "ADMIN")
def labour_report(request):
    """
    Labour ward monthly report:
    - Labour ward visits
    - Deliveries (from labour models if present, else labour-ward encounters)
    - Abortions (notes keywords + model hints)
    - Sex × age of mothers/clients
    """
    year, month, today = _parse_year_month(request)
    start, end = _month_bounds(year, month)
    fmt = (request.GET.get("format") or "").strip().lower()

    labour_visits = list(
        Encounter.objects.filter(
            created_at__range=(start, end),
            current_department="LABOUR_WARD",
        ).select_related("patient")
    )

    matrix_visits = _empty_sex_age_matrix()
    matrix_delivery = _empty_sex_age_matrix()
    matrix_abortion = _empty_sex_age_matrix()
    seen_clients = set()

    delivery_rows = []
    abortion_rows = []

    for e in labour_visits:
        pat = e.patient
        _inc_matrix(matrix_visits, pat)
        if pat.pk not in seen_clients:
            seen_clients.add(pat.pk)

        notes = (e.notes or "").lower()
        is_abort = _text_matches(notes, ABORTION_KEYWORDS)

        if is_abort:
            _inc_matrix(matrix_abortion, pat)
            abortion_rows.append({
                "date": e.created_at,
                "patient": pat.full_name,
                "patient_id": pat.patient_id,
                "sex": _sex_label(pat.gender),
                "age": pat.age,
                "detail": (e.notes or "")[:200] or "Abortion-related (notes)",
            })
        else:
            # Default labour-ward visit counted toward delivery activity
            _inc_matrix(matrix_delivery, pat)
            delivery_rows.append({
                "date": e.created_at,
                "patient": pat.full_name,
                "patient_id": pat.patient_id,
                "sex": _sex_label(pat.gender),
                "age": pat.age,
                "detail": (e.notes or "")[:200] or "Labour ward visit",
            })

    # Optional dedicated labour delivery records
    try:
        from labour import models as labour_models
        DeliveryModel = None
        for name in ("Delivery", "DeliveryRecord", "LabourDelivery"):
            if hasattr(labour_models, name):
                DeliveryModel = getattr(labour_models, name)
                break
        if DeliveryModel is not None:
            qs = DeliveryModel.objects.filter(created_at__range=(start, end))
            # Prefer delivery_at if field exists
            if hasattr(DeliveryModel, "delivery_at"):
                qs = DeliveryModel.objects.filter(
                    Q(created_at__range=(start, end))
                    | Q(delivery_at__range=(start, end))
                )
            for rec in qs.select_related():
                pat = None
                if hasattr(rec, "encounter") and rec.encounter_id:
                    try:
                        pat = rec.encounter.patient
                    except Exception:
                        pass
                if pat is None and hasattr(rec, "patient"):
                    pat = rec.patient
                if pat is None:
                    continue
                _inc_matrix(matrix_delivery, pat)
                delivery_rows.append({
                    "date": getattr(rec, "delivery_at", None) or getattr(rec, "created_at", None),
                    "patient": pat.full_name,
                    "patient_id": pat.patient_id,
                    "sex": _sex_label(pat.gender),
                    "age": pat.age,
                    "detail": str(rec)[:200],
                })
    except Exception:
        pass

    band_labels = [b[0] for b in AGE_BANDS] + ["Unknown"]
    summary = {
        "year": year,
        "month": month,
        "month_name": datetime(year, month, 1).strftime("%B %Y"),
        "labour_visits": len(labour_visits),
        "unique_clients": len(seen_clients),
        "deliveries": _matrix_total(matrix_delivery),
        "abortions": _matrix_total(matrix_abortion),
    }

    if fmt == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="labour_report_{year}_{month:02d}.csv"'
        )
        w = csv.writer(response)
        w.writerow(["Labour monthly report", summary["month_name"]])
        w.writerow(["Labour visits", summary["labour_visits"]])
        w.writerow(["Unique clients", summary["unique_clients"]])
        w.writerow(["Deliveries / labour activity", summary["deliveries"]])
        w.writerow(["Abortions", summary["abortions"]])
        w.writerow([])
        w.writerow(["Delivery / labour list"])
        w.writerow(["Date", "Patient", "ID", "Sex", "Age", "Detail"])
        for r in delivery_rows:
            w.writerow([
                r["date"].strftime("%Y-%m-%d %H:%M") if r["date"] else "",
                r["patient"], r["patient_id"], r["sex"], r["age"], r["detail"],
            ])
        w.writerow([])
        w.writerow(["Abortion list"])
        w.writerow(["Date", "Patient", "ID", "Sex", "Age", "Detail"])
        for r in abortion_rows:
            w.writerow([
                r["date"].strftime("%Y-%m-%d %H:%M") if r["date"] else "",
                r["patient"], r["patient_id"], r["sex"], r["age"], r["detail"],
            ])
        return response

    context = _ctx(request)
    context.update({
        "summary": summary,
        "band_labels": band_labels,
        "visits_rows": _matrix_rows(matrix_visits, band_labels),
        "delivery_rows_matrix": _matrix_rows(matrix_delivery, band_labels),
        "abortion_rows_matrix": _matrix_rows(matrix_abortion, band_labels),
        "delivery_rows": delivery_rows[:100],
        "abortion_rows": abortion_rows[:100],
        "years": list(range(today.year, today.year - 5, -1)),
        "months": list(range(1, 13)),
        "clinic_name": "Argentina Dispensary",
    })
    return render(request, "dashboard/labour_report.html", context)

@login_required
@role_required("DOCTOR", "ADMIN")
def doctor_home(request):
    waiting = Encounter.objects.filter(
        current_department="DOCTOR",
        status__in=["IN_PROGRESS", "RESULTS_READY"],
    ).count()
    results_ready = Encounter.objects.filter(
        current_department="DOCTOR", status="RESULTS_READY"
    ).count()
    context = _ctx(request)
    context.update({"waiting": waiting, "results_ready": results_ready})
    return render(request, "dashboard/doctor_home.html", context)


@login_required
@role_required("LAB", "ADMIN")
def lab_home(request):
    waiting = Encounter.objects.filter(
        status="IN_PROGRESS", current_department="LAB"
    ).count()
    context = _ctx(request)
    context["waiting"] = waiting
    return render(request, "dashboard/lab_home.html", context)


@login_required
@role_required("ULTRASOUND", "ADMIN")
def ultrasound_home(request):
    waiting = Encounter.objects.filter(
        status="IN_PROGRESS", current_department="ULTRASOUND"
    ).count()
    context = _ctx(request)
    context["waiting"] = waiting
    return render(request, "dashboard/ultrasound_home.html", context)


@login_required
@role_required("INJECTION", "ADMIN")
def injection_home(request):
    waiting = Encounter.objects.filter(
        status="IN_PROGRESS", current_department="INJECTION"
    ).count()
    context = _ctx(request)
    context["waiting"] = waiting
    return render(request, "dashboard/injection_home.html", context)


@login_required
@role_required("RCH", "ADMIN")
def rch_home(request):
    waiting = Encounter.objects.filter(
        status="IN_PROGRESS", current_department="RCH"
    ).count()
    context = _ctx(request)
    context["waiting"] = waiting
    return render(request, "dashboard/rch_home.html", context)


@login_required
@role_required("LABOUR_WARD", "ADMIN")
def labour_home(request):
    waiting = Encounter.objects.filter(
        status="IN_PROGRESS", current_department="LABOUR_WARD"
    ).count()
    context = _ctx(request)
    context["waiting"] = waiting
    return render(request, "dashboard/labour_home.html", context)