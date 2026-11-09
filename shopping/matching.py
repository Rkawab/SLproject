import re
import unicodedata
from dataclasses import dataclass, field

from .models import Item
from .normalize import make_key

BRACKETS = re.compile(r"\(([^()]*)\)")
QUANTITY = re.compile(
    r"\s*([0-9]+(?:\.[0-9]+)?\s*(?:パック|切れ|kg|ml|個|玉|本|枚|足|つ|袋|g|L))\s*$",
    re.I,
)


def _parts(text):
    text = unicodedata.normalize("NFKC", text).strip()
    brackets = list(BRACKETS.finditer(text))
    notes = [match[1] for match in brackets]
    inside = {
        index for match in brackets for index in range(match.start(), match.end())
    }
    positions = [index for index in range(len(text)) if index not in inside]
    outside = "".join(text[index] for index in positions)
    quantity = ""
    removed = set()
    if ":" in outside:
        start = outside.rfind(":")
        quantity = outside[start + 1 :].strip()
        removed = set(positions[start:])
        outside = outside[:start]
    else:
        found = QUANTITY.search(outside)
        if found:
            quantity = found[1].replace(" ", "")
            removed = set(positions[found.start() : found.end()])
            outside = outside[: found.start()]
    # 括弧が品名の途中にあっても、括弧込み照合では元の位置を保つ。
    full_name = "".join(
        char for index, char in enumerate(text) if index not in removed
    ).strip()
    return outside.strip(), quantity, " / ".join(notes), full_name


def split_quantity_note(text):
    return _parts(text)[:3]


def exact_item(key):
    if not key:
        return None
    return (
        Item.objects.filter(name_key=key).first()
        or Item.objects.filter(aliases__alias_key=key).first()
    )


@dataclass
class MatchResult:
    kind: str
    item: Item | None = None
    candidates: list = field(default_factory=list)
    name: str = ""
    quantity: str = ""
    note: str = ""


def match_item(raw):
    name, quantity, note, full_name = _parts(raw)
    for candidate_name, keep_note in [(full_name, False), (name, True)]:
        item = exact_item(make_key(candidate_name))
        if item:
            canonical_notes = BRACKETS.findall(unicodedata.normalize("NFKC", item.name))
            matched_name_note = (
                not keep_note
                and note
                and all(part in canonical_notes for part in note.split(" / "))
            )
            return MatchResult(
                "exact",
                item,
                [],
                item.name,
                quantity,
                "" if matched_name_note else note,
            )
    key = make_key(name)
    candidates = []
    if key:
        for item in Item.objects.filter(is_hidden=False).prefetch_related("aliases"):
            keys = [item.name_key] + [a.alias_key for a in item.aliases.all()]
            if any(key in other or other in key for other in keys):
                candidates.append(item)
        candidates.sort(
            key=lambda item: (
                abs(len(item.name_key) - len(key)),
                -item.use_count,
                item.name,
            )
        )
    return MatchResult(
        "maybe" if candidates else "new", None, candidates[:3], name, quantity, note
    )
