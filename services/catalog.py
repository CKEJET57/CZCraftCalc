"""Общие операции каталога предметов без зависимости от HTTP."""
from __future__ import annotations

import json

from config import DB_DIR
from storage.hideout import extract_category_id
from storage.listing import get_item_name


def _get_text(obj, lang: str) -> str:
    if obj is None:
        return ""
    if isinstance(obj, (str, int, float)):
        return str(obj)
    if isinstance(obj, dict):
        if lang in obj:
            return str(obj[lang])
        if "ru" in obj:
            return str(obj["ru"])
        if "en" in obj:
            return str(obj["en"])
        if "lines" in obj:
            lines = obj["lines"]
            return lines.get(lang) or lines.get("ru") or lines.get("en") or ""
        if "text" in obj:
            return _get_text(obj["text"], lang)
    return str(obj)


def _parse_list_block(block_data: dict, lang: str) -> dict:
    b_title = _get_text(block_data.get("title"), lang)
    elements = []
    for el in block_data.get("elements", []):
        el_type = el.get("type")

        if el_type == "text":
            val = _get_text(el.get("text"), lang)
            if val:
                elements.append({
                    "type": "text", "name": "", "value": val,
                    "nameColor": None, "valueColor": None,
                })
        elif el_type in ("numeric", "key-value", "range"):
            name = _get_text(el.get("name") or el.get("key"), lang)
            formatted = el.get("formatted", {})

            if formatted and "value" in formatted:
                val = _get_text(formatted["value"], lang)
                name_color = formatted.get("nameColor")
                val_color = formatted.get("valueColor")
            else:
                val = _get_text(el.get("value"), lang)
                name_color = None
                val_color = None

            if name and val:
                elements.append({
                    "type": el_type,
                    "name": name,
                    "value": val,
                    "nameColor": name_color,
                    "valueColor": val_color,
                })
    return {"type": "list", "title": b_title, "elements": elements}


def _parse_blocks(data: dict, lang: str) -> list[dict]:
    blocks_out: list[dict] = []
    for block in data.get("infoBlocks", []):
        b_type = block.get("type")

        if b_type == "list":
            parsed = _parse_list_block(block, lang)
            if parsed["elements"]:
                blocks_out.append(parsed)

        elif b_type == "grouped":
            for sub_block in block.get("detailed", []):
                parsed = _parse_list_block(sub_block, lang)
                if parsed["elements"]:
                    blocks_out.append(parsed)

        elif b_type == "text":
            text_val = _get_text(block.get("text"), lang).replace("\\n", "\n")
            b_title = _get_text(block.get("title"), lang)
            if text_val:
                blocks_out.append({"type": "text", "title": b_title, "text": text_val})

    return blocks_out


def health() -> dict:
    return {"ok": True}


def list_items(state, lang: str = "ru", q: str | None = None, craftable: bool = False) -> list[dict]:
    def list_items(
        lang: str = "ru",
        q: str | None = None,
        craftable: bool = False,
    ) -> list[dict]:
        """
        Список предметов.
        - craftable=true → только те, что есть в listing_craft.json
        - q=... → фильтр по названию (регистронезависимый)
        """
        state = get_state()
        index = state.craftable_index if craftable else state.item_index
    
        q_low = q.lower() if q else None
        out: list[dict] = []
        for item_id in index:
            name = get_item_name(index, item_id, lang)
            if q_low and q_low not in name.lower():
                continue
            out.append({"item_id": item_id, "name": name})
    
        out.sort(key=lambda x: x["name"])
        return out


def list_categories(state, lang: str = "ru") -> list[dict]:
    def list_categories(lang: str = "ru") -> list[dict]:
        state = get_state()
        cats: dict[str, str] = {}
        for r in state.hideout["recipes"]:
            cid = extract_category_id(r) or "other"
            if cid not in cats:
                cats[cid] = r["category"]["lines"].get(lang) or cid
        return [{"id": k, "name": v} for k, v in cats.items()]


def get_item_details(state, item_id: str, lang: str = "ru") -> dict:
    def get_item_details(item_id: str, lang: str = "ru") -> dict:
        item = state.item_index.get(item_id)
        if not item:
            raise LookupError(f"Предмет {item_id} не найден в listing")
    
        data_path = item.get("data", "")
        icon_path = item.get("icon", "")
        icon_url = f"/api/static{icon_path}" if icon_path else None
        category = item.get("category", "")
    
        blocks_out: list[dict] = []
        has_variants = False
        max_variant_level = 0
    
        if data_path:
            file_path = DB_DIR / data_path.lstrip("/")
            if file_path.exists():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    blocks_out = _parse_blocks(data, lang)
                except Exception as e:
                    print(f"Error parsing {item_id}: {e}")
    
                # Проверка наличия _variants/{item_id}/
                variants_dir = file_path.parent / "_variants" / item_id
                if variants_dir.is_dir():
                    levels = [
                        int(p.stem)
                        for p in variants_dir.glob("*.json")
                        if p.stem.isdigit()
                    ]
                    if levels:
                        has_variants = True
                        max_variant_level = max(levels)
    
        return {
            "color": item.get("color", "DEFAULT"),
            "status": item.get("status", {}).get("state", "NONE"),
            "category": category,
            "icon_url": icon_url,
            "blocks": blocks_out,
            "has_variants": has_variants,
            "max_variant_level": max_variant_level,
        }


def get_item_variants(state, item_id: str, lang: str = "ru") -> dict:
    def get_item_variants(item_id: str, lang: str = "ru") -> dict:
        """
        Возвращает варианты прокачки предмета.
        Ответ: { "available": bool, "variants": [{ "level": int, "blocks": [...] }, ...] }
        """
        item = state.item_index.get(item_id)
        if not item:
            raise LookupError(f"Предмет {item_id} не найден в listing")
    
        data_path = item.get("data", "")
        if not data_path:
            return {"available": False, "variants": []}
    
        file_path = DB_DIR / data_path.lstrip("/")
        variants_dir = file_path.parent / "_variants" / item_id
    
        if not variants_dir.is_dir():
            return {"available": False, "variants": []}
    
        files = sorted(
            (p for p in variants_dir.glob("*.json") if p.stem.isdigit()),
            key=lambda p: int(p.stem),
        )
        if not files:
            return {"available": False, "variants": []}
    
        variants: list[dict] = []
        for p in files:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                variants.append({
                    "level": int(p.stem),
                    "blocks": _parse_blocks(raw, lang),
                })
            except Exception as e:
                print(f"Error parsing variant {p}: {e}")
                continue
    
        if not variants:
            return {"available": False, "variants": []}
    
        return {"available": True, "variants": variants}
