"""
hms_project/urls.py
==================
Root URL configuration for Argentina Dispensary (CDMS).
Includes auth, password reset, and all app routes.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path, re_path
from django.views.static import serve

urlpatterns = [
    path("admin/", admin.site.urls),

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path(
        "accounts/logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),

    # ------------------------------------------------------------------
    # Password reset (Forgot password)
    # ------------------------------------------------------------------
    path(
        "accounts/password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="registration/password_reset_form.html",
            email_template_name="registration/password_reset_email.html",
            subject_template_name="registration/password_reset_subject.txt",
            success_url="/accounts/password-reset/done/",
        ),
        name="password_reset",
    ),
    path(
        "accounts/password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "accounts/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
            success_url="/accounts/reset/done/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "accounts/reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),

    # ------------------------------------------------------------------
    # App routes
    # ------------------------------------------------------------------
    path("", include("dashboard.urls")),
    path("patients/", include("patients.urls")),
    path("encounters/", include("encounters.urls")),
    path("consultations/", include("consultations.urls")),
    path("laboratory/", include("laboratory.urls")),
    path("pharmacy/", include("pharmacy.urls")),
    path("ultrasound/", include("ultrasound.urls")),
    path("injection/", include("injection.urls")),
    path("rch/", include("rch.urls")),
    path("labour/", include("labour.urls")),
]

if settings.USING_S3_STORAGE:
    # Uploads are served straight from the object store / CDN. No Django URL
    # is needed, so no route is registered here.
    pass
elif settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # Local disk in production (e.g. a VPS with a persistent volume and no
    # nginx block yet). This keeps uploads reachable with DEBUG=False instead
    # of 404-ing every patient document, QR code and ultrasound image.
    # On the VPS, serve /media/ with nginx and this block becomes redundant.
    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$",
            serve,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]
