"""品目の読みと、環境に依存しない五十音順の比較キー。"""

import unicodedata
from functools import lru_cache

from pykakasi import kakasi

SMALL_KANA = str.maketrans("ぁぃぅぇぉっゃゅょゎゕゖ", "あいうえおつやゆよわかけ")
# 食材・初期品目で辞書が誤読する語を、変換前に読みへ置き換える。
READING_REPLACEMENTS = (
    ("長ネギ", "ながねぎ"),
    ("長ねぎ", "ながねぎ"),
    ("長葱", "ながねぎ"),
    ("味付き", "あじつき"),
    ("生みそ", "なまみそ"),
    ("生味噌", "なまみそ"),
    ("干物", "ひもの"),
    ("叙々苑", "じょじょえん"),
    ("腹巻き", "はらまき"),
)
VOWELS = {
    char: vowel
    for vowel, chars in (
        ("あ", "あかがさざただなはばぱまやらわぁゃゎゕ"),
        ("い", "いきぎしじちぢにひびぴみりぃゐ"),
        ("う", "うくぐすずつづぬふぶぷむゆるぅゅゔ"),
        ("え", "えけげせぜてでねへべぺめれぇゑゖ"),
        ("お", "おこごそぞとどのほぼぽもよろをぉょ"),
    )
    for char in chars
}


def normalize_reading(text):
    text = unicodedata.normalize("NFKC", text or "").strip().casefold()
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text)


@lru_cache(maxsize=1)
def _converter():
    return kakasi()


@lru_cache(maxsize=4096)
def reading_for_name(name):
    text = unicodedata.normalize("NFKC", name or "").strip()
    for word, reading in READING_REPLACEMENTS:
        text = text.replace(word, reading)
    return normalize_reading(
        "".join(part["hira"] for part in _converter().convert(text))
    )


def reading_sort_key(reading):
    normalized = normalize_reading(reading)
    primary, secondary = [], []
    previous = ""
    for char in normalized:
        if char == "ー":
            char = VOWELS.get(previous, char)
        elif unicodedata.category(char)[0] not in "LN":
            continue
        decomposed = unicodedata.normalize("NFD", char)
        base = decomposed[0]
        voice = (
            "2" if "\u309a" in decomposed else "1" if "\u3099" in decomposed else "0"
        )
        large = base.translate(SMALL_KANA)
        primary.append(large)
        secondary.append(voice + ("1" if large != base else "0"))
        previous = char
    return "".join(primary) + "\0" + "".join(secondary) + "\0" + normalized


def item_sort_key(item):
    return item.sort_key, item.pk or 0
