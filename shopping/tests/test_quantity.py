import json
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.urls import reverse

from shopping.models import Entry, TapOperation
from shopping.quantity import change_quantity, default_tap_quantity, parse_quantity
from shopping.services import add_to_list, tap_item

from .test_models import SeededTestCase


class QuantityTests(SeededTestCase):
    def setUp(self):
        self.user = User.objects.create_user("quantity-user")
        self.client.force_login(self.user)

    def tap(self, item, action="increment", token=None, **kwargs):
        return tap_item(item, action, token or uuid4(), self.user, **kwargs)

    def test_units_and_grams(self):
        for current, step, want in [
            ("", "1個", "1個"),
            ("2パック", "1個", "3パック"),
            ("300g", "1個", "400g"),
            ("0.3kg", "100g", "0.4kg"),
            ("300g", "0.1kg", "400g"),
            ("２個", "1個", "3個"),
            ("2本", "1本", "3本"),
        ]:
            with self.subTest(current=current, step=step):
                self.assertEqual(change_quantity(current, step), want)
        self.assertEqual(parse_quantity("300G"), (Decimal(300), "g"))
        self.assertEqual(default_tap_quantity("鶏胸肉"), "100g")
        self.assertEqual(default_tap_quantity("牛乳"), "1個")
        self.assertEqual(default_tap_quantity("初めての品目", "500g"), "100g")

    def test_unstructured_quantity_is_not_silently_overwritten(self):
        item = self.item("バナナ")
        entry = Entry.objects.create(item=item, quantity="大きめのもの")
        with self.assertRaises(ValidationError):
            self.tap(item)
        entry.refresh_from_db()
        self.assertEqual(entry.quantity, "大きめのもの")
        self.assertEqual(TapOperation.objects.count(), 0)

    def test_repeated_taps_add_quantity_in_one_row_and_keep_metadata(self):
        item = self.item("納豆")
        first = self.tap(item)
        first.entry.note = "いつものもの"
        first.entry.save()
        second = self.tap(item)
        self.assertEqual(second.entry.quantity, "2パック")
        self.assertEqual(second.entry.note, "いつものもの")
        self.assertEqual(second.entry.store_id, item.default_store_id)
        self.assertEqual(Entry.objects.count(), 1)
        item.refresh_from_db()
        self.assertEqual(item.use_count, 1)

    def test_old_blank_quantity_means_one_existing_unit(self):
        item = self.item("納豆")
        Entry.objects.create(item=item, quantity="")
        self.assertEqual(self.tap(item).entry.quantity, "2パック")

    def test_grams_and_checked_item_revival(self):
        item = self.item("牛肉")
        for _ in range(3):
            result = self.tap(item)
        self.assertEqual(result.entry.quantity, "300g")
        result.entry.is_checked = True
        result.entry.save()
        result = self.tap(item)
        self.assertEqual(result.entry.quantity, "100g")
        self.assertFalse(result.entry.is_checked)
        self.assertEqual(Entry.objects.count(), 1)

    def test_request_replay_does_not_add_twice(self):
        item = self.item("バナナ")
        token = uuid4()
        self.tap(item, token=token)
        again = self.tap(item, token=token)
        self.assertEqual(again.status, "already_processed")
        self.assertEqual(again.entry.quantity, "1個")
        self.assertEqual(TapOperation.objects.count(), 1)
        with self.assertRaises(ValidationError):
            self.tap(item, "remove", token=token)

    def test_remove_restore_decrement_and_replay_after_removal(self):
        item = self.item("牛肉")
        added = self.tap(item, token=(token := uuid4()))
        self.tap(item)
        removed = self.tap(item, "remove")
        self.assertEqual(removed.previous["quantity"], "200g")
        self.assertFalse(Entry.objects.exists())
        self.assertIsNone(self.tap(item, token=token).entry)
        restored = self.tap(item, "restore", quantity="200g", note="鍋用")
        self.assertEqual(restored.entry.quantity, "200g")
        self.assertEqual(self.tap(item, "decrement").entry.quantity, "100g")
        self.assertIsNone(self.tap(item, "decrement").entry)
        self.assertFalse(Entry.objects.exists())
        self.assertIsNone(self.tap(item, "decrement").entry)
        self.assertIsNotNone(added.entry.pk)

    def test_restore_does_not_overwrite_other_users_new_entry(self):
        item = self.item("納豆")
        add_to_list(item, quantity="3パック")
        restored = self.tap(item, "restore", quantity="8パック")
        self.assertEqual(restored.status, "already_listed")
        self.assertEqual(restored.entry.quantity, "3パック")

    def test_api_request_ids_and_replays(self):
        item = self.item("牛肉")
        data = {"request_id": str(uuid4()), "action": "increment"}
        url = reverse("shopping:api-tap", args=[item.pk])
        for _ in range(2):
            response = self.client.post(
                url, json.dumps(data), content_type="application/json"
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["entry"]["quantity"], "100g")
        self.assertEqual(
            self.client.post(url, "{}", content_type="application/json").status_code,
            400,
        )
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_invalid_tap_quantity_model_validation(self):
        item = self.item("バナナ")
        item.tap_quantity = "0個"
        with self.assertRaises(ValidationError):
            item.save()
