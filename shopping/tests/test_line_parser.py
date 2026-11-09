import json
from pathlib import Path

from django.contrib.auth.models import User
from django.urls import reverse

from shopping.line_parser import parse_lines
from shopping.models import Entry, Item

from .test_models import SeededTestCase

SAMPLES = json.loads((Path(__file__).parent / "fixtures/line_samples.json").read_text())


class LineParserTests(SeededTestCase):
    def test_all_six_samples_every_line(self):
        self.assertEqual(len(SAMPLES), 6)
        for index, sample in enumerate(SAMPLES, 1):
            rows = parse_lines(sample["text"])
            self.assertEqual(len(rows), len(sample["expected"]), f"sample {index}")
            for row, expected in zip(rows, sample["expected"]):
                with self.subTest(sample=index, raw=row.raw):
                    self.assertEqual(row.kind, expected["kind"])
                    self.assertEqual(
                        row.store.name if row.store else None, expected["store"]
                    )
                    if row.match:
                        self.assertEqual(row.match.kind, expected["match"])
                        self.assertEqual(row.match.name, expected["name"])
                        self.assertEqual(row.match.quantity, expected["quantity"])
                        self.assertEqual(row.match.note, expected["note"])
                        if row.match.kind == "maybe":
                            self.assertEqual(row.match.candidates[0].name, "ヨーグルト")

    def test_boundaries(self):
        rows = parse_lines(
            " \n・バナナ\n□バナナ\n- バナナ2本（熟したもの）\nありがとう！\nよろしくね\nお米\n"
        )
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0].match.quantity, "2本")
        self.assertEqual(rows[0].match.note, "熟したもの")
        self.assertEqual(
            [r.kind for r in rows], ["item", "excluded", "excluded", "item"]
        )
        self.assertEqual(rows[-1].match.kind, "new")
        self.assertEqual(Item.objects.count(), 74)
        Entry.objects.create(item=self.item("納豆"))
        duplicate = parse_lines("納豆")[0]
        self.assertTrue(duplicate.duplicate)
        self.assertFalse(duplicate.include)
        Entry.objects.filter(item=self.item("納豆")).update(is_checked=True)
        self.assertTrue(parse_lines("納豆")[0].include)
        rows = parse_lines("★業スー\nバナナ\n帰りに以下をお願い\n牛乳")
        self.assertEqual(rows[1].store.name, "業務スーパー")
        self.assertIsNone(rows[3].store)

    def test_sample_one_preview_confirm_and_replay(self):
        self.client.force_login(User.objects.create_user("importer"))
        response = self.client.post(
            reverse("shopping:paste-preview"), {"text": SAMPLES[0]["text"]}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Item.objects.count(), 74)
        self.assertEqual(Entry.objects.count(), 0)
        data = {"action": "confirm", "token": self.client.session["paste_token"]}
        for index, row in enumerate(parse_lines(SAMPLES[0]["text"])):
            if row.match:
                data.update(
                    {
                        f"row-{index}-include": "on",
                        f"row-{index}-name": row.match.name,
                        f"row-{index}-quantity": row.match.quantity,
                        f"row-{index}-note": row.match.note,
                        f"row-{index}-store": str(row.store.pk) if row.store else "",
                        f"row-{index}-choice": "",
                        f"row-{index}-section": "",
                    }
                )
        self.assertEqual(
            self.client.post(reverse("shopping:paste-preview"), data).status_code, 302
        )
        self.assertEqual(Entry.objects.count(), 18)
        self.assertEqual(Item.objects.count(), 74)
        self.assertEqual(
            self.client.post(reverse("shopping:paste-preview"), data).status_code, 302
        )
        self.assertEqual(Entry.objects.count(), 18)
