from django.contrib.auth.models import User
from django.urls import reverse

from shopping.models import Entry, Item, Section
from shopping.services import add_to_list, register_item

from .test_models import SeededTestCase


class ManagementTests(SeededTestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user("manager"))

    def test_new_section_move_entries_follow_and_delete(self):
        self.client.post(
            reverse("shopping:sections"),
            {"action": "add", "name": "洗剤・紙類", "description": "洗剤と紙"},
        )
        section = Section.objects.get(name="洗剤・紙類")
        item = self.item("綿棒")
        add_to_list(item)
        self.client.post(
            reverse("shopping:items"),
            {"action": "move", "section": section.pk, "item_ids": [item.pk]},
        )
        entry = Entry.objects.get(item=item)
        self.assertEqual(entry.item.section_id, section.pk)
        self.assertContains(self.client.get(reverse("shopping:add")), "洗剤・紙類")
        data = self.client.get(reverse("shopping:api-entries")).json()["entries"]
        self.assertEqual(data[0]["section"], "洗剤・紙類")
        response = self.client.post(
            reverse("shopping:sections"), {"action": "delete", "section_id": section.pk}
        )
        self.assertContains(response, "その他")
        self.assertTrue(Section.objects.filter(pk=section.pk).exists())
        self.client.post(
            reverse("shopping:sections"),
            {"action": "delete", "section_id": section.pk, "confirm": "yes"},
        )
        item.refresh_from_db()
        self.assertTrue(item.section.is_fallback)
        fallback = Section.objects.get(is_fallback=True)
        self.client.post(
            reverse("shopping:sections"),
            {"action": "delete", "section_id": fallback.pk, "confirm": "yes"},
        )
        self.assertTrue(Section.objects.filter(pk=fallback.pk).exists())

    def test_alias_collision_ui_and_merge(self):
        item = register_item("お米")
        target = register_item("白米")
        response = self.client.post(
            reverse("shopping:item-edit", args=[item.pk]),
            {"action": "alias-add", "alias": "白米"},
        )
        self.assertContains(response, "統合する")
        self.assertEqual(response.status_code, 200)
        self.client.post(
            reverse("shopping:item-merge", args=[item.pk]), {"target": target.pk}
        )
        self.assertFalse(Item.objects.filter(pk=item.pk).exists())
        self.assertEqual(target.aliases.get().alias, "お米")
        self.assertEqual(
            self.client.post(
                reverse("shopping:api-add"),
                '{"raw":"お米"}',
                content_type="application/json",
            ).json()["item"]["id"],
            target.pk,
        )

    def test_edit_and_favorite_hidden_reorder(self):
        item = self.item("バナナ")
        for action in ("favorite", "hidden"):
            self.client.post(
                reverse("shopping:items"), {"action": action, "item_id": item.pk}
            )
        item.refresh_from_db()
        self.assertTrue(item.is_favorite)
        self.assertTrue(item.is_hidden)
        first = Section.objects.filter(is_fallback=False).first()
        self.client.post(
            reverse("shopping:sections"), {"action": "down", "section_id": first.pk}
        )
        self.assertNotEqual(Section.objects.first().pk, first.pk)
        self.assertTrue(Section.objects.last().is_fallback)
        for name, args in [
            ("shopping:items", None),
            ("shopping:sections", None),
            ("shopping:item-edit", [item.pk]),
            ("shopping:item-merge", [item.pk]),
        ]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)
