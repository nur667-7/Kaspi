import urllib.request
import urllib.parse
import json
import time
import logging
from typing import List, Dict, Any, Optional

from config import DEFAULT_CITY_ID, get_niche
from storage import product_exists

logger = logging.getLogger("kaspi_parser")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class KaspiParser:
    BASE_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'X-KS-City': DEFAULT_CITY_ID,
        'Sec-Ch-Ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin'
    }

    def __init__(self, city_id: str = DEFAULT_CITY_ID):
        self.city_id = city_id

    def _make_request(self, url: str, referer: Optional[str] = None, timeout: int = 10) -> Optional[Any]:
        headers = dict(self.BASE_HEADERS)
        headers['X-KS-City'] = self.city_id
        if referer:
            headers['Referer'] = referer

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    raw = resp.read().decode('utf-8', errors='ignore')
                    return json.loads(raw)
        except Exception as e:
            logger.warning(f"Request failed for {url}: {e}")
        return None

    def search_listing(self, query: str, page: int = 0) -> List[Dict[str, Any]]:
        """Запрашивает результаты поиска по ключевой фразе."""
        encoded = urllib.parse.quote(query)
        url = f"https://kaspi.kz/yml/product-view/pl/results?page={page}&q={encoded}&text={encoded}"
        referer = f"https://kaspi.kz/shop/search/?text={encoded}"
        
        data = self._make_request(url, referer=referer)
        if not data or not isinstance(data, dict):
            return []
        return data.get('data', [])

    def get_product_features(self, kaspi_id: str) -> List[Dict[str, str]]:
        """Запрашивает детальные технические характеристики товара."""
        url = f"https://kaspi.kz/yml/content/item/api/v1/item/{kaspi_id}/features"
        referer = f"https://kaspi.kz/shop/p/-{kaspi_id}/"
        
        data = self._make_request(url, referer=referer)
        if not data or "features" not in data:
            return []

        features_list = []
        for f in data.get("features", []):
            code = f.get("attributeCode", "")
            # Очищаем код атрибута от технического префикса (например, 'kitchen*material' -> 'материал')
            attr_name = code.split("*")[-1].replace("_", " ").title() if "*" in code else code
            values = f.get("formattedValues", [])
            val_str = ", ".join(str(v) for v in values if v)
            if val_str:
                features_list.append({"name": attr_name, "value": val_str})
        return features_list

    def extract_clean_images(self, raw_images: List[Dict[str, Any]]) -> List[str]:
        """Извлекает ссылки на изображения в максимальном качестве."""
        clean_urls = []
        for img in raw_images:
            if not isinstance(img, dict):
                continue
            # Приоритет: large -> medium -> small
            url = img.get("large") or img.get("medium") or img.get("small")
            if url:
                # Отрезаем ?format=preview-large чтобы получить чистый оригинал с CDN
                base_url = url.split("?")[0]
                if base_url not in clean_urls:
                    clean_urls.append(base_url)
        return clean_urls

    def parse_niche(
        self,
        niche_key: str,
        max_price: Optional[int] = None,
        min_rating: Optional[float] = None,
        min_reviews: Optional[int] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Ищет качественные товары по нише, фильтрует и обогащает характеристиками.
        Пропускает товары, которые уже есть в локальной базе данных.
        """
        niche = get_niche(niche_key)
        if not niche:
            raise ValueError(f"Неизвестная ниша: {niche_key}")

        target_max_price = max_price if max_price is not None else niche.default_max_price
        target_min_rating = min_rating if min_rating is not None else niche.min_rating
        target_min_reviews = min_reviews if min_reviews is not None else niche.min_reviews

        found_products: List[Dict[str, Any]] = []

        logger.info(f"Начинаем поиск для ниши '{niche.name}' (макс. цена: {target_max_price} ₸, мин. рейтинг: {target_min_rating})")

        for kw in niche.keywords:
            if len(found_products) >= limit:
                break

            for page in range(3):
                if len(found_products) >= limit:
                    break

                logger.info(f"Проверяем поисковый запрос: '{kw}' (стр. {page})")
                items = self.search_listing(kw, page=page)
                if not items:
                    break
                
                for item in items:
                    if len(found_products) >= limit:
                        break

                    kaspi_id = str(item.get("id"))
                    if not kaspi_id:
                        continue

                    # 1. Проверка на дубликат в базе
                    if product_exists(kaspi_id):
                        continue

                    # 2. Фильтрация по цене
                    unit_price = item.get("unitPrice", 0)
                    if not unit_price or unit_price > target_max_price:
                        continue

                    # 3. Фильтрация по рейтингу
                    rating = float(item.get("rating", 0.0))
                    if rating < target_min_rating:
                        continue

                    # 4. Фильтрация по количеству отзывов
                    reviews_count = int(item.get("reviewsQuantity", 0))
                    if reviews_count < target_min_reviews:
                        continue

                    # Извлекаем фото
                    images = self.extract_clean_images(item.get("previewImages", []))
                    if not images:
                        continue

                    # Формируем прямую ссылку на товар
                    raw_shop_link = item.get("shopLink", "")
                    if raw_shop_link.startswith("/"):
                        full_shop_link = f"https://kaspi.kz/shop{raw_shop_link}"
                    else:
                        full_shop_link = f"https://kaspi.kz/shop/p/-{kaspi_id}/"

                    # Пауза перед догрузкой характеристик
                    time.sleep(0.5)
                    features = self.get_product_features(kaspi_id)

                    best_merchant = item.get("bestMerchant", {})
                    seller_name = best_merchant.get("name", "") if isinstance(best_merchant, dict) else ""

                    product_record = {
                        "kaspi_id": kaspi_id,
                        "title": item.get("title", "").strip(),
                        "brand": item.get("brand", "").strip(),
                        "niche": niche_key,
                        "price": unit_price,
                        "price_before_discount": item.get("unitPriceBeforeDiscount"),
                        "rating": rating,
                        "reviews_quantity": reviews_count,
                        "shop_link": full_shop_link,
                        "images": images,
                        "features": features,
                        "seller_name": seller_name
                    }

                    found_products.append(product_record)
                    logger.info(f"Найдена подходящая находка: {product_record['title'][:35]} | {unit_price} ₸ (⭐ {rating}, {reviews_count} отзывов)")

            # Небольшая пауза между запросами к Kaspi
            time.sleep(1.0)

        logger.info(f"Поиск по нише '{niche.name}' завершен. Отобрано новых товаров: {len(found_products)}")
        return found_products
