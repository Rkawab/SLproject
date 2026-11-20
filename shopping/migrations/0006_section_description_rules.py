"""ジャンル判定の優先ルール（冷凍優先・中華まんはパン側）を説明文へ反映する。

ジャンル管理画面で説明を編集済みのものは上書きせず、初期値のままのものだけ更新する。
"""

from django.db import migrations

# ジャンル名: (旧の初期説明, 新しい説明)
DESCRIPTIONS = {
    "肉・魚": (
        "精肉・鮮魚・干物・しらす・海藻・ハム/ベーコン・サラダチキン・刺身",
        "生鮮・冷蔵の肉と魚。精肉・鮮魚・干物・しらす・海藻・ハム/ベーコン・サラダチキン・刺身（冷凍品は冷凍食品）",
    ),
    "パン・麺・米": (
        "主食。パン・うどん・そば・ラーメン・パスタ・米・餅",
        "主食。パン・肉まん等の中華まん・うどん・そば・ラーメン・パスタ・米・餅",
    ),
    "調味料・加工食品": (
        "常温の食品。調味料・味噌・ドレッシング・鍋つゆ・缶詰・乾物・レトルト・油",
        "常温の食品。調味料・味噌・ドレッシング・鍋つゆ・缶詰・乾物・レトルト・油（冷凍品は冷凍食品、パン類・中華まんはパン・麺・米）",
    ),
    "冷凍食品": (
        "冷凍庫の物すべて。冷凍野菜・冷凍食品・アイス",
        "冷凍庫の物すべて。冷凍野菜・冷凍の唐揚げ/揚げ物/弁当おかず・アイス。名前やメモに「冷凍」と付く物は肉・魚等より優先してここ",
    ),
}


def apply(apps, schema_editor, forward=True):
    Section = apps.get_model("shopping", "Section")
    database = schema_editor.connection.alias
    for name, (old, new) in DESCRIPTIONS.items():
        before, after = (old, new) if forward else (new, old)
        Section.objects.using(database).filter(name=name, description=before).update(
            description=after
        )


def forwards(apps, schema_editor):
    apply(apps, schema_editor, forward=True)


def backwards(apps, schema_editor):
    apply(apps, schema_editor, forward=False)


class Migration(migrations.Migration):
    dependencies = [("shopping", "0005_drugstore_catalog")]

    operations = [migrations.RunPython(forwards, backwards)]
