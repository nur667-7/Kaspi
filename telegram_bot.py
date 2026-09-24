import sys
import time
import json
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional, List

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, NICHES, get_niche, get_chat_id_for_niche, WA_BRIDGE_URL
from telegram_notifier import TelegramNotifier
from storage import (
    get_niche_settings, save_niche_settings, get_analytics_summary,
    get_pending_wa_posts, mark_post_published_wa, mark_post_failed_wa,
    save_product, update_post_caption, get_post_by_id
)
from kaspi_parser import KaspiParser
from copywriter import Copywriter
from social_exporter import SocialExporter


class TelegramBotController:
    """
    Интерактивный пульт управления ботом Kaspi:
    - Zero-typing интерфейс (все настройки через inline-кнопки).
    - Текстовый ввод активируется ТОЛЬКО по кнопке «🎯 Задать направление».
    - Управление ценовыми диапазонами, рейтингом и модерация товаров.
    """

    def __init__(self):
        self.notifier = TelegramNotifier()
        self.bot_token = (TELEGRAM_BOT_TOKEN or "").strip()
        self.admin_chat_id = str(TELEGRAM_CHAT_ID or "").strip()
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.last_update_id = 0
        # Состояние ожидания текстового направления для пользователя: {chat_id: {"action": "wait_focus", "niche": "gadgets"}}
        self.user_states: Dict[str, Dict[str, Any]] = {}

    def get_updates(self, offset: Optional[int] = None, timeout: int = 25) -> List[Dict[str, Any]]:
        """Получает новые обновления через Long Polling."""
        url = f"{self.api_url}/getUpdates?timeout={timeout}"
        if offset:
            url += f"&offset={offset}"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=timeout + 5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("ok"):
                    return data.get("result", [])
        except Exception:
            pass
        return []

    # ---------------------------------------------------------
    # Экраны и клавиатуры меню
    # ---------------------------------------------------------

    def build_main_menu(self) -> tuple[str, Dict[str, Any]]:
        """Главный экран админ-панели."""
        text = (
            "🎛 <b>Центр управления Kaspi Automation</b>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "Выберите раздел на кнопках ниже:\n\n"
            "• <b>Настройки ниш:</b> лимиты цен, рейтинг и подниши\n"
            "• <b>Быстрый парсинг:</b> поиск свежих находок на Kaspi\n"
            "• <b>Аналитика:</b> наполненность буфера и финансы\n"
            "• <b>WhatsApp:</b> ручная отправка карточек из очереди"
        )
        keyboard = {
            "inline_keyboard": [
                [{"text": "⚡ Запустить цикл (Старт ➔ Постинг ➔ Стоп)", "callback_data": "act:run_full_cycle"}],
                [
                    {"text": "🟢 Поднять сервер", "callback_data": "act:start_server"},
                    {"text": "🔴 Выключить сервер", "callback_data": "act:stop_server"}
                ],
                [{"text": "⚙️ Настройки ниш и цен", "callback_data": "menu:niches"}],
                [{"text": "🔍 Спарсить товары сейчас", "callback_data": "menu:parse_select"}],
                [{"text": "📊 Краткая аналитика", "callback_data": "act:analytics"}],
                [{"text": "🚀 Отправить по 1 товару в WhatsApp", "callback_data": "act:post_all_wa"}]
            ]
        }
        return text, keyboard

    def build_niches_list_menu(self, action_prefix: str = "niche_cfg") -> tuple[str, Dict[str, Any]]:
        """Список всех 6 ниш в виде кнопок."""
        icons = {
            "men_clothing": "👔",
            "gadgets": "📱",
            "kitchen": "🍳",
            "care": "💄",
            "auto": "🚗",
            "sport": "🏋️"
        }
        buttons = []
        for slug, n_cfg in NICHES.items():
            icon = icons.get(slug, "📦")
            buttons.append([{"text": f"{icon} {n_cfg.name}", "callback_data": f"{action_prefix}:{slug}"}])
        buttons.append([{"text": "◀️ В главное меню", "callback_data": "menu:main"}])

        text = "📁 <b>Выберите нишу для настройки параметров:</b>"
        return text, {"inline_keyboard": buttons}

    def build_niche_settings_menu(self, niche_key: str) -> tuple[str, Dict[str, Any]]:
        """Экран параметров конкретной ниши."""
        n_cfg = get_niche(niche_key)
        if not n_cfg:
            return "Ошибка ниши", {"inline_keyboard": [[{"text": "Назад", "callback_data": "menu:niches"}]]}

        st = get_niche_settings(niche_key)
        min_p = st.get("min_price", 0)
        max_p = st.get("max_price") or n_cfg.default_max_price
        rating = st.get("min_rating", 4.7)
        reviews = st.get("min_reviews", 15)
        focus = st.get("custom_focus") or "(не задано, общий поиск)"

        text = (
            f"⚙️ <b>Параметры ниши: {n_cfg.name}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Диапазон цен:</b> от {min_p:,} до {max_p:,} ₸\n".replace(",", " ") +
            f"⭐ <b>Мин. рейтинг:</b> {rating}\n"
            f"💬 <b>Мин. отзывов:</b> {reviews} шт.\n"
            f"🎯 <b>Направление поиска (подниша):</b>\n<code>{focus}</code>\n\n"
            f"<i>Выберите настройку для изменения кнопкой:</i>"
        )

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "💰 Макс. цена", "callback_data": f"set_maxp_menu:{niche_key}"},
                    {"text": "💵 Мин. цена", "callback_data": f"set_minp_menu:{niche_key}"}
                ],
                [
                    {"text": "⭐ Рейтинг", "callback_data": f"set_rat_menu:{niche_key}"},
                    {"text": "💬 Отзывы", "callback_data": f"set_rev_menu:{niche_key}"}
                ],
                [
                    {"text": "🎯 Задать направление (поднишу)", "callback_data": f"ask_focus:{niche_key}"}
                ],
                [
                    {"text": "🧹 Сбросить поднишу", "callback_data": f"clear_focus:{niche_key}"}
                ],
                [
                    {"text": "🔍 Спарсить эту нишу сейчас", "callback_data": f"parse_niche:{niche_key}"}
                ],
                [
                    {"text": "◀️ Ко всем нишам", "callback_data": "menu:niches"}
                ]
            ]
        }
        return text, keyboard

    def build_price_presets_menu(self, niche_key: str, price_type: str = "max") -> tuple[str, Dict[str, Any]]:
        """Кнопки готовых пресетов цен (Zero Typing)."""
        n_cfg = get_niche(niche_key)
        label = "максимальную" if price_type == "max" else "минимальную"
        text = f"💰 <b>Выберите {label} цену для «{n_cfg.name}»:</b>"

        if price_type == "max":
            presets = [3000, 5000, 8000, 10000, 12000, 15000, 20000, 30000]
        else:
            presets = [0, 1000, 2000, 3000, 5000, 7000]

        rows = []
        cur_row = []
        for p in presets:
            t = "0 ₸" if p == 0 else f"{p:,} ₸".replace(",", " ")
            cur_row.append({"text": t, "callback_data": f"save_p:{niche_key}:{price_type}:{p}"})
            if len(cur_row) == 2:
                rows.append(cur_row)
                cur_row = []
        if cur_row:
            rows.append(cur_row)

        rows.append([{"text": "◀️ Назад к нише", "callback_data": f"niche_cfg:{niche_key}"}])
        return text, {"inline_keyboard": rows}

    def build_rating_presets_menu(self, niche_key: str) -> tuple[str, Dict[str, Any]]:
        """Кнопки выбора рейтинга."""
        n_cfg = get_niche(niche_key)
        text = f"⭐ <b>Выберите минимальный рейтинг товаров для «{n_cfg.name}»:</b>"
        presets = [4.5, 4.6, 4.7, 4.8, 4.9]
        rows = [[{"text": f"⭐ {r}+", "callback_data": f"save_rat:{niche_key}:{r}"} for r in presets]]
        rows.append([{"text": "◀️ Назад к нише", "callback_data": f"niche_cfg:{niche_key}"}])
        return text, {"inline_keyboard": rows}

    def build_reviews_presets_menu(self, niche_key: str) -> tuple[str, Dict[str, Any]]:
        """Кнопки выбора минимального количества отзывов."""
        n_cfg = get_niche(niche_key)
        text = f"💬 <b>Выберите минимальное число отзывов для «{n_cfg.name}»:</b>"
        presets = [5, 10, 15, 25, 50, 100]
        rows = [
            [{"text": f"{p}+ отзывов", "callback_data": f"save_rev:{niche_key}:{p}"} for p in presets[:3]],
            [{"text": f"{p}+ отзывов", "callback_data": f"save_rev:{niche_key}:{p}"} for p in presets[3:]],
            [{"text": "◀️ Назад к нише", "callback_data": f"niche_cfg:{niche_key}"}]
        ]
        return text, {"inline_keyboard": rows}

    # ---------------------------------------------------------
    # Обработка действий
    # ---------------------------------------------------------

    def handle_callback(self, cq: Dict[str, Any]):
        """Обрабатывает нажатия на inline-кнопки."""
        cq_id = cq["id"]
        data = cq.get("data", "")
        message = cq.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        msg_id = message.get("message_id")

        # Безопасность: доступ только для доверенного чата администратора
        if self.admin_chat_id and chat_id != self.admin_chat_id:
            self.notifier.answer_callback(cq_id, "Доступ запрещен!")
            return

        self.notifier.answer_callback(cq_id)

        # Главное меню
        if data == "menu:main":
            t, kb = self.build_main_menu()
            self.notifier.edit_message_text(t, message_id=msg_id, reply_markup=kb, chat_id=chat_id)

        # Список ниш для настройки
        elif data == "menu:niches":
            t, kb = self.build_niches_list_menu("niche_cfg")
            self.notifier.edit_message_text(t, message_id=msg_id, reply_markup=kb, chat_id=chat_id)

        # Список ниш для ручного парсинга
        elif data == "menu:parse_select":
            t, kb = self.build_niches_list_menu("parse_niche")
            self.notifier.edit_message_text("🔍 <b>Выберите нишу для поиска товаров:</b>", message_id=msg_id, reply_markup=kb, chat_id=chat_id)

        # Экран конкретной ниши
        elif data.startswith("niche_cfg:"):
            slug = data.split(":", 1)[1]
            t, kb = self.build_niche_settings_menu(slug)
            self.notifier.edit_message_text(t, message_id=msg_id, reply_markup=kb, chat_id=chat_id)

        # Меню выбора цен
        elif data.startswith("set_maxp_menu:"):
            slug = data.split(":", 1)[1]
            t, kb = self.build_price_presets_menu(slug, "max")
            self.notifier.edit_message_text(t, message_id=msg_id, reply_markup=kb, chat_id=chat_id)

        elif data.startswith("set_minp_menu:"):
            slug = data.split(":", 1)[1]
            t, kb = self.build_price_presets_menu(slug, "min")
            self.notifier.edit_message_text(t, message_id=msg_id, reply_markup=kb, chat_id=chat_id)

        # Сохранение выбранной цены
        elif data.startswith("save_p:"):
            parts = data.split(":")
            slug, p_type, val = parts[1], parts[2], int(parts[3])
            if p_type == "max":
                save_niche_settings(slug, max_price=val)
            else:
                save_niche_settings(slug, min_price=val)
            t, kb = self.build_niche_settings_menu(slug)
            self.notifier.edit_message_text(f"✅ Цена успешно сохранена!\n\n" + t, message_id=msg_id, reply_markup=kb, chat_id=chat_id)

        # Меню выбора рейтинга и отзывов
        elif data.startswith("set_rat_menu:"):
            slug = data.split(":", 1)[1]
            t, kb = self.build_rating_presets_menu(slug)
            self.notifier.edit_message_text(t, message_id=msg_id, reply_markup=kb, chat_id=chat_id)

        elif data.startswith("save_rat:"):
            parts = data.split(":")
            slug, val = parts[1], float(parts[2])
            save_niche_settings(slug, min_rating=val)
            t, kb = self.build_niche_settings_menu(slug)
            self.notifier.edit_message_text(f"✅ Рейтинг {val}+ сохранен!\n\n" + t, message_id=msg_id, reply_markup=kb, chat_id=chat_id)

        elif data.startswith("set_rev_menu:"):
            slug = data.split(":", 1)[1]
            t, kb = self.build_reviews_presets_menu(slug)
            self.notifier.edit_message_text(t, message_id=msg_id, reply_markup=kb, chat_id=chat_id)

        elif data.startswith("save_rev:"):
            parts = data.split(":")
            slug, val = parts[1], int(parts[2])
            save_niche_settings(slug, min_reviews=val)
            t, kb = self.build_niche_settings_menu(slug)
            self.notifier.edit_message_text(f"✅ Порог отзывов {val}+ сохранен!\n\n" + t, message_id=msg_id, reply_markup=kb, chat_id=chat_id)

        # Запрос текстового направления (единственное текстовое действие)
        elif data.startswith("ask_focus:"):
            slug = data.split(":", 1)[1]
            n_cfg = get_niche(slug)
            self.user_states[chat_id] = {"action": "wait_focus", "niche": slug}
            cancel_kb = {"inline_keyboard": [[{"text": "❌ Отмена", "callback_data": f"niche_cfg:{slug}"}]]}
            self.notifier.send_message(
                f"🎯 <b>Задайте направление поиска (поднишу) для «{n_cfg.name}»:</b>\n\n"
                f"Напечатайте то, что вам нужно найти прямо сейчас.\n"
                f"<i>Примеры:</i>\n"
                f"• <code>беспроводные петлички</code>\n"
                f"• <code>органайзер в багажник</code>\n"
                f"• <code>оверсайз худи</code>\n"
                f"• <code>набор ножей с подставкой</code>",
                reply_markup=cancel_kb,
                chat_id=chat_id
            )

        # Сброс подниши
        elif data.startswith("clear_focus:"):
            slug = data.split(":", 1)[1]
            save_niche_settings(slug, custom_focus="")
            t, kb = self.build_niche_settings_menu(slug)
            self.notifier.edit_message_text("🧹 Поисковое направление сброшено на стандартное.\n\n" + t, message_id=msg_id, reply_markup=kb, chat_id=chat_id)

        # Ручной парсинг ниши
        elif data.startswith("parse_niche:"):
            slug = data.split(":", 1)[1]
            n_cfg = get_niche(slug)
            self.notifier.send_message(f"⏳ Начинаю поиск на Kaspi для «{n_cfg.name}» с учётом ваших настроек цен и фильтров...", chat_id=chat_id)
            self._execute_parse_and_offer(slug, chat_id)

        # Аналитика
        elif data == "act:analytics":
            self.notifier.send_analytics_only()

        # Ручное поднятие WhatsApp-сервера
        elif data == "act:start_server":
            from daily_runner import is_bridge_online, ensure_bridge_running
            if is_bridge_online():
                self.notifier.send_message("✅ WhatsApp-сервер уже запущен и готов к работе!", chat_id=chat_id)
            else:
                self.notifier.send_message("⏳ Поднимаю WhatsApp-сервер на ноутбуке...", chat_id=chat_id)
                ok = ensure_bridge_running()
                if ok:
                    self.notifier.send_message("🟢 <b>WhatsApp-сервер успешно запущен!</b>", chat_id=chat_id)
                else:
                    self.notifier.send_message("❌ Не удалось поднять WhatsApp-сервер. Проверьте QR-код или статус моста.", chat_id=chat_id)

        # Ручное выключение WhatsApp-сервера
        elif data == "act:stop_server":
            from daily_runner import stop_bridge
            self.notifier.send_message("⏳ Останавливаю WhatsApp-сервер...", chat_id=chat_id)
            stop_bridge()
            self.notifier.send_message("🛑 <b>WhatsApp-сервер выключен.</b> Ресурсы ноутбука свободны.", chat_id=chat_id)

        # Полный автоматический цикл (поднятие сервера ➔ парсинг ➔ отправка ➔ выключение сервера)
        elif data == "act:run_full_cycle":
            self.notifier.send_message(
                "⚡ <b>Запуск разового цикла:</b>\n"
                "1. Поднятие WhatsApp-сервера\n"
                "2. Парсинг и отбор товаров Kaspi\n"
                "3. Отправка по 1 карточке во все каналы\n"
                "4. Отчёт с аналитикой\n"
                "5. Автоматическое выключение сервера...",
                chat_id=chat_id
            )
            from daily_runner import run_session, stop_bridge
            run_session(dry_run=False)
            stop_bridge()
            self.notifier.send_message("💤 <b>Сессия завершена:</b> WhatsApp-сервер автоматически выключен.", chat_id=chat_id)

        # Отправка товаров во все каналы
        elif data == "act:post_all_wa":
            self.notifier.send_message("🚀 Запускаю отправку по 1 товару во все 6 каналов WhatsApp...", chat_id=chat_id)
            from daily_runner import post_one_item_per_niche
            sent, items = post_one_item_per_niche(dry_run=False)
            self.notifier.send_session_report("Ручной запуск из бота", sent, 0.0, items)

        # Одобрение карточки товара для отправки в WhatsApp
        elif data.startswith("approve_post:"):
            post_id = int(data.split(":", 1)[1])
            self._publish_single_post(post_id, chat_id, msg_id)

        # Пропуск карточки
        elif data.startswith("reject_post:"):
            post_id = int(data.split(":", 1)[1])
            mark_post_failed_wa(post_id, "Отклонено пользователем через бота")
            self.notifier.edit_message_text("❌ Товар пропущен и снят с очереди публикации.", message_id=msg_id, chat_id=chat_id)

    def _execute_parse_and_offer(self, niche_key: str, chat_id: str):
        """Парсит товары по нише и предлагает карточки с кнопками одобрения."""
        parser = KaspiParser()
        cw = Copywriter()
        n_cfg = get_niche(niche_key)

        try:
            found = parser.parse_niche(niche_key=niche_key, limit=3)
            if not found:
                self.notifier.send_message(f"ℹ️ Для «{n_cfg.name}» по заданным фильтрам новых уникальных товаров не найдено.", chat_id=chat_id)
                return

            added_posts = []
            for item in found:
                if save_product(item):
                    pending = get_pending_wa_posts(niche=niche_key, limit=10)
                    for p in pending:
                        if str(p["kaspi_id"]) == str(item["kaspi_id"]):
                            added_posts.append(p)
                            break

            self.notifier.send_message(f"🎉 Найдено <b>{len(added_posts)}</b> свежих товаров. Ниже карточки для модерации:", chat_id=chat_id)

            for post in added_posts:
                post_id = post["id"]
                title = post.get("title", "")
                price = post.get("price", 0)
                rating = post.get("rating", 0.0)
                reviews = post.get("reviews_quantity", 0)
                link = post.get("shop_link", "")

                card_text = (
                    f"📦 <b>{self.notifier._escape_html(title)}</b>\n"
                    f"🏷️ <b>Ниша:</b> {n_cfg.name}\n"
                    f"💰 <b>Цена:</b> {price:,} ₸\n".replace(",", " ") +
                    f"⭐ <b>Рейтинг:</b> {rating} ({reviews} отзывов)\n"
                    f"🔗 <a href=\"{link}\">Открыть на Kaspi</a>"
                )

                kb = {
                    "inline_keyboard": [
                        [
                            {"text": "✅ Опубликовать в WhatsApp", "callback_data": f"approve_post:{post_id}"},
                            {"text": "❌ Пропустить", "callback_data": f"reject_post:{post_id}"}
                        ]
                    ]
                }
                self.notifier.send_message(card_text, reply_markup=kb, chat_id=chat_id)

        except Exception as e:
            self.notifier.send_message(f"❌ Ошибка при поиске: {e}", chat_id=chat_id)

    def _publish_single_post(self, post_id: int, chat_id: str, message_id: int):
        """Публикует выбранный товар в соответствующую группу WhatsApp."""
        post = get_post_by_id(post_id)
        if not post:
            self.notifier.edit_message_text("⚠️ Товар не найден в базе.", message_id=message_id, chat_id=chat_id)
            return

        n_key = post.get("niche", "general")
        n_cfg = get_niche(n_key)
        wa_chat_id = get_chat_id_for_niche(n_key)

        if not wa_chat_id:
            self.notifier.edit_message_text(f"⚠️ Для ниши «{n_key}» не настроен Chat ID в .env!", message_id=message_id, chat_id=chat_id)
            return

        cw = Copywriter()
        caption = post.get("wa_caption") or cw.generate_post(post)
        update_post_caption(post_id, caption)

        images = post.get("images", [])
        image_url = images[0] if images else None

        exporter = SocialExporter()
        import os
        temp_dir = os.path.join(os.path.dirname(__file__), "temp")
        os.makedirs(temp_dir, exist_ok=True)
        local_img = os.path.join(temp_dir, f"post_{post['kaspi_id']}.jpg")
        image_to_send = image_url

        if image_url and exporter.download_image(image_url, local_img, add_badge=True):
            image_to_send = os.path.abspath(local_img)

        payload = {"chatId": wa_chat_id, "imageUrl": image_to_send, "caption": caption}
        try:
            req = urllib.request.Request(
                f"{WA_BRIDGE_URL}/send",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                if res.get("success"):
                    msg_id = res.get("messageId", "ok")
                    mark_post_published_wa(post_id, wa_chat_id, msg_id)
                    n_name = n_cfg.name if n_cfg else n_key
                    self.notifier.edit_message_text(f"✅ <b>Успешно отправлено в WhatsApp!</b>\nКанал: {n_name}\nMsg ID: {msg_id}", message_id=message_id, chat_id=chat_id)
                else:
                    mark_post_failed_wa(post_id)
                    self.notifier.edit_message_text(f"❌ Ошибка отправки моста: {res}", message_id=message_id, chat_id=chat_id)
        except Exception as e:
            mark_post_failed_wa(post_id)
            self.notifier.edit_message_text(f"❌ Исключение при отправке: {e}", message_id=message_id, chat_id=chat_id)
        finally:
            if os.path.exists(local_img):
                try:
                    os.remove(local_img)
                except Exception:
                    pass

    def handle_text_message(self, msg: Dict[str, Any]):
        """Обрабатывает текстовые сообщения."""
        chat_id = str(msg.get("chat", {}).get("id", ""))
        text = msg.get("text", "").strip()

        if self.admin_chat_id and chat_id != self.admin_chat_id:
            return

        # Команды старта и вызова меню
        if text in ["/start", "/menu", "меню", "start"]:
            t, kb = self.build_main_menu()
            self.notifier.send_message(t, reply_markup=kb, chat_id=chat_id)
            return

        # Если находимся в состоянии ожидания направления подниши
        state = self.user_states.get(chat_id)
        if state and state.get("action") == "wait_focus":
            niche_key = state.get("niche")
            n_cfg = get_niche(niche_key)
            save_niche_settings(niche_key, custom_focus=text)
            del self.user_states[chat_id]

            t, kb = self.build_niche_settings_menu(niche_key)
            self.notifier.send_message(
                f"🎯 <b>Направление для «{n_cfg.name}» успешно задано:</b>\n"
                f"<code>{text}</code>\n\n"
                f"Теперь при парсинге бот будет искать товары именно по этому запросу!\n\n" + t,
                reply_markup=kb,
                chat_id=chat_id
            )
            return

        # Если пользователь просто отправил текст не из контекста
        t, kb = self.build_main_menu()
        self.notifier.send_message(
            "Для управления используйте кнопки интерфейса:\n",
            reply_markup=kb,
            chat_id=chat_id
        )

    def run_polling(self):
        """Запуск бесконечного цикла Long Polling."""
        print("🤖 Telegram Bot Controller запущен в режиме ожидания команд...")
        print(f"👤 Авторизованный Chat ID: {self.admin_chat_id}")
        t, kb = self.build_main_menu()
        self.notifier.send_message(t, reply_markup=kb)

        while True:
            try:
                updates = self.get_updates(offset=self.last_update_id + 1, timeout=20)
                for u in updates:
                    self.last_update_id = u["update_id"]

                    if "callback_query" in u:
                        self.handle_callback(u["callback_query"])
                    elif "message" in u and "text" in u["message"]:
                        self.handle_text_message(u["message"])

                time.sleep(0.5)
            except KeyboardInterrupt:
                print("\n🛑 Остановка Telegram Bot Controller...")
                break
            except Exception as e:
                time.sleep(3)


if __name__ == "__main__":
    controller = TelegramBotController()
    controller.run_polling()
