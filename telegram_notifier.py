import os
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, NICHES, get_niche
from storage import get_analytics_summary


class TelegramNotifier:
    """Модуль отправки отчетов о публикациях в WhatsApp и аналитики в Telegram."""

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = (bot_token or TELEGRAM_BOT_TOKEN or "").strip()
        self.chat_id = str(chat_id or TELEGRAM_CHAT_ID or "").strip()
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"

    def is_configured(self) -> bool:
        """Проверяет, заданы ли токен и chat_id."""
        return bool(self.bot_token and self.chat_id)

    def send_message(
        self,
        text: str,
        parse_mode: str = "HTML",
        disable_preview: bool = False,
        reply_markup: Optional[Dict[str, Any]] = None,
        chat_id: Optional[str] = None
    ) -> bool:
        """Отправляет текстовое сообщение в Telegram через Bot API с поддержкой кнопок."""
        if not self.is_configured():
            return False

        target_chat = chat_id or self.chat_id
        url = f"{self.api_url}/sendMessage"
        payload = {
            "chat_id": target_chat,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_preview
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return bool(data.get("ok"))
        except Exception as e:
            print(f"⚠️ Ошибка отправки в Telegram: {e}")
            return False

    def edit_message_text(
        self,
        text: str,
        message_id: int,
        parse_mode: str = "HTML",
        reply_markup: Optional[Dict[str, Any]] = None,
        chat_id: Optional[str] = None
    ) -> bool:
        """Редактирует текст существующего сообщения."""
        if not self.is_configured():
            return False

        target_chat = chat_id or self.chat_id
        url = f"{self.api_url}/editMessageText"
        payload = {
            "chat_id": target_chat,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return bool(data.get("ok"))
        except Exception as e:
            print(f"⚠️ Ошибка редактирования сообщения в Telegram: {e}")
            return False

    def answer_callback(self, callback_query_id: str, text: Optional[str] = None) -> bool:
        """Подтверждает получение callback нажатия кнопки."""
        if not self.is_configured():
            return False

        url = f"{self.api_url}/answerCallbackQuery"
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return bool(data.get("ok"))
        except Exception:
            return False

    def notify_product_posted(self, product: Dict[str, Any], chat_name_or_id: str, success: bool = True, error: str = ""):
        """
        Отправляет отчет об отправке карточки товара в WhatsApp группу.
        """
        if not self.is_configured():
            return

        title = product.get("title", "Без названия")
        niche_key = product.get("niche", "general")
        n_cfg = get_niche(niche_key)
        niche_title = n_cfg.name if n_cfg else niche_key

        price = product.get("price", 0)
        old_price = product.get("price_before_discount")
        rating = product.get("rating", 0.0)
        reviews = product.get("reviews_quantity", 0)
        kaspi_id = product.get("kaspi_id", "")
        link = product.get("shop_link") or f"https://kaspi.kz/shop/p/-{kaspi_id}/"

        price_str = f"<b>{price:,} ₸</b>".replace(",", " ")
        if old_price and old_price > price:
            price_str += f" <s>{old_price:,} ₸</s>".replace(",", " ")

        status_emoji = "✅" if success else "❌"
        status_line = f"{status_emoji} <b>Опубликовано в WhatsApp</b>" if success else f"{status_emoji} <b>Ошибка отправки</b>: {error}"

        text = (
            f"{status_line}\n\n"
            f"📦 <b>Товар:</b> <a href=\"{link}\">{self._escape_html(title)}</a>\n"
            f"🏷️ <b>Ниша:</b> {niche_title}\n"
            f"💰 <b>Цена:</b> {price_str}\n"
            f"⭐ <b>Рейтинг:</b> {rating} ({reviews} отзывов)\n"
            f"💬 <b>Канал WhatsApp:</b> {self._escape_html(chat_name_or_id)}"
        )

        self.send_message(text, parse_mode="HTML", disable_preview=False)

    def send_session_report(self, session_name: str, posted_count: int, elapsed_sec: float, items_summary: Optional[List[Dict[str, Any]]] = None):
        """
        Отправляет сводный отчёт по результатам сессии автопостинга + краткую аналитику.
        """
        if not self.is_configured():
            return

        analytics = get_analytics_summary()

        # Формируем список опубликованных товаров
        items_block = ""
        if items_summary:
            lines = []
            for item in items_summary:
                p_title = item.get("title", "")[:35]
                p_niche = item.get("niche_name", item.get("niche", ""))
                p_price = f"{item.get('price', 0):,} ₸".replace(",", " ")
                lines.append(f"• <b>[{p_niche}]</b> {self._escape_html(p_title)}... — {p_price}")
            items_block = "\n<b>Опубликованные карточки:</b>\n" + "\n".join(lines) + "\n"

        # Формируем статус буфера по нишам
        buffer_lines = []
        for slug, n_cfg in NICHES.items():
            st = analytics["niches"].get(slug, {})
            pending = st.get("pending", 0)
            indicator = "🟢" if pending >= 4 else ("🟡" if pending >= 2 else "🔴")
            buffer_lines.append(f"{indicator} <b>{n_cfg.name}:</b> {pending} шт. в очереди")

        niche_buffer_block = "\n".join(buffer_lines)

        report = (
            f"📊 <b>ОТЧЁТ: {session_name.upper()} ЗАПУСК</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 <b>Отправлено в WhatsApp:</b> {posted_count} карточек\n"
            f"⏱ <b>Время выполнения:</b> {elapsed_sec:.1f} сек.\n"
            f"{items_block}\n"
            f"📈 <b>КРАТКАЯ АНАЛИТИКА:</b>\n"
            f"• <b>Опубликовано сегодня:</b> {analytics['posted_today']} шт.\n"
            f"• <b>Всего отправлено за все время:</b> {analytics['total_posted']} шт.\n"
            f"• <b>Средний чек товаров:</b> {analytics['avg_price']:,} ₸\n".replace(",", " ") +
            f"• <b>Средний рейтинг товаров:</b> ⭐ {analytics['avg_rating']}\n\n"
            f"📦 <b>БУФЕР ОЧЕРЕДИ (ГОТОВЫ К ПОСТИНГУ):</b>\n"
            f"{niche_buffer_block}\n\n"
            f"Всего товаров в базе: {analytics['total_products']} шт."
        )

        self.send_message(report, parse_mode="HTML", disable_preview=True)

    def send_analytics_only(self):
        """Отправляет отдельную подробную аналитику по запросу."""
        if not self.is_configured():
            return False

        analytics = get_analytics_summary()

        buffer_lines = []
        for slug, n_cfg in NICHES.items():
            st = analytics["niches"].get(slug, {})
            pending = st.get("pending", 0)
            posted = st.get("posted", 0)
            avg_p = f"{st.get('avg_price', 0):,} ₸".replace(",", " ")
            indicator = "🟢" if pending >= 4 else ("🟡" if pending >= 2 else "🔴")
            buffer_lines.append(
                f"{indicator} <b>{n_cfg.name}</b>\n"
                f"   └ В очереди: {pending} | Опубликовано: {posted} | Ср. цена: {avg_p}"
            )

        niche_block = "\n".join(buffer_lines)

        msg = (
            f"📊 <b>ТЕКУЩАЯ АНАЛИТИКА КАТАЛОГА KASPI</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>Всего товаров в базе:</b> {analytics['total_products']} шт.\n"
            f"📤 <b>Опубликовано сегодня:</b> {analytics['posted_today']} шт.\n"
            f"📨 <b>Всего отправлено в WhatsApp:</b> {analytics['total_posted']} шт.\n"
            f"⏳ <b>Ожидают публикации:</b> {analytics['total_pending']} шт.\n\n"
            f"💰 <b>Финансовые метрики:</b>\n"
            f"• Средний чек: <b>{analytics['avg_price']:,} ₸</b>\n".replace(",", " ") +
            f"• Диапазон цен: {analytics['min_price']:,} ₸ – {analytics['max_price']:,} ₸\n".replace(",", " ") +
            f"• Средний рейтинг: ⭐ <b>{analytics['avg_rating']}</b>\n\n"
            f"🏷️ <b>Разбивка по 6 нишам:</b>\n"
            f"{niche_block}"
        )

        return self.send_message(msg, parse_mode="HTML", disable_preview=True)

    def _escape_html(self, text: str) -> str:
        """Экранирует спецсимволы для HTML разметки Telegram."""
        if not text:
            return ""
        return (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
        )
