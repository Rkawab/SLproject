import json

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from shopping.models import Item, ItemAlias, Section, Store
from shopping.normalize import make_key


class Command(BaseCommand):
    help = "初期データを投入します。既存品目の編集内容は保持します。"

    @transaction.atomic
    def handle(self, *args, **options):
        data = json.loads(
            (settings.BASE_DIR / "seed/items.json").read_text(encoding="utf-8")
        )
        stores = {}
        for row in data["stores"]:
            values = row.copy()
            name = values.pop("name")
            stores[name], _ = Store.objects.get_or_create(name=name, defaults=values)
        sections = {}
        for row in data["sections"]:
            values = row.copy()
            name = values.pop("name")
            sections[name], _ = Section.objects.get_or_create(
                name=name, defaults=values
            )
        for row in data["items"]:
            if Item.objects.filter(name_key=make_key(row["name"])).exists():
                continue
            item = Item.objects.create(
                name=row["name"],
                section=sections[row["section"]],
                default_store=stores.get(row.get("store")),
                default_note=row.get("note", ""),
                default_quantity=row.get("quantity", ""),
            )
            for alias in row.get("aliases", []):
                ItemAlias.objects.create(item=item, alias=alias)
        self.stdout.write(
            f"店{Store.objects.count()}・ジャンル{Section.objects.count()}・品目{Item.objects.count()}"
        )
