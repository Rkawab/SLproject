from django.db import migrations

# 過去のマイグレーションを再実行しても変わらないよう、初期値をここに固定する。
UNITS = {
    "豚肉しゃぶしゃぶ用": "100g",
    "牛肉": "100g",
    "焼くだけの味付き肉": "100g",
    "牛乳": "1本",
    "牛乳（スッキリカルシウム鉄）": "1本",
    "ビヒダス飲むヨーグルト 1日分の鉄分": "1本",
    "豆腐": "1パック",
    "納豆": "1パック",
    "うどん": "1玉",
    "骨取り鮭": "1切れ",
    "産後ブラ長袖": "1枚",
    "マタニティ腹巻きパンツ": "1枚",
    "短肌着": "1枚",
    "コンビ肌着": "1枚",
    "ベビー靴下": "1足",
    "哺乳瓶": "1本",
}


def set_units(apps, schema_editor):
    item = apps.get_model("shopping", "Item")
    for name, quantity in UNITS.items():
        item.objects.using(schema_editor.connection.alias).filter(
            name=name, tap_quantity="1個"
        ).update(tap_quantity=quantity)


class Migration(migrations.Migration):
    dependencies = [("shopping", "0002_item_tap_quantity_tapoperation")]
    operations = [migrations.RunPython(set_units, migrations.RunPython.noop)]
