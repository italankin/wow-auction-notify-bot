import re


def sanitize_str(s: str) -> str:
    return s \
        .replace('_', '\\_') \
        .replace('*', '\\*') \
        .replace('[', '\\[') \
        .replace(']', '\\]') \
        .replace('(', '\\(') \
        .replace(')', '\\)') \
        .replace('~', '\\~') \
        .replace('`', '\\`') \
        .replace('>', '\\>') \
        .replace('#', '\\#') \
        .replace('+', '\\+') \
        .replace('-', '\\-') \
        .replace('=', '\\=') \
        .replace('|', '\\|') \
        .replace('{', '\\{') \
        .replace('}', '\\}') \
        .replace('.', '\\.') \
        .replace('!', '\\!')


def to_human_price(price: int) -> str:
    return f"{'{:.2f}'.format(price / 10000)}g"


def from_human_price(price: str) -> int:
    match = re.match("([0-9]*\\.?[0-9]*)([gc])", price)
    if match:
        s = float(match.group(1))
        d = match.group(2)
        if d == "g":
            return int(s * 10000)
        elif d == "c":
            return int(s * 100)
    raise ValueError(f"invalid price format: {price}")


def wowhead_link(item_id: int, name: str) -> str:
    sanitized_name = sanitize_str(name)
    return f"[\\[{sanitized_name}\\]](https://www.wowhead.com/item={item_id})"
