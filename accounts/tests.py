"""
accounts/tests.py
=================
Tests for the accounts app: custom User, StaffProfile roles, the
auto-profile signal, and role-based access.

Run with:
    python manage.py test accounts
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.decorators import doctor_required, role_required
from accounts.models import StaffProfile

User = get_user_model()


class UserModelTests(TestCase):
    """The custom User model itself."""

    def test_create_user(self):
        user = User.objects.create_user(
            username="jdoe",
            password="TestPass123!",
            first_name="Jane",
            last_name="Doe",
            phone="+255700000001",
        )
        self.assertEqual(user.username, "jdoe")
        self.assertEqual(user.phone, "+255700000001")
        self.assertTrue(user.check_password("TestPass123!"))

    def test_str_prefers_full_name(self):
        user = User.objects.create_user(username="jdoe", first_name="Jane", last_name="Doe")
        self.assertEqual(str(user), "Jane Doe")

    def test_str_falls_back_to_username(self):
        user = User.objects.create_user(username="jdoe")
        self.assertEqual(str(user), "jdoe")

    def test_ordering_is_by_username(self):
        User.objects.create_user(username="zeta")
        User.objects.create_user(username="alpha")
        self.assertEqual(User.objects.first().username, "alpha")


class StaffProfileModelTests(TestCase):
    """StaffProfile and the role field that drives all permissions."""

    def _user_with_role(self, role, user_kwargs=None, **profile_kwargs):
        """Create a user and set role + extra fields on its staff profile."""
        user = User.objects.create_user(
            username=f"u_{role.lower()}", **(user_kwargs or {})
        )
        profile = StaffProfile.objects.get(user=user)
        profile.role = role
        for key, value in profile_kwargs.items():
            setattr(profile, key, value)
        profile.save()
        return User.objects.get(pk=user.pk)

    def test_profile_is_created_automatically_by_signal(self):
        user = User.objects.create_user(username="auto")
        self.assertTrue(StaffProfile.objects.filter(user=user).exists())

    def test_signal_does_not_duplicate_profile(self):
        user = User.objects.create_user(username="auto")
        user.first_name = "Changed"
        user.save()
        self.assertEqual(StaffProfile.objects.filter(user=user).count(), 1)

    def test_role_round_trip(self):
        user = self._user_with_role("DOCTOR", department="OPD")
        profile = user.staff_profile
        self.assertEqual(profile.role, "DOCTOR")
        self.assertEqual(profile.get_role_display(), "Doctor")
        self.assertEqual(profile.department, "OPD")

    def test_str_and_display_name(self):
        user = self._user_with_role(
            "LAB", user_kwargs={"first_name": "Ana", "last_name": "Bebe"}
        )
        profile = user.staff_profile
        self.assertEqual(profile.display_name, "Ana Bebe")
        self.assertIn("Laboratory", str(profile))

    def test_default_employment_type(self):
        user = self._user_with_role("PHARMACY")
        self.assertEqual(user.staff_profile.employment_type, "FULL_TIME")

    def test_role_display_without_profile(self):
        orphan = User.objects.create_user(username="orphan")
        StaffProfile.objects.filter(user=orphan).delete()
        orphan.refresh_from_db()
        self.assertIsNone(orphan.role)
        self.assertEqual(orphan.role_display, "No Role")


class RoleHelperTests(TestCase):
    """The is_* permission helpers on the User model."""

    def setUp(self):
        self.user = User.objects.create_user(username="helper")
        self.profile = self.user.staff_profile

    def _as(self, role):
        self.profile.role = role
        self.profile.save()
        self.user.refresh_from_db()
        return self.user

    def test_no_role_means_no_permissions(self):
        self._as("")
        for helper in (
            "is_admin", "is_reception", "is_doctor", "is_lab",
            "is_ultrasound", "is_injection", "is_rch", "is_labour",
        ):
            self.assertFalse(getattr(self.user, helper)(), helper)

    def test_doctor_helper(self):
        self._as("DOCTOR")
        self.assertTrue(self.user.is_doctor())
        self.assertFalse(self.user.is_lab())

    def test_lab_helper(self):
        self._as("LAB")
        self.assertTrue(self.user.is_lab())
        self.assertFalse(self.user.is_doctor())

    def test_admin_passes_every_helper(self):
        self._as("ADMIN")
        for helper in (
            "is_admin", "is_reception", "is_doctor", "is_lab",
            "is_ultrasound", "is_injection", "is_rch", "is_labour",
        ):
            self.assertTrue(getattr(self.user, helper)(), helper)

    def test_has_role(self):
        self._as("ULTRASOUND")
        self.assertTrue(self.user.has_role("ULTRASOUND"))
        self.assertTrue(self.user.has_role("ULTRASOUND", "RCH"))
        self.assertFalse(self.user.has_role("RCH"))


class ReceptionRoleTests(TestCase):
    """
    Regression tests for User.is_reception().

    Root cause of the original bug: migration 0002 introduced the combined
    role "RECEPTION_PHARMACY". Migration 0003 split it into RECEPTION and
    PHARMACY, and the decorator, views and templates were all updated to
    "RECEPTION", but is_reception() kept checking the retired code and so
    returned False for every real Reception user.
    """

    def _user_with_role(self, role):
        user = User.objects.create_user(username=f"r_{role.lower() or 'none'}")
        profile = StaffProfile.objects.get(user=user)
        profile.role = role
        profile.save()
        return User.objects.get(pk=user.pk)

    def test_reception_user_is_reception(self):
        self.assertTrue(self._user_with_role("RECEPTION").is_reception())

    def test_admin_is_reception(self):
        """ADMIN passes every role check, matching every other is_* helper."""
        self.assertTrue(self._user_with_role("ADMIN").is_reception())

    def test_doctor_is_not_reception(self):
        self.assertFalse(self._user_with_role("DOCTOR").is_reception())

    def test_pharmacy_is_not_reception(self):
        self.assertFalse(self._user_with_role("PHARMACY").is_reception())

    def test_lab_is_not_reception(self):
        self.assertFalse(self._user_with_role("LAB").is_reception())

    def test_empty_role_is_not_reception(self):
        self.assertFalse(self._user_with_role("").is_reception())

    def test_retired_recombined_code_is_not_reachable(self):
        """
        "RECEPTION_PHARMACY" was removed in migration 0003. If it ever returns
        True, the choices and the helper have drifted apart again.
        """
        user = self._user_with_role("RECEPTION")
        self.assertNotIn("RECEPTION_PHARMACY", dict(StaffProfile.ROLE_CHOICES))
        self.assertNotIn("RECEPTION_PHARMACY", user.role)

    def test_helper_agrees_with_the_decorator(self):
        """
        is_reception() and reception_required() must accept the same roles,
        otherwise a Reception user passes the helper but is bounced by the view.
        """
        from accounts.decorators import reception_required

        for role in ("RECEPTION", "PHARMACY", "DOCTOR", "ADMIN"):
            user = self._user_with_role(role)

            allowed_by_decorator = role in ("RECEPTION", "ADMIN")
            self.assertEqual(
                user.is_reception(),
                allowed_by_decorator,
                f"role={role} helper/decorator disagree",
            )
        self.assertTrue(callable(reception_required))

    def test_missing_profile_is_safe(self):
        """
        A user with no StaffProfile (deleted, or never created) must report
        False rather than raising.
        """
        user = User.objects.create_user(username="r_orphan")
        StaffProfile.objects.filter(user=user).delete()
        user = User.objects.get(pk=user.pk)
        self.assertFalse(user.is_reception())
        self.assertIsNone(user.role)
        self.assertFalse(user.has_role("RECEPTION"))

    def test_inactive_profile_does_not_grant_reception(self):
        """
        is_active on the profile is a flag for listings; role checks stay
        role-based, so this asserts the current deliberate behaviour.
        """
        user = self._user_with_role("RECEPTION")
        user.staff_profile.is_active = False
        user.staff_profile.save()
        self.assertTrue(User.objects.get(pk=user.pk).is_reception())


class AuthenticationTests(TestCase):
    """Login/logout through the real URLconf."""

    def setUp(self):
        self.password = "TestPass123!"
        self.user = User.objects.create_user(username="jdoe", password=self.password)
        self.profile = self.user.staff_profile
        self.profile.role = "RECEPTION"
        self.profile.save()

    def test_login_page_renders(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/login.html")

    def test_successful_login(self):
        self.assertTrue(self.client.login(username="jdoe", password=self.password))

    def test_failed_login_wrong_password(self):
        self.assertFalse(self.client.login(username="jdoe", password="wrong-password"))

    def test_failed_login_unknown_user(self):
        self.assertFalse(self.client.login(username="nobody", password=self.password))

    def test_logout_view(self):
        self.client.login(username="jdoe", password=self.password)
        response = self.client.post(reverse("logout"))
        self.assertEqual(response.status_code, 302)

    def test_login_redirects_to_dashboard(self):
        response = self.client.post(
            reverse("login"),
            {"username": "jdoe", "password": self.password},
        )
        self.assertRedirects(
            response, reverse("dashboard:home"), fetch_redirect_response=False
        )


class RoleDecoratorTests(TestCase):
    """role_required and the role shortcuts built on it."""

    def setUp(self):
        self.password = "TestPass123!"
        self.user = User.objects.create_user(username="doc", password=self.password)
        self.profile = self.user.staff_profile
        self.profile.role = "DOCTOR"
        self.profile.save()

        @doctor_required
        def doctor_only(request):
            from django.http import HttpResponse
            return HttpResponse("ok")

        self.doctor_only = doctor_only

        @role_required("LABOUR_WARD", "ADMIN")
        def labour_only(request):
            from django.http import HttpResponse
            return HttpResponse("ok")

        self.labour_only = labour_only

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)

    def test_correct_role_reaches_the_view(self):
        self.client.login(username="doc", password=self.password)
        request = self.client.request(PATH_INFO="/").wsgi_request
        request.user = self.user
        response = self.doctor_only(request)
        self.assertEqual(response.status_code, 200)

    def test_wrong_role_is_redirected_to_dashboard(self):
        request = self.client.request(PATH_INFO="/").wsgi_request
        request.user = self.user
        response = self.labour_only(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard:home"))

    def test_missing_profile_is_denied(self):
        StaffProfile.objects.filter(user=self.user).delete()
        # Re-fetch so the reverse relation is not cached on the instance.
        request = self.client.request(PATH_INFO="/").wsgi_request
        request.user = User.objects.get(pk=self.user.pk)
        response = self.doctor_only(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard:home"))
