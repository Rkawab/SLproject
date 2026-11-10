import re
import unicodedata
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

from .normalize import make_key

PATTERN = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*(個|パック|玉|本|枚|足|切れ|つ|袋|房|缶|箱|組|セット|g|kg|ml|L)?\s*$",
    re.I,
)
WEIGHT = {"g": Decimal(1), "kg": Decimal(1000)}


def parse_quantity(text):
    match = PATTERN.fullmatch(unicodedata.normalize("NFKC", text or ""))
    if not match:
        raise ValidationError(
            "数量を「2個」「300g」のように編集してから追加してください。"
        )
    try:
        amount = Decimal(match[1])
    except InvalidOperation as exc:
        raise ValidationError("数量を確認してください。") from exc
    unit = match[2] or "個"
    unit = (
        unit.lower()
        if unit.lower() in {"g", "kg", "ml"}
        else ("L" if unit.lower() == "l" else unit)
    )
    if amount < 0 or amount > 1000000:
        raise ValidationError("数量は1000000以下にしてください。")
    return amount, unit


def format_quantity(amount, unit):
    return f"{format(amount, 'f').rstrip('0').rstrip('.') if '.' in format(amount, 'f') else format(amount, 'f')}{unit}"


def default_tap_quantity(name, quantity=""):
    if quantity:
        try:
            _, unit = parse_quantity(quantity)
            return "100g" if unit in WEIGHT else f"1{unit}"
        except ValidationError:
            pass
    key = make_key(name)
    if key.endswith("肉") or key in {
        make_key("豚肉しゃぶしゃぶ用"),
        make_key("鶏もも"),
        make_key("鶏むね"),
    }:
        return "100g"
    return "1個"


def change_quantity(current, tap_quantity, direction=1):
    step, step_unit = parse_quantity(tap_quantity)
    if step <= 0:
        raise ValidationError("1タップの数量は0より大きくしてください。")
    if current:
        amount, unit = parse_quantity(current)
        if unit in WEIGHT:
            # 手入力でg/kgを指定した品目も、以降は基本100gずつ。
            grams = step * WEIGHT[step_unit] if step_unit in WEIGHT else Decimal(100)
            step = grams / WEIGHT[unit]
        elif step_unit != unit:
            step = Decimal(1)
    else:
        amount, unit = Decimal(0), step_unit
    amount += step * direction
    if amount <= 0:
        return ""
    if amount > 1000000:
        raise ValidationError("数量は1000000以下にしてください。")
    return format_quantity(amount, unit)
