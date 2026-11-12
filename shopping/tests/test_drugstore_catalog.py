import json
from importlib import import_module
from io import StringIO
from types import SimpleNamespace
from uuid import uuid4

from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import connection
from django.urls import reverse

from shopping.line_parser import parse_lines
from shopping.models import Entry, Item, ItemAlias, Store

from .test_models import SeededTestCase


class DrugstoreCatalogTests(SeededTestCase):
    def test_new_stores_and_daily_necessities_match_seed(self):
        self.assertEqual(
            list(Store.objects.values_list("name", flat=True)),
            ["業務スーパー", "イトーヨーカドー", "ドラッグストア", "その他"],
        )
        migration = import_module("shopping.migrations.0005_drugstore_catalog")
        seed = json.loads(
            (settings.BASE_DIR / "seed/items.json").read_text(encoding="utf-8")
        )
        seeded = {row["name"]: row for row in seed["items"]}
        self.assertEqual(len(migration.ITEMS), 13)
        for name, reading, quantity, aliases in migration.ITEMS:
            with self.subTest(name=name):
                item = self.item(name)
                self.assertEqual(item.default_store.name, "ドラッグストア")
                self.assertEqual(item.section.name, "日用品")
                self.assertEqual(item.tap_quantity, quantity)
                self.assertEqual(item.name_reading, reading)
                self.assertEqual(seeded[name]["name_reading"], reading)
                self.assertEqual(seeded[name]["tap_quantity"], quantity)
                self.assertEqual(
                    set(item.aliases.values_list("alias", flat=True)), set(aliases)
                )
        self.assertFalse(Entry.objects.exists())

    def test_migration_and_seed_preserve_custom_items_aliases_and_current_list(self):
        paper = self.item("トイレットペーパー")
        paper.default_store = Store.objects.get(name="業務スーパー")
        paper.default_note = "編集済みのメモ"
        paper.name_reading = "いつものぺーぱー"
        paper.is_favorite = True
        paper.save()
        entry = Entry.objects.create(
            item=paper,
            quantity="3パック",
            note="今週の買い物",
            store=paper.default_store,
        )
        self.item("ウェットティッシュ").delete()
        custom = Item.objects.create(
            name="携帯用ウェットシート",
            section=paper.section,
            default_store=paper.default_store,
        )
        ItemAlias.objects.create(item=custom, alias="ウェットティッシュ")
        counts = (
            Store.objects.count(),
            Item.objects.count(),
            ItemAlias.objects.count(),
        )
        migration = import_module("shopping.migrations.0005_drugstore_catalog")
        for _ in range(2):
            migration.add_catalog(apps, SimpleNamespace(connection=connection))
            call_command("load_seed", stdout=StringIO())
        self.assertEqual(
            (Store.objects.count(), Item.objects.count(), ItemAlias.objects.count()),
            counts,
        )
        paper.refresh_from_db()
        entry.refresh_from_db()
        self.assertEqual(paper.default_note, "編集済みのメモ")
        self.assertEqual(paper.default_store.name, "業務スーパー")
        self.assertEqual(paper.name_reading, "いつものぺーぱー")
        self.assertTrue(paper.is_favorite)
        self.assertFalse(Item.objects.filter(name="ウェットティッシュ").exists())
        self.assertEqual(custom.aliases.get().alias, "ウェットティッシュ")
        self.assertEqual(
            (Entry.objects.count(), entry.quantity, entry.note),
            (1, "3パック", "今週の買い物"),
        )

    def test_drugstore_and_other_headings_are_supported(self):
        rows = parse_lines("★薬局\nトイレットペーパー\n★その他\nウェットティッシュ")
        self.assertEqual(rows[1].store.name, "ドラッグストア")
        self.assertEqual(rows[3].store.name, "その他")
        self.assertEqual(rows[1].match.item.name, "トイレットペーパー")
        self.assertEqual(rows[3].match.item.name, "ウェットティッシュ")

    def test_store_tabs_and_default_store_when_tapping(self):
        self.client.force_login(User.objects.create_user("catalog-user"))
        response = self.client.get(reverse("shopping:list"))
        for name in ("ドラッグストア", "その他"):
            store = Store.objects.get(name=name)
            self.assertContains(response, f'data-store="{store.pk}"')
        item = self.item("トイレットペーパー")
        response = self.client.post(
            reverse("shopping:api-tap", args=[item.pk]),
            json.dumps({"action": "increment", "request_id": str(uuid4())}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["entry"]["store_id"], item.default_store_id)
        self.assertEqual(response.json()["entry"]["quantity"], "1パック")
