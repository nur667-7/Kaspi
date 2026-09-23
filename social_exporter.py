import os
import shutil
import urllib.request
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from config import get_niche
from storage import get_candidates_for_social_carousel, record_carousel_batch
from slide_builder import SlideBuilder

logger = logging.getLogger("social_exporter")

# Основная папка Google Drive (локальная или внешняя синхронизируемая)
GOOGLE_DRIVE_DEFAULT = os.path.join(os.path.dirname(__file__), "Google_Drive")
GOOGLE_DRIVE_ROOT = os.getenv("GOOGLE_DRIVE_PATH", GOOGLE_DRIVE_DEFAULT)

NICHE_FOLDERS = {
    "men_clothing": "01_Мужская_одежда",
    "gadgets": "02_Гаджеты_и_техника",
    "kitchen": "03_Кухня_и_уют",
    "care": "04_Красота_и_уход",
    "auto": "05_Автотовары",
    "sport": "06_Спорт_и_фитнес"
}

NICHE_CAROUSEL_HOOKS = {
    "men_clothing": [
        "Топ-{count} находок мужской одежды на Kaspi до {max_price} ₸ 🔥",
        "Стильная мужская база дешевле Zara: топ-{count} вещей на Kaspi до {max_price} ₸ 👔",
        "Кажется, на Kaspi ошиблись с ценой: топ-{count} мужских находок до {max_price} ₸ 👀",
        "О них молчат в ТРЦ: топ-{count} качественных мужских вещей с Kaspi 🤫"
    ],
    "gadgets": [
        "Топ-{count} полезных гаджетов с Kaspi дешевле {max_price} ₸ ⚡",
        "Девайсы с Kaspi дешевле похода в кафе, которые реально спасают быт 📱",
        "Работают как дорогие бренды: топ-{count} гаджетов с Kaspi до {max_price} ₸ 🔋",
        "Тайные бестселлеры Kaspi: топ-{count} смарт-гаджетов с честными отзывами 🤫"
    ],
    "kitchen": [
        "Топ-{count} находок для кухни на Kaspi дешевле {max_price} ₸ 🍳",
        "Идеальный порядок на кухне: топ-{count} гениальных находок до {max_price} ₸ ✨",
        "«Как я раньше без этого жила?»: топ-{count} вещей для кухни с Kaspi 🍲",
        "Забудьте про бардак: топ-{count} кухонных лайфхаков с Kaspi до {max_price} ₸ 🧊"
    ],
    "care": [
        "Топ-{count} крутых средств для ухода на Kaspi с рейтингом 5.0 🌸",
        "Эффект салонного ухода прямо дома: топ-{count} хитов Kaspi до {max_price} ₸ 💄",
        "Любимчики бьюти-блогеров: топ-{count} средств с Kaspi с чистым составом ✨",
        "Стирают усталость за копейки: топ-{count} находок для ухода на Kaspi 💖"
    ],
    "auto": [
        "Топ-{count} полезных автотоваров на Kaspi, которые спасут ваш салон 🚗",
        "Копеечные девайсы в машину, которые выручат в любой момент: топ-{count} находок 🔧",
        "Чистота и порядок в авто без трат на детейлинг: топ-{count} хитов Kaspi 🧼",
        "Опытные водители сметают их на Kaspi: топ-{count} автонаходок до {max_price} ₸ 🚘"
    ],
    "sport": [
        "Топ-{count} удобных товаров для тренировок на Kaspi до {max_price} ₸ 💪",
        "Спортзал прямо дома без переплат: топ-{count} находок на Kaspi 🏋️",
        "Спасут спину и фигуру: топ-{count} проверенных товаров для спорта на Kaspi 🎯",
        "Крутой инвентарь без наценки за бренд: топ-{count} спортивных вещей с Kaspi ⚡"
    ]
}

class SocialExporter:
    def __init__(self, output_root: str = GOOGLE_DRIVE_ROOT):
        self.output_root = output_root
        os.makedirs(self.output_root, exist_ok=True)
        self.slide_builder = SlideBuilder()

    def apply_badge(self, image_path: str):
        """Накладывает фирменную круглую аватарку Kaspi в угол фотографии товара."""
        badge_path = os.path.join(os.path.dirname(__file__), "kaspi_avatar.png")
        if not os.path.exists(badge_path):
            return
        try:
            from PIL import Image
            base = Image.open(image_path).convert('RGBA')
            badge = Image.open(badge_path).convert('RGBA')
            badge_dim = int(min(base.size) * 0.16)
            badge = badge.resize((badge_dim, badge_dim), Image.Resampling.LANCZOS)
            padding = 24
            pos = (base.width - badge_dim - padding, padding)
            base.paste(badge, pos, badge)
            base.convert('RGB').save(image_path, quality=95)
        except Exception as e:
            logger.warning(f"Не удалось наложить бейдж на {image_path}: {e}")

    def download_image(self, url: str, target_path: str, add_badge: bool = True) -> bool:
        """Скачивает изображение в высоком разрешении и брендирует его аватаркой Kaspi."""
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 200:
                    with open(target_path, 'wb') as f:
                        f.write(resp.read())
                    if add_badge:
                        self.apply_badge(target_path)
                    return True
        except Exception as e:
            logger.warning(f"Не удалось скачать {url}: {e}")
        return False

    def export_niche_carousel(self, niche_key: str, count: int = 4) -> Optional[str]:
        """
        Автоматически генерирует готовый визуальный пакет для Google Drive:
        - 01_Обложка.png (9:16)
        - 02..05_Слайд_товара.png (9:16 со всеми плашками)
        - 06_Коллаж_4в1_Сетка.png (все 4 товара на одном слайде)
        - 07_Финальный_слайд_CTA.png
        - Папка с исходными фото с бейджем Kaspi
        - Сценарий_и_описание_TikTok.txt
        """
        niche = get_niche(niche_key)
        if not niche:
            logger.error(f"Неизвестная ниша: {niche_key}")
            return None

        # Выбираем товары из БД
        items = get_candidates_for_social_carousel(niche_key, count=count)
        if not items:
            logger.warning(f"Нет доступных товаров для создания карусели в нише '{niche.name}'.")
            return None

        actual_count = len(items)
        max_price = max(it.get("price", 0) for it in items)

        # Формируем структуру папок по нишам для Google Drive
        niche_subfolder = NICHE_FOLDERS.get(niche_key, f"00_{niche_key}")
        niche_dir = os.path.join(self.output_root, niche_subfolder)
        os.makedirs(niche_dir, exist_ok=True)

        date_str = datetime.now().strftime("%Y-%m-%d")
        timestamp = datetime.now().strftime("%H%M%S")
        batch_folder_name = f"{date_str}_Выпуск_{actual_count}находки_{timestamp}"
        batch_dir = os.path.join(niche_dir, batch_folder_name)
        os.makedirs(batch_dir, exist_ok=True)

        raw_photos_dir = os.path.join(batch_dir, "Исходные_фото_с_бейдж_Kaspi")
        os.makedirs(raw_photos_dir, exist_ok=True)

        hook_options = NICHE_CAROUSEL_HOOKS.get(niche_key, ["Топ-{count} находок на Kaspi до {max_price} ₸ 🔥"])
        if isinstance(hook_options, list):
            import random
            hook_template = random.choice(hook_options)
        else:
            hook_template = hook_options
        max_price_str = f"{max_price:,}".replace(",", " ")
        hook_text = hook_template.format(count=actual_count, max_price=max_price_str)

        print(f"\n🎨 Генерация графических слайдов 9:16 для '{niche.name}' ({actual_count} товара)...")

        # 1. Слайд 1: Обложка
        cover_path = os.path.join(batch_dir, "01_Обложка.png")
        self.slide_builder.create_cover_slide(niche.name, actual_count, max_price, cover_path)

        # 2. Слайды с товарами
        product_ids = []
        downloaded_photo_paths = []

        total_slides = actual_count + 2 # Обложка + товары + CTA

        for idx, item in enumerate(items, start=1):
            pid = str(item.get("kaspi_id"))
            product_ids.append(pid)
            
            # Скачиваем чистое фото товара
            images = item.get("images", [])
            local_raw_photo = os.path.join(raw_photos_dir, f"товар_{idx}_{pid}.jpg")
            if images:
                self.download_image(images[0], local_raw_photo, add_badge=False)
            downloaded_photo_paths.append(local_raw_photo)

            # Генерируем красивый 9:16 слайд товара
            prod_slide_name = f"{idx+1:02d}_Слайд_{idx}_Товар_{pid}.png"
            prod_slide_path = os.path.join(batch_dir, prod_slide_name)
            self.slide_builder.create_product_slide(
                item=item,
                slide_idx=idx + 1,
                total_slides=total_slides,
                niche_name=niche.name,
                local_photo_path=local_raw_photo,
                output_path=prod_slide_path
            )

        # 3. Слайд-Коллаж 4-в-1 (все 3-4 товара на одном слайде в сетке)
        collage_path = os.path.join(batch_dir, f"{actual_count+2:02d}_Коллаж_Сетка_Все_{actual_count}_товара.png")
        self.slide_builder.create_collage_slide(
            items=items,
            niche_name=niche.name,
            photo_paths=downloaded_photo_paths,
            output_path=collage_path
        )

        # 4. Финальный слайд: CTA
        cta_slide_idx = actual_count + 3
        cta_path = os.path.join(batch_dir, f"{cta_slide_idx:02d}_Финальный_слайд_CTA.png")
        self.slide_builder.create_cta_slide(niche.name, cta_path)

        # 5. Сценарий и текст для публикации
        script_lines = [
            f"=== ПАКЕТ ДЛЯ TIKTOK / REELS / INSTAGRAM КАРУСЕЛИ ===",
            f"Ниша: {niche.name}",
            f"Папка Google Drive: {niche_subfolder}/{batch_folder_name}",
            f"Дата создания: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            "\n" + "="*50 + "\n",
            f"ТЕКСТ ОБЛОЖКИ: {hook_text}\n"
        ]

        for i, it in enumerate(items, 1):
            script_lines.append(f"Товар #{i}: {it.get('title')}")
            script_lines.append(f"Цена: {it.get('price')} ₸ | Рейтинг: {it.get('rating')}")
            script_lines.append(f"Ссылка: {it.get('shop_link')}\n")

        script_lines.append("="*50)
        script_lines.append("ГОТОВЫЙ ТЕКСТ ДЛЯ ОПИСАНИЯ РОЛИКА:\n")
        script_lines.append(f"{hook_text}\n")
        script_lines.append("Все артикулы и прямые ссылки на Kaspi закрепили в нашем WhatsApp-канале (активная ссылка в описании профиля 🔗).\n")
        script_lines.append("Какой товар понравился больше всего? Напиши в комментариях 👇\n")
        script_lines.append(f"#kaspi #каспинаходки #казахстан #алматы #астана #шымкент #обзортоваров #{niche_key} #скидки")

        script_file = os.path.join(batch_dir, "Сценарий_и_описание_TikTok.txt")
        with open(script_file, "w", encoding="utf-8") as f:
            f.write("\n".join(script_lines))

        # 6. Фиксируем пакет в базе данных (товары помечаются tt_status = 'batched')
        batch_code = f"GD_{niche_key.upper()}_{date_str}_{timestamp}"
        record_carousel_batch(batch_code, niche_key, product_ids, hook_text, batch_dir)

        # Если настроен путь к внешнему Google Drive Desktop — копируем
        external_gdrive = os.getenv("GOOGLE_DRIVE_PATH")
        if external_gdrive and os.path.exists(external_gdrive) and os.path.abspath(external_gdrive) != os.path.abspath(self.output_root):
            try:
                target_ext = os.path.join(external_gdrive, niche_subfolder, batch_folder_name)
                shutil.copytree(batch_dir, target_ext, dirs_exist_ok=True)
                print(f"☁️ Синхронизировано с Google Диском: {target_ext}")
            except Exception as e:
                logger.warning(f"Не удалось скопировать на внешний Google Drive: {e}")

        print(f"✅ Пакет слайдов успешно сохранен для Google Drive!")
        print(f"📁 Путь: {batch_dir}")
        return batch_dir
