import os
import json
import urllib.request
import logging
from typing import Dict, Any, List

from config import GEMINI_API_KEY, get_niche

logger = logging.getLogger("copywriter")

# Пул динамических хуков под решение болей и триггеры ниш
PAIN_AND_BENEFIT_HOOKS = {
    "kitchen": [
        "🍳 *Забудьте про вечный бардак и нехватку места на кухне: гениальная находка*",
        "✨ *«Как я раньше без этого обходилась?»: кухонная деталь, экономящая кучу времени*",
        "🧊 *Идеальный порядок в холодильнике и шкафах: находка с честным рейтингом*",
        "🍲 *Готовить и хранить продукты станет в 3 раза быстрее и приятнее*",
        "🔥 *Находка для кухни, о которой молчат в магазинах, но сметают на Kaspi*"
    ],
    "gadgets": [
        "⚡ *Умный девайс дешевле похода в кафе, который реально решает проблему*",
        "🎧 *Работает как дорогие бренды, но стоит в разы дешевле: топ-находка на каждый день*",
        "🔋 *Мастхэв для работы и поездок: вещь, которая не раз вас выручит*",
        "📱 *Гениальный гаджет для смартфона и дома, о котором многие не знают*",
        "🔥 *Тот самый девайс за смешные деньги, который отрабатывает каждую тенге*"
    ],
    "auto": [
        "🚗 *Копеечный девайс, который раз и навсегда избавит салон авто от хаоса*",
        "🔧 *Полезная автонаходка на Kaspi, которая выручит в самый неподходящий момент*",
        "🧼 *Чистота и комфорт в салоне без лишних трат на дорогой детейлинг*",
        "🔥 *Вещь в машину, которую оценят все опытные водители: просто и надежно*",
        "🚘 *Спасение для порядка в поездках: полезный аксессуар по супер-цене*"
    ],
    "men_clothing": [
        "👔 *Нашли качественную мужскую базу дешевле Zara и масс-маркета: сидит идеально*",
        "⚡ *Плотная мужская вещь на каждый день: не садится и не теряет вид после стирок*",
        "💥 *Стиль без усилий: базовая вещь отличного качества по честной цене*",
        "👟 *Мужской мастхэв в гардероб: строгий вид, комфорт и высокий рейтинг*",
        "🔥 *Отличная находка без переплат за логотип: проверено сотнями отзывов*"
    ],
    "care": [
        "🌸 *Эффект салонного ухода прямо дома: чистый состав и рейтинг 5.0*",
        "✨ *Тот самый хит, который стирает следы усталости и делает кожу сияющей*",
        "💄 *Любимое средство бьюти-блогеров: работает на все 100% без липкости*",
        "🧴 *Проверенный уход с сотнями реальных фотоотзывов покупательниц на Kaspi*",
        "💖 *Маленький секрет свежего и ухоженного вида на каждый день*"
    ],
    "sport": [
        "💪 *Инвентарь для домашних тренировок и зала без наценки за раскрученный бренд*",
        "🔥 *Спасет осанку и поможет держать форму: простой и надежный девайс*",
        "⚡ *Эффективные тренировки прямо дома: удобно, прочно и по честной цене*",
        "🏋️ *Качественная спортивная вещь, которая не подведет при нагрузках*",
        "🎯 *Топ-находка для тех, кто ценит форму, тонус и заряд энергии*"
    ]
}

# Вариативные заголовки секций характеристик (борьба с баннерной слепотой)
SECTION_HEADERS = [
    "✨ *Почему стоит взять:*",
    "💎 *В чем главная фишка:*",
    "🎯 *Ключевые преимущества:*",
    "💡 *Что нужно знать:*",
    "🔥 *Главные детали:*"
]

# Вариативные кнопки призыва к покупке
CTA_BUTTONS = [
    "👉 *Забрать на Kaspi:*",
    "🛒 *Ссылка на товар на Kaspi:*",
    "⚡ *Смотреть наличие и отзывы:*",
    "🔗 *Прямая ссылка на Kaspi:*"
]

# Вариативные шеринг-призывы по нишам (борьба с шаблонным однообразием)
NICHE_SHARE_CTAS = {
    "kitchen": [
        "📲 *Перешлите маме или в семейный чат — полезная вещь для каждой кухни!*",
        "📢 *Сохраните и перешлите близким, пока товар в наличии по такой цене!*",
        "💬 *Скиньте подруге, которая любит уют и порядок дома!*"
    ],
    "gadgets": [
        "📲 *Перешлите друзьям или коллегам — классный девайс за копейки!*",
        "⚡ *Скиньте тем, кто любит полезные и умные гаджеты!*",
        "💬 *Поделитесь с друзьями годной находкой — разберут быстро!*"
    ],
    "auto": [
        "📲 *Перешлите знакомым водителям — в салоне авто точно пригодится!*",
        "🚗 *Скиньте в чат автолюбителей или другу-водителю!*",
        "📢 *Сохраните себе и перешлите тем, кто часто за рулем!*"
    ],
    "men_clothing": [
        "📲 *Перешлите брату или другу — отличная база по честной цене!*",
        "👔 *Скиньте тем, кто сейчас обновляет повседневный гардероб!*",
        "🔥 *Поделитесь с друзьями — качественная вещь без переплат!*"
    ],
    "care": [
        "📲 *Перешлите подруге или сестре — проверенный уход с топ-рейтингом!*",
        "🌸 *Скиньте в чат подругам — за такую цену на Kaspi быстро раскупают!*",
        "💖 *Сохраните и поделитесь бьюти-находкой с близкими!*"
    ],
    "sport": [
        "📲 *Перешлите тем, кто тренируется — крутой инвентарь без переплат!*",
        "💪 *Скиньте друзьям на спорте — удобная вещь для дома и зала!*",
        "⚡ *Поделитесь с теми, кто следит за формой и здоровьем!*"
    ]
}

TRANSLATE_FEATURES = {
    "material": "Материал",
    "size": "Размер",
    "height": "Высота",
    "width": "Ширина",
    "assignment": "Назначение",
    "type": "Тип",
    "fabric": "Ткань",
    "color": "Цвет",
    "bluetooth version": "Bluetooth",
    "capacity": "Емкость",
    "power": "Мощность",
    "volume": "Объем",
    "weight": "Вес",
    "country": "Страна производства",
    "warranty": "Гарантия"
}

IGNORABLE_FEATURES = {
    "notice", "notice1", "gps", "microwave use", "functions and features",
    "dishwasher safe", "package", "water resistance", "waterproof"
}


class Copywriter:
    def __init__(self, api_key: str = GEMINI_API_KEY):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")

    def generate_post(self, product: Dict[str, Any]) -> str:
        """
        Генерирует готовый продающий текст для WhatsApp Сообщества.
        Если доступен API-ключ Gemini — использует LLM, иначе адаптивный шаблонизатор против баннерной слепоты.
        """
        if self.api_key:
            try:
                ai_text = self._generate_with_gemini(product)
                if ai_text and len(ai_text.strip()) > 50:
                    return ai_text.strip()
            except Exception as e:
                logger.warning(f"Ошибка Gemini API, переключаемся на шаблонизатор: {e}")

        return self._generate_with_template(product)

    def _clean_features(self, features: Any) -> List[str]:
        """Очищает характеристики от мусора (булевы true/false, системные notice и т.д.)."""
        bullets = []
        if not isinstance(features, list):
            return bullets

        for f in features:
            if not isinstance(f, dict):
                continue
            name = str(f.get("name", "")).strip()
            val = str(f.get("value", "")).strip()

            # Пропуск булевых значений и системных полей
            if val.lower() in ("true", "false", "да", "нет", "none", "null") or not val:
                continue
            if any(ign in name.lower() for ign in IGNORABLE_FEATURES):
                continue
            if "обмену и возврату не подлежит" in val.lower():
                continue

            clean_name = TRANSLATE_FEATURES.get(name.lower(), name)
            if clean_name.lower() == val.lower():
                bullets.append(f"• {val}")
            else:
                bullets.append(f"• {clean_name}: *{val}*")

            if len(bullets) >= 3:
                break

        return bullets

    def _select_dynamic_hook(self, product: Dict[str, Any]) -> str:
        """
        Интеллектуальный генератор хуков против баннерной слепоты.
        Выбирает один из 4 психологических углов (Шок-цена, Скидка, Хит отзывов, Боль/Польза).
        """
        kaspi_id = str(product.get("kaspi_id", "0"))
        h_val = abs(hash(kaspi_id))
        price = product.get("price", 0)
        old_price = product.get("price_before_discount")
        rating = product.get("rating", 5.0)
        reviews = product.get("reviews_quantity", 0)
        niche_key = product.get("niche", "gadgets")

        diff_val = (old_price - price) if (old_price and old_price > price) else 0
        diff_str = f"{diff_val:,}".replace(",", " ")
        old_price_str = f"{old_price:,}".replace(",", " ") if old_price else ""
        price_str = f"{price:,}".replace(",", " ")
        reviews_str = f"{reviews:,}".replace(",", " ") if reviews else "0"

        # 1. Угол: Реальная скидка от 20%
        if old_price and old_price > price and (old_price - price) / old_price >= 0.20:
            diff = old_price - price
            pct = int(round(diff / old_price * 100))
            discount_hooks = [
                f"🔥 *Скидка -{pct}% на Kaspi: урвали проверенный хит по рекордно низкой цене!*",
                f"⚡ *Сбросили цену на {diff_str} ₸: успейте забрать, пока не разобрали партию!*",
                f"📉 *Временный дисконт на Kaspi: вместо {old_price_str} ₸ отдают всего за {price_str} ₸!*"
            ]
            return discount_hooks[h_val % len(discount_hooks)]

        # 2. Угол: Шок-цена до 1 500 ₸
        if price > 0 and price <= 1500:
            cheap_hooks = [
                f"🔥 *Всего {price_str} ₸ на Kaspi: полезнейшая находка, которую сметают пачками!*",
                f"💸 *Нашли за {price_str} ₸ то, за что в офлайн-магазинах просят в 3-4 раза дороже!*",
                f"⚡ *Шок-цена {price_str} ₸: копеечная вещь с Kaspi, которая реально меняет быт!*",
                f"👀 *«Почему так дешево?»: всего {price_str} ₸ за находку с топ-рейтингом {rating}*"
            ]
            return cheap_hooks[h_val % len(cheap_hooks)]

        # 3. Угол: Социальное доказательство / Хит отзывов (от 300 отзывов)
        if reviews >= 300:
            proof_hooks = [
                f"⭐ *Тайный бестселлер Kaspi: {reviews_str}+ честных отзывов и оценка {rating}*",
                f"🤫 *Находка с Kaspi, о которой молчат блогеры, но заказывают тысячами*",
                f"🏆 *Топ-1 по отзывам в своей категории: проверено тысячами покупателей в Казахстане*",
                f"💥 *Редкий случай: почти идеальный рейтинг {rating} при {reviews_str}+ реальных заказов*"
            ]
            return proof_hooks[h_val % len(proof_hooks)]

        # 4. Угол: Боль и конкретная польза ниши
        niche_list = PAIN_AND_BENEFIT_HOOKS.get(niche_key, PAIN_AND_BENEFIT_HOOKS["gadgets"])
        return niche_list[h_val % len(niche_list)]

    def _generate_with_gemini(self, product: Dict[str, Any]) -> str:
        """Генерация через Google Gemini API."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.api_key}"
        
        niche_key = product.get("niche", "gadgets")
        niche_info = get_niche(niche_key)
        niche_name = niche_info.name if niche_info else "Разное"

        raw_features = product.get("features_parsed", product.get("features", []))
        cleaned_bullets = self._clean_features(raw_features)
        features_str = "\n".join(cleaned_bullets)

        prompt = f"""
Ты — копирайтер вирусного сообщества Kaspi Находки в WhatsApp для Казахстана.
Главная задача: преодолеть баннерную слепоту! Каждый пост должен начинаться с уникального эмоционального крючка.

Данные товара:
- Ниша: {niche_name}
- Название: {product.get('title')}
- Бренд: {product.get('brand', 'Оригинал')}
- Цена: {product.get('price')} ₸
- Старая цена: {product.get('price_before_discount', 'нет')} ₸
- Рейтинг: {product.get('rating')} из 5 (отзывов: {product.get('reviews_quantity')})
- Особенности:
{features_str}
- Ссылка: {product.get('shop_link')}

Требования:
1. Заголовок-крючок (без шаблонных «Находка для кухни»): используй шок от цены, интригу, решение боли или социальное доказательство. Выдели *жирным шрифтом*.
2. 1-2 предложения сути: зачем брать именно сейчас.
3. 2-3 чистых буллета преимуществ. Исключи любые булевы true/false и технический мусор.
4. Строка рейтинга (⭐ *Рейтинг {product.get('rating')}* ({product.get('reviews_quantity')}+ отзывов)).
5. Строка цены со значком ₸.
6. Призыв к покупке со ссылкой.
7. В финале ОБЯЗАТЕЛЬНО вирусный призыв переслать в семейный чат / друзьям.
8. Не используй решетки #. Только WhatsApp форматирование (*жирный*).
"""

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 450}
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
        return ""

    def _generate_with_template(self, product: Dict[str, Any]) -> str:
        """Адаптивный локальный шаблонизатор против баннерной слепоты."""
        kaspi_id = str(product.get("kaspi_id", "0"))
        h_val = abs(hash(kaspi_id))

        niche_key = product.get("niche", "gadgets")
        hook = self._select_dynamic_hook(product)

        # Вариативные заголовки и кнопки против привыкания глаз
        header = SECTION_HEADERS[h_val % len(SECTION_HEADERS)]
        cta_btn = CTA_BUTTONS[h_val % len(CTA_BUTTONS)]

        share_options = NICHE_SHARE_CTAS.get(niche_key, NICHE_SHARE_CTAS["gadgets"])
        share_cta = share_options[h_val % len(share_options)]

        title = product.get("title", "")
        price = product.get("price", 0)
        old_price = product.get("price_before_discount")
        rating = product.get("rating", 5.0)
        reviews = product.get("reviews_quantity", 0)
        shop_link = product.get("shop_link", "")

        # Цена с выгодой
        if old_price and old_price > price:
            price_line = f"💸 *Цена:* {price:,} ₸ ~(вместо {old_price:,} ₸)~".replace(",", " ")
        else:
            price_line = f"💸 *Цена:* {price:,} ₸".replace(",", " ")

        # Очищенные буллеты характеристик
        raw_features = product.get("features_parsed", product.get("features", []))
        bullets = self._clean_features(raw_features)
        
        if not bullets:
            bullets = [
                "• Отличное проверенное качество по отзывам покупателей",
                "• Хит продаж на Kaspi с сотнями реальных заказов",
                "• Практичное и надежное решение на каждый день"
            ]

        reviews_str = f"{reviews:,}".replace(",", " ") if reviews else "0"
        bullets_text = "\n".join(bullets)

        post = f"""{hook}

*{title}*

{header}
{bullets_text}

⭐ *Рейтинг {rating}* ({reviews_str}+ честных отзывов)
{price_line}

{cta_btn} {shop_link}

{share_cta}"""

        return post.strip()
