"""既存の編集内容を保持して、買い物先2件と日用品候補13件を追加する。"""

import unicodedata

from django.db import migrations
from django.db.models import Q

ITEMS = (
    ("トイレットペーパー", "といれっとぺーぱー", "1パック", ["トイレペーパー"]),
    (
        "ウェットティッシュ",
        "うぇっとてぃっしゅ",
        "1パック",
        ["ウエットティッシュ", "ウェットティシュ"],
    ),
    (
        "ティッシュペーパー",
        "てぃっしゅぺーぱー",
        "1パック",
        ["ティッシュ", "箱ティッシュ"],
    ),
    ("キッチンペーパー", "きっちんぺーぱー", "1パック", []),
    ("洗濯洗剤", "せんたくせんざい", "1個", ["洗濯用洗剤"]),
    ("柔軟剤", "じゅうなんざい", "1個", []),
    ("食器用洗剤", "しょっきようせんざい", "1本", ["台所用洗剤", "食器洗剤"]),
    ("ハンドソープ", "はんどそーぷ", "1本", []),
    ("シャンプー", "しゃんぷー", "1本", []),
    ("ボディソープ", "ぼでぃそーぷ", "1本", ["ボディーソープ"]),
    ("歯磨き粉", "はみがきこ", "1本", ["歯みがき粉", "ハミガキ粉"]),
    ("歯ブラシ", "はぶらし", "1本", ["ハブラシ"]),
    ("ゴミ袋", "ごみぶくろ", "1袋", []),
)


def name_key(text):
    text = unicodedata.normalize("NFKC", text)
    text = "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in text)
    return "".join(
        c
        for c in text
        if c == "ー" or (not c.isspace() and unicodedata.category(c)[0] not in "PSZC")
    ).lower()


def add_catalog(apps, schema_editor):
    database = schema_editor.connection.alias
    Store = apps.get_model("shopping", "Store")
    Section = apps.get_model("shopping", "Section")
    Item = apps.get_model("shopping", "Item")
    ItemAlias = apps.get_model("shopping", "ItemAlias")
    store, _ = Store.objects.using(database).get_or_create(
        name="ドラッグストア",
        defaults={"aliases": ["薬局", "ドラッグ"], "order": 3},
    )
    Store.objects.using(database).get_or_create(
        name="その他", defaults={"aliases": [], "order": 4}
    )
    section, _ = Section.objects.using(database).get_or_create(
        name="日用品",
        defaults={
            "order": 8,
            "description": "食品以外の家庭用品。洗剤・掃除・紙類・ラップ/袋・衛生用品・薬・シャンプー・電池・文具",
        },
    )
    for name, reading, quantity, aliases in ITEMS:
        keys = [name_key(value) for value in [name, *aliases]]
        if (
            Item.objects.using(database)
            .filter(Q(name=name) | Q(name_key__in=keys))
            .exists()
            or ItemAlias.objects.using(database).filter(alias_key__in=keys).exists()
        ):
            continue
        item = Item.objects.using(database).create(
            name=name,
            name_key=keys[0],
            name_reading=reading,
            section_id=section.pk,
            default_store_id=store.pk,
            tap_quantity=quantity,
        )
        for alias in aliases:
            key = name_key(alias)
            if not Item.objects.using(database).filter(name_key=key).exists():
                ItemAlias.objects.using(database).get_or_create(
                    alias_key=key, defaults={"item_id": item.pk, "alias": alias}
                )


class Migration(migrations.Migration):
    dependencies = [("shopping", "0004_item_name_reading")]
    operations = [migrations.RunPython(add_catalog, migrations.RunPython.noop)]
