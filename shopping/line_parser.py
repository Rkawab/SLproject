import re
from dataclasses import dataclass

from .matching import MatchResult, match_item
from .models import Entry, Store
from .normalize import make_key

REQUEST_KEYWORDS = (
    "以下",
    "お願い",
    "もらえ",
    "もらって",
    "くれる",
    "行くなら",
    "かな？",
    "かな?",
    "ごめん",
)
GREETING_KEYWORDS = ("ありがとう", "大丈夫", "よろしく")
HEADING_PREFIXES = ("★", "■", "【")
HEADING_SUFFIXES = ("↓", ":", "：")
BULLET = re.compile(r"^\s*(?:-\s*\[[ xX✓]\]\s*|[-・□☐]\s*)")


@dataclass
class ParsedLine:
    raw: str
    kind: str
    store: Store | None = None
    match: MatchResult | None = None
    duplicate: bool = False
    include: bool = True


def parse_lines(text):
    stores = list(Store.objects.all())
    current = None
    rows = []
    seen = {}
    listed = set(
        Entry.objects.filter(completed_at__isnull=True, is_checked=False).values_list(
            "item_id", flat=True
        )
    )
    for raw in text.splitlines():
        line = BULLET.sub("", raw).strip()
        if not line:
            continue
        if (
            line.startswith(HEADING_PREFIXES)
            or line.endswith(HEADING_SUFFIXES)
            or any(word in line for word in REQUEST_KEYWORDS)
        ):
            key = make_key(line)
            current = next(
                (
                    s
                    for s in stores
                    if any(
                        make_key(name) in key
                        for name in [s.name] + s.aliases
                        if make_key(name)
                    )
                ),
                None,
            )
            rows.append(ParsedLine(line, "heading", current, include=False))
        elif any(word in line for word in GREETING_KEYWORDS):
            rows.append(
                ParsedLine(line, "excluded", current, match_item(line), include=False)
            )
        else:
            result = match_item(line)
            key = (
                ("item", result.item.pk)
                if result.item
                else ("new", make_key(result.name))
            )
            if key in seen:
                prior = seen[key]
                prior.raw, prior.match, prior.store = line, result, current
                continue
            duplicate = bool(result.item and result.item.pk in listed)
            row = ParsedLine(line, "item", current, result, duplicate, not duplicate)
            rows.append(row)
            seen[key] = row
    return rows
