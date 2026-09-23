import urllib.request
import urllib.parse
import json
import os
import logging
from typing import Dict, Any, List, Optional
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from config import GOOGLE_SHEETS_WEBHOOK_URL

logger = logging.getLogger("sheets_sync")

class GoogleSheetsSync:
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or GOOGLE_SHEETS_WEBHOOK_URL or os.getenv("GOOGLE_SHEETS_WEBHOOK_URL")

    def is_configured(self) -> bool:
        return bool(self.webhook_url and self.webhook_url.startswith("http"))

    def send_product(self, product: Dict[str, Any], niche_name: str) -> bool:
        """Отправляет один товар в Google Таблицу по вебхуку."""
        if not self.is_configured():
            logger.debug("Google Sheets Webhook URL не настроен.")
            return False

        payload = {
            "kaspi_id": str(product.get("kaspi_id")),
            "niche": product.get("niche", "general"),
            "niche_name": niche_name,
            "title": product.get("title", ""),
            "price": product.get("price", 0),
            "rating": product.get("rating", 0.0),
            "reviews": product.get("reviews_quantity", 0),
            "shop_link": product.get("shop_link", ""),
            "date": datetime.now().strftime("%Y-%m-%d")
        }

        try:
            req = urllib.request.Request(
                self.webhook_url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode('utf-8', errors='ignore')
                res = json.loads(raw)
                if res.get("status") in ("ok", "exists"):
                    return True
                logger.warning(f"Ошибка ответа Google Sheets: {res}")
        except urllib.error.HTTPError as e:
            if e.code == 403:
                logger.error("403 Forbidden: В Google Apps Script доступ должен быть установлен на 'Все' (Anyone).")
            else:
                logger.error(f"HTTP ошибка при отправке в Google Sheets: {e}")
        except Exception as e:
            logger.error(f"Не удалось отправить в Google Sheets: {e}")
        return False

    def sync_all_from_db(self) -> int:
        """Синхронизирует все существующие в базе товары в Google Таблицу."""
        if not self.is_configured():
            print("❌ Ошибка: GOOGLE_SHEETS_WEBHOOK_URL не настроен в .env!")
            return 0

        from storage import get_all_products
        from config import get_niche

        items = get_all_products()
        success_count = 0
        print(f"Начало выгрузки {len(items)} товаров в Google Таблицу...")

        for it in items:
            n_cfg = get_niche(it.get("niche"))
            n_name = n_cfg.name if n_cfg else it.get("niche")
            ok = self.send_product(it, n_name)
            if ok:
                success_count += 1
                print(f"  ✅ [{n_name}] {it.get('title')[:30]}... -> отправлен в таблицу")
            else:
                print(f"  ❌ [{n_name}] {it.get('title')[:30]}... -> ошибка отправки")

        print(f"\nСинхронизация завершена: успешно {success_count} из {len(items)}.")
        return success_count

    def fetch_links_for_bot(self, niche: Optional[str] = None, status: str = "new") -> List[Dict[str, Any]]:
        """Запрашивает из таблицы свежие ссылки для внешнего бота."""
        if not self.is_configured():
            return []

        url = f"{self.webhook_url}?status={status}"
        if niche:
            url += f"&niche={urllib.parse.quote(niche)}"

        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data.get("items", [])
        except Exception as e:
            logger.error(f"Ошибка запроса ссылок: {e}")
            return []
