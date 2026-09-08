"""
accounts/decorators.py
======================
Reusable role-based access control decorators.

Usage:
    @login_required
    @role_required("DOCTOR", "ADMIN")
    def my_view(request):
        ...
"""

from functools import wraps
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.contrib import messages


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("login")
            profile = getattr(request.user, "staff_profile", None)
            if not profile or profile.role not in roles:
                messages.error(request, "You do not have permission to access this page.")
                return redirect("dashboard:home")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def reception_required(view_func):
    return role_required("RECEPTION", "ADMIN")(view_func)


def pharmacy_required(view_func):
    return role_required("PHARMACY", "ADMIN")(view_func)


def doctor_required(view_func):
    return role_required("DOCTOR", "ADMIN")(view_func)


def lab_required(view_func):
    return role_required("LAB", "ADMIN")(view_func)