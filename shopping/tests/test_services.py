from unittest.mock import patch

from django.db import IntegrityError
from django.utils import timezone

from shopping.matching import match_item, split_quantity_note
from shopping.models import Entry, Item
from shopping.services import (
    add_alias,
    add_to_list,
    complete_shopping,
    merge_items,
    register_item,
)

from .test_models import SeededTestCase


class ServiceTests(SeededTestCase):
    def test_matching(self):
        self.assertEqual(match_item("ネギ").item.name, "長ネギ")
        self.assertEqual(
            match_item("牛乳（スッキリカルシウム鉄）").item.name,
            "牛乳（スッキリカルシウム鉄）",
        )
        self.assertEqual(match_item("ヨーグルトの大きいの").kind, "maybe")
        self.assertEqual(match_item("お米").kind, "new")
        self.assertEqual(
            split_quantity_note("産後ブラ長袖:５枚"), ("産後ブラ長袖", "5枚", "")
        )
        self.assertEqual(
            split_quantity_note("全粒粉食パン6枚切り"), ("全粒粉食パン6枚切り", "", "")
        )

    def test_parentheses_in_middle_of_item_name(self):
        item = register_item("プレーン（低脂肪）ヨーグルト")
        for raw in [
            "プレーン（低脂肪）ヨーグルト2個",
            "プレーン(低脂肪)ヨーグルト:2個",
        ]:
            result = match_item(raw)
            self.assertEqual(result.kind, "exact")
            self.assertEqual(result.item.pk, item.pk)
            self.assertEqual(result.quantity, "2個")
            self.assertEqual(result.note, "")

    def test_add_duplicate_revive_complete(self):
        banana = self.item("バナナ")
        first = add_to_list(banana, quantity="2本", note="黄色")
        self.assertEqual(first.status, "added")
        duplicate = add_to_list(banana, quantity="3本")
        self.assertEqual(duplicate.status, "already_listed")
        self.assertEqual(duplicate.entry.quantity, "2本")
        first.entry.is_checked = True
        first.entry.checked_at = timezone.now()
        first.entry.save()
        self.assertEqual(add_to_list(banana).status, "revived")
        banana.refresh_from_db()
        self.assertEqual(banana.use_count, 2)
        self.assertEqual(banana.default_note, "黄色")
        self.assertEqual(Entry.objects.filter(completed_at__isnull=True).count(), 1)
        first.entry.refresh_from_db()
        self.assertIsNone(first.entry.checked_at)
        self.assertEqual(complete_shopping(), 0)

    def test_integrity_error_recovers_existing_entry(self):
        item = self.item("バナナ")
        existing = Entry.objects.create(item=item)
        # 同時リクエストが先に作成し、INSERTだけが一意制約に当たる状況。
        with patch("shopping.services.Entry.objects.select_for_update") as lock:
            lock.return_value.filter.return_value.first.return_value = None
            with patch(
                "shopping.services.Entry.objects.create", side_effect=IntegrityError
            ):
                result = add_to_list(item)
        self.assertEqual(result.entry.pk, existing.pk)
        self.assertEqual(result.status, "already_listed")

    def test_registration_collision_and_alias(self):
        self.assertEqual(register_item("ねぎ").pk, self.item("長ネギ").pk)
        item = register_item("お米")
        self.assertEqual(register_item("お米").pk, item.pk)
        add_alias(item, "白いお米")
        self.assertEqual(match_item("白いお米").item.pk, item.pk)

    def test_merge_transfers_history_aliases_counts_and_favorite(self):
        src, dst = register_item("お米"), register_item("白米")
        src.use_count, src.is_favorite = 4, True
        src.last_used_at = timezone.now()
        src.save()
        add_alias(src, "ライス")
        history = Entry.objects.create(item=src, completed_at=timezone.now())
        Entry.objects.create(item=src, quantity="5kg", note="無洗米")
        target = Entry.objects.create(item=dst)
        result = merge_items(src, dst)
        target.refresh_from_db()
        history.refresh_from_db()
        self.assertEqual((target.quantity, target.note), ("5kg", "無洗米"))
        self.assertEqual(history.item_id, dst.pk)
        self.assertEqual(result.use_count, 4)
        self.assertTrue(result.is_favorite)
        self.assertFalse(Item.objects.filter(pk=src.pk).exists())
        self.assertEqual(match_item("お米").item.pk, dst.pk)
        self.assertEqual(match_item("ライス").item.pk, dst.pk)

    def test_completion_store_includes_unspecified_but_not_other_store(self):
        a = Entry.objects.create(
            item=self.item("バナナ"),
            store=self.item("バナナ").default_store,
            is_checked=True,
        )
        b = Entry.objects.create(
            item=self.item("卵"), store=self.item("卵").default_store, is_checked=True
        )
        c = Entry.objects.create(item=self.item("爪切り"), is_checked=True)
        self.assertEqual(complete_shopping(a.store), 2)
        b.refresh_from_db()
        c.refresh_from_db()
        self.assertIsNone(b.completed_at)
        self.assertIsNotNone(c.completed_at)
