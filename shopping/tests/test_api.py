import json

from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.urls import reverse

from shopping.models import Entry, Section

from .test_models import SeededTestCase


class ApiTests(SeededTestCase):
    def setUp(self):
        self.a = User.objects.create_user("wife", password="test-pass-123")
        self.b = User.objects.create_user("husband", password="test-pass-123")
        self.client.force_login(self.a)
        self.other = Client()
        self.other.force_login(self.b)

    def post(self, name, data, args=None):
        return self.client.post(
            reverse(name, args=args), json.dumps(data), content_type="application/json"
        )

    def test_auth_methods_and_csrf(self):
        self.assertEqual(Client().get(reverse("shopping:list")).status_code, 302)
        self.assertEqual(Client().get(reverse("shopping:api-entries")).status_code, 401)
        self.assertEqual(self.client.get(reverse("shopping:api-add")).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.a)
        self.assertEqual(
            csrf_client.post(
                reverse("shopping:api-add"), "{}", content_type="application/json"
            ).status_code,
            403,
        )

    def test_two_users_share_check_and_delete(self):
        result = self.post("shopping:api-add", {"raw": "納豆2パック"}).json()
        entry = result["entry"]
        self.assertEqual(result["status"], "added")
        self.assertEqual(
            len(self.other.get(reverse("shopping:api-entries")).json()["entries"]), 1
        )
        for _ in range(2):
            self.other.post(
                entry["toggle_url"],
                json.dumps({"checked": True}),
                content_type="application/json",
            )
        saved = Entry.objects.get(pk=entry["id"])
        self.assertTrue(saved.is_checked)
        self.assertEqual(saved.checked_by, self.b)
        self.post("shopping:api-delete", {}, [saved.pk])
        self.assertEqual(
            self.other.get(reverse("shopping:api-entries")).json()["entries"], []
        )

    def test_validation_and_no_preview_registration(self):
        self.assertEqual(
            self.post("shopping:api-add", {"raw": "お米"}).json()["status"], "new"
        )
        self.assertEqual(
            self.post("shopping:api-add", {"raw": "ヨーグルトの大きいの"}).json()[
                "status"
            ],
            "maybe",
        )
        self.assertEqual(self.post("shopping:api-add", {"raw": ""}).status_code, 400)
        self.assertEqual(
            self.post("shopping:api-add", {"item_id": "bad"}).status_code, 400
        )

    def test_list_page_renders(self):
        response = self.client.get(reverse("shopping:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "残り")

    @override_settings(FORCE_SCRIPT_NAME="/shopping")
    def test_subpath_api_links(self):
        from django.urls import get_script_prefix, set_script_prefix

        before = get_script_prefix()
        set_script_prefix("/shopping/")
        try:
            # プロキシでサブパスを除いたPATH_INFOとSCRIPT_NAMEを再現する。
            result = self.client.post(
                "/api/add/",
                json.dumps({"raw": "バナナ"}),
                content_type="application/json",
                SCRIPT_NAME="/shopping",
            )
            self.assertTrue(
                result.json()["entry"]["toggle_url"].startswith("/shopping/")
            )
        finally:
            set_script_prefix(before)

    def test_manual_registration_suggestion_and_duplicate(self):
        self.assertContains(self.client.get(reverse("shopping:add")), "ジャンルに移動")
        first = self.post("shopping:api-add", {"raw": "ネギ"}).json()
        self.assertEqual(first["item"]["name"], "長ネギ")
        duplicate = self.post("shopping:api-add", {"raw": "ネギ2本"}).json()
        self.assertEqual(duplicate["status"], "already_listed")
        self.assertEqual(duplicate["requested"]["quantity"], "2本")
        section = Section.objects.get(name="パン・麺・米")
        result = self.post(
            "shopping:api-items", {"name": "お米", "section_id": section.pk}
        ).json()
        self.assertEqual(result["item"]["section_id"], section.pk)
        self.assertContains(self.client.get(reverse("shopping:add")), "お米")
        suggestions = self.client.get(
            reverse("shopping:api-suggest"), {"q": "ネギ"}
        ).json()["items"]
        self.assertEqual(suggestions[0]["name"], "長ネギ")
        self.assertEqual(suggestions[0]["alias"], "ネギ")
        self.assertLessEqual(len(suggestions), 5)
