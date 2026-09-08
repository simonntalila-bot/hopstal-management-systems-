from django.contrib import admin
from .models import Patient, PatientDocument


class PatientDocumentInline(admin.TabularInline):
    model = PatientDocument
    extra = 0
    fields = ("title", "document", "notes", "uploaded_by", "created_at")
    readonly_fields = ("created_at",)
    show_change_link = True


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = (
        "patient_id",
        "full_name",
        "gender",
        "phone",
        "is_nhif",
        "nhif_card_number",
        "insurance_number",
        "is_active",
        "created_at",
    )
    list_filter = ("gender", "is_active", "is_nhif", "created_at")
    search_fields = (
        "patient_id",
        "full_name",
        "phone",
        "insurance_number",
        "nhif_card_number",
    )
    readonly_fields = ("patient_id", "qr_code", "created_at", "updated_at", "created_by")
    inlines = [PatientDocumentInline]

    fieldsets = (
        (
            "Identity",
            {
                "fields": (
                    "patient_id",
                    "full_name",
                    "date_of_birth",
                    "gender",
                    "qr_code",
                )
            },
        ),
        (
            "Contact",
            {
                "fields": (
                    "phone",
                    "address",
                    "next_of_kin",
                    "next_of_kin_phone",
                )
            },
        ),
        (
            "Clinical",
            {
                "fields": (
                    "blood_group",
                    "allergies",
                    "chronic_conditions",
                )
            },
        ),
        (
            "Insurance / NHIF",
            {
                "fields": (
                    "is_nhif",
                    "nhif_card_number",
                    "insurance_number",
                )
            },
        ),
        (
            "Meta",
            {
                "fields": (
                    "is_active",
                    "notes",
                    "created_at",
                    "updated_at",
                    "created_by",
                )
            },
        ),
    )


@admin.register(PatientDocument)
class PatientDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "patient", "uploaded_by", "created_at")
    list_filter = ("created_at",)
    search_fields = ("title", "patient__patient_id", "patient__full_name")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("patient", "uploaded_by", "created_by")