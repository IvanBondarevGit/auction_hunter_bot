# stalcraft_bot/services/search.py

import json
import os
from config import ITEMS_PATH
from rapidfuzz import process


def load_item_by_name(name, type_="item"):
    """Ищем товары или артефакты с учётом опечаток."""
    items = []

    base_path = ITEMS_PATH
    if type_ == "artifact":
        base_path = os.path.join(ITEMS_PATH, "artefact")

    for root, dirs, files in os.walk(base_path):
        # Исключаем артефакты при поиске обычных товаров
        if type_ == "item" and "artefact" in root.lower():
            continue

        for file in files:
            if file.endswith(".json"):
                with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                    item_data = json.load(f)
                    item_name = item_data["name"]["lines"]["ru"]
                    synonyms = item_data.get("synonyms", [])
                    items.append(
                        {"name": item_name, "synonyms": synonyms, "data": item_data}
                    )

    names = [item["name"] for item in items] + [
        syn for item in items for syn in item["synonyms"]
    ]
    results = process.extract(name, names, limit=10, score_cutoff=70)

    found_items = []
    for match_name, score, index in results:
        matched_item = items[index // (len(names) // len(items))]["data"]
        found_items.append({"name": match_name, "score": score, "data": matched_item})

    return found_items
