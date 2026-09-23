import os
from PIL import Image, ImageDraw, ImageFont
from typing import List, Dict, Any, Optional

FONT_BOLD = r"C:\Windows\Fonts\segoeuib.ttf"
FONT_REGULAR = r"C:\Windows\Fonts\segoeui.ttf"
AVATAR_PATH = os.path.join(os.path.dirname(__file__), "kaspi_avatar.png")

COLOR_BG = (245, 247, 250)         # Светлый мягкий фон
COLOR_CARD = (255, 255, 255)       # Белая карточка
COLOR_TEXT_MAIN = (20, 24, 33)     # Темный текст
COLOR_TEXT_MUTED = (100, 110, 125) # Серый подтекст
COLOR_RED = (241, 70, 53)          # Kaspi Red
COLOR_PRICE_BG = (241, 70, 53)     # Красная плашка цены
COLOR_GOLD = (217, 119, 6)         # Золотой цвет рейтинга
COLOR_BORDER = (226, 232, 240)

def get_font(size: int, bold: bool = False):
    font_path = FONT_BOLD if bold else FONT_REGULAR
    try:
        return ImageFont.truetype(font_path, size)
    except Exception:
        return ImageFont.load_default()

class SlideBuilder:
    def __init__(self, width: int = 1080, height: int = 1920):
        self.width = width
        self.height = height
        self.avatar = Image.open(AVATAR_PATH).convert('RGBA') if os.path.exists(AVATAR_PATH) else None

    def _draw_top_bar(self, draw: ImageDraw.ImageDraw, img: Image.Image, niche_name: str, current_slide: Optional[int] = None, total_slides: Optional[int] = None):
        """Верхняя плашка с логотипом Kaspi, названием ниши и номером слайда."""
        if self.avatar:
            ava = self.avatar.resize((90, 90), Image.Resampling.LANCZOS)
            img.paste(ava, (60, 80), ava)
        
        font_brand = get_font(38, bold=True)
        draw.text((170, 90), "КАСПИ НАХОДКИ", fill=COLOR_TEXT_MAIN, font=font_brand)
        font_sub = get_font(28, bold=False)
        draw.text((170, 135), niche_name.upper(), fill=COLOR_RED, font=font_sub)

        if current_slide and total_slides:
            slide_str = f"{current_slide}/{total_slides}"
            font_pg = get_font(32, bold=True)
            draw.rounded_rectangle((self.width - 190, 95, self.width - 60, 155), radius=30, fill=(235, 240, 248))
            draw.text((self.width - 155, 108), slide_str, fill=COLOR_TEXT_MAIN, font=font_pg)

    def create_cover_slide(self, niche_name: str, count: int, max_price: int, output_path: str):
        """Слайд 1: Обложка подборки (9:16 vertical cover)."""
        img = Image.new('RGB', (self.width, self.height), color=COLOR_BG)
        draw = ImageDraw.Draw(img)

        self._draw_top_bar(draw, img, niche_name)

        # Контейнер
        draw.rounded_rectangle((60, 260, self.width - 60, 1580), radius=48, fill=COLOR_CARD, outline=COLOR_BORDER, width=2)

        # Большой логотип Kaspi
        if self.avatar:
            big_ava = self.avatar.resize((240, 240), Image.Resampling.LANCZOS)
            img.paste(big_ava, ((self.width - 240) // 2, 360), big_ava)

        # Тег
        font_tag = get_font(30, bold=True)
        tag_str = "ПОДБОРКА НАХОДОК С KASPI"
        bbox_tag = draw.textbbox((0, 0), tag_str, font=font_tag)
        tag_w = bbox_tag[2] - bbox_tag[0]
        draw.rounded_rectangle(((self.width - tag_w - 60) // 2, 660, (self.width + tag_w + 60) // 2, 730), radius=35, fill=(254, 238, 238))
        draw.text(((self.width - tag_w) // 2, 680), tag_str, fill=COLOR_RED, font=font_tag)

        # Главный оффер
        lines = [
            f"ТОП-{count} НАХОДОК С KASPI",
            niche_name.upper(),
            f"ДО {max_price:,} ₸".replace(",", " ")
        ]
        
        # Подбираем размер шрифта, чтобы текст гарантированно помещался в карточку
        max_allowed_w = 840
        f_size = 60
        font_h1 = get_font(f_size, bold=True)
        for l in lines:
            bbox = draw.textbbox((0, 0), l, font=font_h1)
            while (bbox[2] - bbox[0]) > max_allowed_w and f_size > 36:
                f_size -= 4
                font_h1 = get_font(f_size, bold=True)
                bbox = draw.textbbox((0, 0), l, font=font_h1)

        y_text = 800
        for l in lines:
            bbox = draw.textbbox((0, 0), l, font=font_h1)
            text_w = bbox[2] - bbox[0]
            draw.text(((self.width - text_w) // 2, y_text), l, fill=COLOR_TEXT_MAIN, font=font_h1)
            y_text += int(f_size * 1.45)

        # Подтекст о рейтинге
        font_sub = get_font(34, bold=False)
        sub_text = "Проверенные товары с рейтингом 5.0 из 5"
        bbox_sub = draw.textbbox((0, 0), sub_text, font=font_sub)
        draw.text(((self.width - (bbox_sub[2] - bbox_sub[0])) // 2, 1160), sub_text, fill=COLOR_TEXT_MUTED, font=font_sub)

        # Кнопка Свайпай
        font_swipe = get_font(42, bold=True)
        draw.rounded_rectangle((120, 1320, self.width - 120, 1450), radius=65, fill=COLOR_RED)
        swipe_str = "СМОТРЕТЬ ТОВАРЫ →"
        bbox_sw = draw.textbbox((0, 0), swipe_str, font=font_swipe)
        draw.text(((self.width - (bbox_sw[2] - bbox_sw[0])) // 2, 1365), swipe_str, fill=(255, 255, 255), font=font_swipe)

        # Футер
        font_ft = get_font(28, bold=False)
        ft_text = "Прямые ссылки на все товары в описании профиля"
        bbox_ft = draw.textbbox((0, 0), ft_text, font=font_ft)
        draw.text(((self.width - (bbox_ft[2] - bbox_ft[0])) // 2, 1680), ft_text, fill=COLOR_TEXT_MUTED, font=font_ft)

        img.save(output_path, quality=95)
        return output_path

    def create_product_slide(
        self,
        item: Dict[str, Any],
        slide_idx: int,
        total_slides: int,
        niche_name: str,
        local_photo_path: str,
        output_path: str
    ):
        """Слайд с отдельным товаром в деталях (9:16)."""
        img = Image.new('RGB', (self.width, self.height), color=COLOR_BG)
        draw = ImageDraw.Draw(img)

        self._draw_top_bar(draw, img, niche_name, current_slide=slide_idx, total_slides=total_slides)

        # 1. Фото-карточка
        card_box = (60, 220, self.width - 60, 1160)
        draw.rounded_rectangle(card_box, radius=40, fill=COLOR_CARD, outline=COLOR_BORDER, width=2)

        if os.path.exists(local_photo_path):
            try:
                prod_img = Image.open(local_photo_path).convert('RGB')
                prod_img.thumbnail((880, 860), Image.Resampling.LANCZOS)
                px = (self.width - prod_img.width) // 2
                py = 240 + (880 - prod_img.height) // 2
                img.paste(prod_img, (px, py))
            except Exception as e:
                print(f"Ошибка вставки фото {local_photo_path}: {e}")

        # Бейдж Kaspi в углу фото
        if self.avatar:
            badge = self.avatar.resize((100, 100), Image.Resampling.LANCZOS)
            img.paste(badge, (self.width - 180, 240), badge)

        # 2. Инфо-карточка снизу
        info_box = (60, 1200, self.width - 60, 1780)
        draw.rounded_rectangle(info_box, radius=40, fill=COLOR_CARD, outline=COLOR_BORDER, width=2)

        # Название товара
        title = item.get("title", "")
        font_title = get_font(42, bold=True)
        words = title.split()
        lines = []
        cur_line = ""
        for w in words:
            test_line = f"{cur_line} {w}".strip()
            if len(test_line) < 32:
                cur_line = test_line
            else:
                lines.append(cur_line)
                cur_line = w
                if len(lines) == 2:
                    break
        if cur_line and len(lines) < 2:
            lines.append(cur_line)

        ty = 1250
        for l in lines:
            draw.text((100, ty), l, fill=COLOR_TEXT_MAIN, font=font_title)
            ty += 56

        # Рейтинг
        rating = item.get("rating", 5.0)
        reviews = item.get("reviews_quantity", 0)
        draw.rounded_rectangle((100, 1380, 600, 1450), radius=20, fill=(254, 249, 235))
        font_rating = get_font(32, bold=True)
        draw.text((120, 1395), f"Рейтинг {rating}  ·  {reviews:,}+ отзывов".replace(",", " "), fill=COLOR_GOLD, font=font_rating)

        # Цена
        price = item.get("price", 0)
        draw.rounded_rectangle((100, 1490, 580, 1610), radius=28, fill=COLOR_PRICE_BG)
        font_price = get_font(56, bold=True)
        draw.text((130, 1515), f"{price:,} ₸".replace(",", " "), fill=(255, 255, 255), font=font_price)

        # Кнопка призыва
        font_btn = get_font(32, bold=True)
        draw.rounded_rectangle((self.width - 450, 1500, self.width - 100, 1600), radius=25, fill=(240, 244, 250))
        draw.text((self.width - 420, 1530), "Артикул в био →", fill=COLOR_TEXT_MAIN, font=font_btn)

        # Подпись
        font_hint = get_font(26, bold=False)
        draw.text((100, 1680), "Прямая ссылка и артикул закреплены в WhatsApp-канале", fill=COLOR_TEXT_MUTED, font=font_hint)

        img.save(output_path, quality=95)
        return output_path

    def create_collage_slide(
        self,
        items: List[Dict[str, Any]],
        niche_name: str,
        photo_paths: List[str],
        output_path: str
    ):
        """Единый слайд-коллаж: 3-4 товара на одном слайде (Сетка 2x2)."""
        img = Image.new('RGB', (self.width, self.height), color=COLOR_BG)
        draw = ImageDraw.Draw(img)

        self._draw_top_bar(draw, img, niche_name)

        font_h = get_font(48, bold=True)
        title_text = f"ВСЕ {len(items)} НАХОДКИ НА ОДНОМ СЛАЙДЕ"
        bbox = draw.textbbox((0, 0), title_text, font=font_h)
        draw.text(((self.width - (bbox[2] - bbox[0])) // 2, 210), title_text, fill=COLOR_TEXT_MAIN, font=font_h)

        grid_positions = [
            (60, 290, 520, 930),       # верх-лево
            (560, 290, 1020, 930),     # верх-право
            (60, 960, 520, 1600),      # низ-лево
            (560, 960, 1020, 1600),    # низ-право
        ]

        for idx, (item, path) in enumerate(zip(items[:4], photo_paths[:4])):
            bx1, by1, bx2, by2 = grid_positions[idx]
            draw.rounded_rectangle((bx1, by1, bx2, by2), radius=32, fill=COLOR_CARD, outline=COLOR_BORDER, width=2)

            # Фото
            if os.path.exists(path):
                try:
                    p_img = Image.open(path).convert('RGB')
                    p_img.thumbnail((380, 380), Image.Resampling.LANCZOS)
                    px = bx1 + (460 - p_img.width) // 2
                    py = by1 + 15
                    img.paste(p_img, (px, py))
                    if self.avatar:
                        badge_sm = self.avatar.resize((52, 52), Image.Resampling.LANCZOS)
                        img.paste(badge_sm, (px + p_img.width - 56, py + 4), badge_sm)
                except Exception:
                    pass

            # Название
            title = item.get("title", "")[:24] + "..."
            font_it = get_font(28, bold=True)
            draw.text((bx1 + 25, by1 + 420), title, fill=COLOR_TEXT_MAIN, font=font_it)

            # Рейтинг
            rating = item.get("rating", 5.0)
            font_r = get_font(24, bold=False)
            draw.text((bx1 + 25, by1 + 470), f"Рейтинг {rating}", fill=COLOR_GOLD, font=font_r)

            # Цена
            price = item.get("price", 0)
            draw.rounded_rectangle((bx1 + 25, by1 + 515, bx2 - 25, by1 + 595), radius=20, fill=COLOR_PRICE_BG)
            font_p = get_font(34, bold=True)
            draw.text((bx1 + 45, by1 + 535), f"{price:,} ₸".replace(",", " "), fill=(255, 255, 255), font=font_p)

        # Если товаров ровно 3, заполняем 4-ю карточку промо-блоком канала
        if len(items) == 3:
            bx1, by1, bx2, by2 = grid_positions[3]
            draw.rounded_rectangle((bx1, by1, bx2, by2), radius=32, fill=(255, 245, 244), outline=(241, 70, 53), width=2)
            if self.avatar:
                ava_small = self.avatar.resize((140, 140), Image.Resampling.LANCZOS)
                img.paste(ava_small, (bx1 + (460 - 140) // 2, by1 + 120), ava_small)
            font_more = get_font(32, bold=True)
            draw.text((bx1 + 95, by1 + 300), "ЕЩЕ БОЛЬШЕ", fill=COLOR_PRICE_BG, font=font_more)
            draw.text((bx1 + 120, by1 + 350), "НАХОДОК", fill=COLOR_PRICE_BG, font=font_more)
            font_more_sub = get_font(24, bold=False)
            draw.text((bx1 + 65, by1 + 440), "в нашем WhatsApp", fill=COLOR_TEXT_MUTED, font=font_more_sub)
            draw.rounded_rectangle((bx1 + 50, by1 + 515, bx2 - 50, by1 + 595), radius=20, fill=COLOR_PRICE_BG)
            font_btn_p = get_font(28, bold=True)
            draw.text((bx1 + 80, by1 + 538), "ПОДПИСАТЬСЯ →", fill=(255, 255, 255), font=font_btn_p)

        # Нижний CTA
        font_cta = get_font(36, bold=True)
        draw.rounded_rectangle((60, 1660, self.width - 60, 1790), radius=40, fill=COLOR_TEXT_MAIN)
        cta_str = "ССЫЛКИ И АРТИКУЛЫ В НАШЕМ WHATSAPP"
        bbox_cta = draw.textbbox((0, 0), cta_str, font=font_cta)
        draw.text(((self.width - (bbox_cta[2] - bbox_cta[0])) // 2, 1705), cta_str, fill=(255, 255, 255), font=font_cta)

        img.save(output_path, quality=95)
        return output_path

    def create_cta_slide(self, niche_name: str, output_path: str):
        """Финальный слайд карусели: призыв к действию (CTA)."""
        img = Image.new('RGB', (self.width, self.height), color=COLOR_BG)
        draw = ImageDraw.Draw(img)

        self._draw_top_bar(draw, img, niche_name)

        draw.rounded_rectangle((60, 320, self.width - 60, 1540), radius=48, fill=COLOR_CARD, outline=COLOR_BORDER, width=2)

        if self.avatar:
            big_ava = self.avatar.resize((220, 220), Image.Resampling.LANCZOS)
            img.paste(big_ava, ((self.width - 220) // 2, 440), big_ava)

        font_h1 = get_font(60, bold=True)
        title_lines = ["СОХРАНЯЙ И", "ПЕРЕХОДИ В КАНАЛ!"]
        y_t = 730
        for l in title_lines:
            bbox = draw.textbbox((0, 0), l, font=font_h1)
            draw.text(((self.width - (bbox[2] - bbox[0])) // 2, y_t), l, fill=COLOR_TEXT_MAIN, font=font_h1)
            y_t += 80

        font_sub = get_font(34, bold=False)
        sub_lines = [
            "Прямые ссылки на все товары",
            "и артикулы на Kaspi уже ждут",
            "в нашем WhatsApp-сообществе"
        ]
        y_s = 930
        for l in sub_lines:
            bbox = draw.textbbox((0, 0), l, font=font_sub)
            draw.text(((self.width - (bbox[2] - bbox[0])) // 2, y_s), l, fill=COLOR_TEXT_MUTED, font=font_sub)
            y_s += 50

        # Кнопка перехода
        draw.rounded_rectangle((120, 1180, self.width - 120, 1310), radius=65, fill=COLOR_RED)
        font_btn = get_font(40, bold=True)
        btn_str = "ССЫЛКА В ШАПКЕ ПРОФИЛЯ →"
        bbox_b = draw.textbbox((0, 0), btn_str, font=font_btn)
        draw.text(((self.width - (bbox_b[2] - bbox_b[0])) // 2, 1225), btn_str, fill=(255, 255, 255), font=font_btn)

        font_ft = get_font(28, bold=False)
        ft_text = "Канал с ежедневными находками на Kaspi.kz"
        bbox_ft = draw.textbbox((0, 0), ft_text, font=font_ft)
        draw.text(((self.width - (bbox_ft[2] - bbox_ft[0])) // 2, 1420), ft_text, fill=COLOR_TEXT_MUTED, font=font_ft)

        img.save(output_path, quality=95)
        return output_path
