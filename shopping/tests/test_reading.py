from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth.models import User
from django.db import connection
from django.urls import reverse

from shopping.forms import ItemForm
from shopping.models import Item, Section
from shopping.reading import item_sort_key, reading_for_name, reading_sort_key

from .test_models import SeededTestCase


class ReadingTests(SeededTestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user("reading-user"))

    def test_kanji_kana_and_long_vowels_use_reading_order(self):
        for name, reading in [
            ("牛乳", "ぎゅうにゅう"),
            ("卵", "たまご"),
            ("納豆", "なっとう"),
            ("長ネギ", "ながねぎ"),
            ("味付きめかぶ", "あじつきめかぶ"),
            ("魚の干物", "さかなのひもの"),
        ]:
            with self.subTest(name=name):
                self.assertEqual(reading_for_name(name), reading)
                self.assertEqual(self.item(name).name_reading, reading)
        names = ["なっとう", "たまご", "ぎゅうにゅう", "きゅうり", "えのき"]
        self.assertEqual(
            sorted(names, key=reading_sort_key),
            ["えのき", "ぎゅうにゅう", "きゅうり", "たまご", "なっとう"],
        )
        self.assertEqual(reading_sort_key("ﾊﾞﾅﾅ"), reading_sort_key("ばなな"))
        self.assertEqual(
            sorted(["こしょう", "コーヒー", "こうちゃ"], key=reading_sort_key),
            ["こうちゃ", "コーヒー", "こしょう"],
        )

    def test_reading_edit_blank_and_rename(self):
        item = self.item("牛乳")
        item.name_reading = "ミルク"
        item.save()
        item.refresh_from_db()
        self.assertEqual(item.name_reading, "みるく")
        item.default_note = "いつもの"
        item.save(update_fields=["default_note"])
        item.refresh_from_db()
        self.assertEqual(item.name_reading, "みるく")
        item.name_reading = ""
        item.save(update_fields=["name_reading"])
        item.refresh_from_db()
        self.assertEqual(item.name_reading, "ぎゅうにゅう")
        item.name = "豆乳"
        item.save(update_fields=["name"])
        item.refresh_from_db()
        self.assertEqual(item.name_reading, "とうにゅう")

    def test_form_can_correct_a_reading_while_renaming(self):
        item = self.item("牛乳")
        form = ItemForm(
            {
                "name": "飲む牛乳",
                "name_reading": "ミルク",
                "section": item.section_id,
                "tap_quantity": item.tap_quantity,
            },
            instance=item,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        item.refresh_from_db()
        self.assertEqual(item.name_reading, "みるく")

    def test_categories_ignore_favorites_and_frequency_but_frequent_keeps_them(self):
        section = Section.objects.get(name="その他")
        expected = ["えのき", "牛乳", "卵", "納豆", "バナナ"]
        for name in expected:
            item = self.item(name if name != "えのき" else "エノキ")
            item.section = section
            item.save()
        favorite = self.item("バナナ")
        favorite.is_favorite = True
        favorite.use_count = 100
        favorite.save()
        expected[0] = "エノキ"
        for url in ("shopping:add", "shopping:items"):
            response = self.client.get(reverse(url))
            displayed = next(
                s for s in response.context["sections"] if s.pk == section.pk
            )
            self.assertEqual([i.name for i in displayed.page_items], expected)
            if url == "shopping:add":
                self.assertEqual(response.context["frequent"][0].pk, favorite.pk)
                self.assertContains(response, 'id="clear-selection"')

    def test_api_sort_key_matches_new_item_and_entry(self):
        item = self.item("牛乳")
        response = self.client.post(
            reverse("shopping:api-add"),
            '{"item_id":%d}' % item.pk,
            content_type="application/json",
        )
        payload = response.json()
        self.assertEqual(payload["item"]["name_reading"], "ぎゅうにゅう")
        self.assertEqual(payload["item"]["sort_key"], item_sort_key(item)[0])
        self.assertEqual(payload["entry"]["sort_key"], payload["item"]["sort_key"])

    def test_backfill_preserves_existing_data_and_manual_readings(self):
        item = self.item("牛乳")
        Item.objects.filter(pk=item.pk).update(
            name_reading="", default_note="保持するメモ"
        )
        custom = self.item("納豆")
        Item.objects.filter(pk=custom.pk).update(name_reading="てづくりなっとう")
        migration = import_module("shopping.migrations.0004_item_name_reading")
        migration.fill_readings(apps, SimpleNamespace(connection=connection))
        item.refresh_from_db()
        custom.refresh_from_db()
        self.assertEqual(item.name_reading, "ぎゅうにゅう")
        self.assertEqual(item.default_note, "保持するメモ")
        self.assertEqual(custom.name_reading, "てづくりなっとう")
