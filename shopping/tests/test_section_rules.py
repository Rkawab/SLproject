import importlib
from types import SimpleNamespace

from django.apps import apps
from django.db import connection

from shopping.models import Section

from .test_models import SeededTestCase

migration = importlib.import_module(
    "shopping.migrations.0006_section_description_rules"
)


class SectionDescriptionRuleMigrationTests(SeededTestCase):
    def run_forwards(self):
        migration.forwards(apps, SimpleNamespace(connection=connection))

    def test_updates_only_untouched_initial_descriptions(self):
        old_frozen, new_frozen = migration.DESCRIPTIONS["冷凍食品"]
        old_bread, _ = migration.DESCRIPTIONS["パン・麺・米"]
        Section.objects.filter(name="冷凍食品").update(description=old_frozen)
        # ジャンル管理画面で編集済みの説明は上書きしない。
        Section.objects.filter(name="パン・麺・米").update(
            description="自分で書いた説明"
        )
        self.run_forwards()
        self.assertEqual(Section.objects.get(name="冷凍食品").description, new_frozen)
        self.assertEqual(
            Section.objects.get(name="パン・麺・米").description, "自分で書いた説明"
        )
        self.assertNotEqual(old_bread, "自分で書いた説明")

    def test_seed_matches_new_rules(self):
        for name, (_, new) in migration.DESCRIPTIONS.items():
            self.assertEqual(Section.objects.get(name=name).description, new)
