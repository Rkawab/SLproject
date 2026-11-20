import io
import json
from unittest.mock import patch
from urllib.error import URLError

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

from shopping.classification import classify_section
from shopping.models import Item, Section
from shopping.services import register_item

from .test_models import SeededTestCase


def response_for(section_id, **overrides):
    payload = {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps({"section_id": section_id}),
                    }
                ],
            }
        ],
    }
    payload.update(overrides)
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


@override_settings(OPENAI_API_KEY="test-only-key", OPENAI_MODEL="gpt-4o-mini")
class ClassificationTests(SeededTestCase):
    def setUp(self):
        cache.clear()

    def test_valid_classification_schema_cache_and_no_api_for_existing_item(self):
        section = Section.objects.get(name="パン・麺・米")
        with patch(
            "shopping.classification.urlopen", return_value=response_for(section.pk)
        ) as api:
            self.assertEqual(classify_section("お米").pk, section.pk)
            self.assertEqual(classify_section("お米").pk, section.pk)
            api.assert_called_once()
            request = api.call_args.args[0]
            payload = json.loads(request.data)
            self.assertEqual(payload["model"], "gpt-4o-mini")
            self.assertFalse(payload["store"])
            self.assertEqual(api.call_args.kwargs["timeout"], 4)
            schema = payload["text"]["format"]["schema"]
            self.assertIn(section.pk, schema["properties"]["section_id"]["enum"])
        with patch("shopping.classification.urlopen") as api:
            self.assertEqual(register_item("バナナ").pk, self.item("バナナ").pk)
            api.assert_not_called()

    @override_settings(OPENAI_API_KEY="")
    def test_no_key_uses_fallback_without_network(self):
        with patch("shopping.classification.urlopen") as api:
            self.assertTrue(classify_section("お米").is_fallback)
            api.assert_not_called()

    def test_timeout_unknown_id_refusal_and_invalid_json_fall_back(self):
        with patch("shopping.classification.urlopen", side_effect=URLError("timeout")):
            self.assertTrue(classify_section("お米").is_fallback)
        for response in [
            response_for(99999),
            response_for(True),
            response_for(1, status="incomplete"),
            io.BytesIO(b"not json"),
            io.BytesIO(b'{"status":"completed","output":null}'),
        ]:
            cache.clear()
            with patch("shopping.classification.urlopen", return_value=response):
                self.assertTrue(classify_section("お米").is_fallback)

    @override_settings(OPENAI_MODEL="gpt-6-luna", OPENAI_REASONING_EFFORT="none")
    def test_note_and_reasoning_effort_are_sent(self):
        section = Section.objects.get(name="冷凍食品")
        with patch(
            "shopping.classification.urlopen", return_value=response_for(section.pk)
        ) as api:
            self.assertEqual(
                classify_section("むねから", "冷凍鶏むね唐揚げ").pk, section.pk
            )
            payload = json.loads(api.call_args.args[0].data)
        self.assertEqual(payload["model"], "gpt-6-luna")
        self.assertEqual(payload["reasoning"], {"effort": "none"})
        content = json.loads(payload["input"][1]["content"])
        self.assertEqual(
            content["item"], {"name": "むねから", "note": "冷凍鶏むね唐揚げ"}
        )
        # メモが違えば別判定としてキャッシュを分ける。
        with patch(
            "shopping.classification.urlopen", return_value=response_for(section.pk)
        ) as api:
            classify_section("むねから")
            api.assert_called_once()
            content = json.loads(
                json.loads(api.call_args.args[0].data)["input"][1]["content"]
            )
            self.assertEqual(content["item"], {"name": "むねから"})

    @override_settings(OPENAI_REASONING_EFFORT="")
    def test_empty_reasoning_effort_is_not_sent(self):
        section = Section.objects.get(name="パン・麺・米")
        with patch(
            "shopping.classification.urlopen", return_value=response_for(section.pk)
        ) as api:
            classify_section("お米")
            self.assertNotIn("reasoning", json.loads(api.call_args.args[0].data))

    def test_extra_output_text_does_not_break_parsing(self):
        section = Section.objects.get(name="パン・麺・米")
        payload = {
            "status": "completed",
            "output": [
                {"type": "reasoning", "summary": []},
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps({"section_id": section.pk}),
                        }
                    ],
                },
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "補足"}],
                },
            ],
        }
        response = io.BytesIO(json.dumps(payload).encode("utf-8"))
        with patch("shopping.classification.urlopen", return_value=response):
            self.assertEqual(classify_section("肉まん").pk, section.pk)

    def test_manual_input_note_is_used_for_classification(self):
        self.client.force_login(User.objects.create_user("note-user"))
        section = Section.objects.get(name="冷凍食品")
        with patch(
            "shopping.classification.urlopen", return_value=response_for(section.pk)
        ) as api:
            response = self.client.post(
                reverse("shopping:api-add"),
                json.dumps(
                    {"raw": "むねから（冷凍鶏むね唐揚げ）", "auto_register": True}
                ),
                content_type="application/json",
            )
            content = json.loads(
                json.loads(api.call_args.args[0].data)["input"][1]["content"]
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(content["item"]["note"], "冷凍鶏むね唐揚げ")
        item = Item.objects.get(pk=response.json()["item"]["id"])
        self.assertEqual((item.name, item.section_id), ("むねから", section.pk))

    def test_manual_section_overrides_ai(self):
        section = Section.objects.get(name="パン・麺・米")
        with patch("shopping.classification.urlopen") as api:
            self.assertEqual(
                register_item("お米", section=section).section_id, section.pk
            )
            api.assert_not_called()

    def test_new_manual_input_is_auto_registered_once(self):
        self.client.force_login(User.objects.create_user("ai-user"))
        section = Section.objects.get(name="パン・麺・米")
        with patch(
            "shopping.classification.urlopen", return_value=response_for(section.pk)
        ) as api:
            response = self.client.post(
                reverse("shopping:api-add"),
                json.dumps({"raw": "お米", "auto_register": True}),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["auto_registered"])
            self.assertEqual(data["item"]["section_id"], section.pk)
            self.assertEqual(data["entry"]["quantity"], "1個")
            item = Item.objects.get(pk=data["item"]["id"])
            self.client.post(
                reverse("shopping:api-add"),
                json.dumps({"item_id": item.pk}),
                content_type="application/json",
            )
            api.assert_called_once()
        self.assertEqual(Item.objects.count(), self.seed_item_count + 1)

    def test_line_new_item_only_suggests_category_before_confirmation(self):
        self.client.force_login(User.objects.create_user("paste-ai"))
        section = Section.objects.get(name="パン・麺・米")
        with patch(
            "shopping.classification.urlopen", return_value=response_for(section.pk)
        ):
            response = self.client.post(
                reverse("shopping:paste-preview"), {"text": "お米"}
            )
        self.assertEqual(response.status_code, 200)
        row = response.context["rows"][0]
        self.assertEqual(row["form"].initial["section"].pk, section.pk)
        self.assertEqual(Item.objects.count(), self.seed_item_count)
