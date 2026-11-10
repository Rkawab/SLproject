from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from shopping.models import Entry, Item, ItemAlias, Section, Store
from shopping.normalize import make_key


@override_settings(
    OPENAI_API_KEY="",
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
)
class SeededTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_seed", stdout=StringIO())

    def item(self, name):
        return Item.objects.get(name=name)


class ModelTests(SeededTestCase):
    def test_seed_is_idempotent_and_preserves_edits(self):
        banana = self.item("バナナ")
        banana.default_note = "好みの熟し具合"
        banana.save()
        call_command("load_seed", stdout=StringIO())
        self.assertEqual(
            (Store.objects.count(), Section.objects.count(), Item.objects.count()),
            (2, 10, 74),
        )
        banana.refresh_from_db()
        self.assertEqual(banana.default_note, "好みの熟し具合")

    def test_keys(self):
        for left, right in [
            ("しらす", "シラス"),
            ("ﾐﾆﾄﾏﾄ", "ミニトマト"),
            ("牛乳スッキリCa鉄", "牛乳スッキリca鉄"),
        ]:
            self.assertEqual(make_key(left), make_key(right))
        self.assertEqual(make_key(" ヨーグルト（大）・。 "), "ヨーグルト大")

    def test_cross_table_collisions(self):
        with self.assertRaises(ValidationError):
            Item.objects.create(name="ネギ", section=Section.objects.first())
        with self.assertRaises(ValidationError):
            ItemAlias.objects.create(item=self.item("バナナ"), alias="納豆")

    def test_one_open_entry_but_multiple_history(self):
        item = self.item("バナナ")
        Entry.objects.create(item=item)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Entry.objects.create(item=item)
        Entry.objects.create(item=item, completed_at=timezone.now())
        Entry.objects.create(item=item, completed_at=timezone.now())
        self.assertEqual(Entry.objects.filter(item=item).count(), 3)
