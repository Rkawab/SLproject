import unicodedata


def make_key(text):
    text = unicodedata.normalize("NFKC", text or "")
    text = "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in text)
    return "".join(
        c
        for c in text
        if c == "ー" or (not c.isspace() and unicodedata.category(c)[0] not in "PSZC")
    ).lower()
