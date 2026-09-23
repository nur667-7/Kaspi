"""
Клиент для получения товаров и ссылок из Google Таблицы Kaspi.
Подходит для интеграции в Telegram-ботов, внешние парсеры или автопостеры.
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

# Настройка UTF-8 для корректного вывода в терминал Windows
if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Вебхук Google Таблицы из .env
SHEETS_WEBHOOK_URL = (
    "https://script.google.com/macros/s/AKfycbygYwiIYd6oOe_OihdE6inCzHS3a4RTZpUVOVtoVHuINUA8bpohyAjcfmEFxuY7YQmd/exec"
)


def fetch_products(
    status: Optional[str] = "new",
    niche: Optional[str] = None,
    webhook_url: str = SHEETS_WEBHOOK_URL,
    timeout: int = 15
) -> List[Dict[str, Any]]:
    """
    Запрашивает список товаров из Google Таблицы по GET-запросу.

    :param status: Фильтр по статусу (например, 'new' для свежих или None для всех)
    :param niche: Название ниши (например, 'Товары для кухни', 'Мужская одежда' или None)
    :param webhook_url: URL вебхука Google Apps Script
    :param timeout: Таймаут запроса в секундах
    :return: Список словарей с данными товаров
    """
    params = {}
    if status:
        params["status"] = status
    if niche:
        params["niche"] = niche

    query_string = urllib.parse.urlencode(params)
    url = f"{webhook_url}?{query_string}" if query_string else webhook_url

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KaspiBot/1.0",
        "Accept": "application/json"
    }

    req = urllib.request.Request(url, headers=headers, method="GET")

    # urllib автоматически обрабатывает HTTP 302 Redirect от серверов Google
    with urllib.request.urlopen(req, timeout=timeout) as response:
        if response.status == 200:
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("items", [])
        else:
            raise RuntimeError(f"Google Sheets вернул статус {response.status}")


if __name__ == "__main__":
    print("=" * 60)
    print("📡 Запрос свежих товаров из Google Таблицы (status='new')...")
    print("=" * 60)

    try:
        items = fetch_products(status="new")
        print(f"✅ Успешно получено товаров со статусом 'new': {len(items)}\n")

        for idx, item in enumerate(items[:5], start=1):
            print(f"[{idx}] {item.get('title')}")
            print(f"    Ниша: {item.get('niche')}")
            print(f"    Цена: {item.get('price')} ₸ | Рейтинг: ⭐ {item.get('rating')} ({item.get('reviews')} отзывов)")
            print(f"    Ссылка: {item.get('link')}")
            print(f"    ID Kaspi: {item.get('kaspi_id')}")
            print("-" * 50)

        if len(items) > 5:
            print(f"... и еще {len(items) - 5} товаров.")

    except Exception as err:
        print(f"❌ Ошибка запроса: {err}")
