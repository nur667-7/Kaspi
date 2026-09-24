import os
import sys
import json
import time
import shutil
import urllib.request
import subprocess
from datetime import datetime
from typing import Dict, Any, List, Optional

# Обеспечиваем правильный import модулей из текущей директории
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Настройка UTF-8 для Windows консоли
if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import (
    WA_BRIDGE_URL,
    WA_BRIDGE_PORT,
    NICHES,
    get_niche,
    get_chat_id_for_niche
)
from storage import (
    get_pending_wa_posts,
    save_product,
    update_post_caption,
    mark_post_published_wa,
    mark_post_failed_wa
)
from kaspi_parser import KaspiParser
from google_sheets_sync import GoogleSheetsSync
from copywriter import Copywriter
from social_exporter import SocialExporter
from telegram_notifier import TelegramNotifier

LOG_FILE = os.path.join(BASE_DIR, "daily_run.log")
TEMP_DIR = os.path.join(BASE_DIR, "temp")


def log(msg: str):
    """Выводит сообщение в консоль и дописывает в daily_run.log."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        print(line)
    except Exception:
        try:
            print(line.encode("ascii", errors="replace").decode("ascii"))
        except Exception:
            pass
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def truncate_log_if_needed(max_bytes: int = 500_000, keep_lines: int = 500):
    """Предотвращает разрастание лога на диске ноутбука (zero bloat)."""
    if not os.path.exists(LOG_FILE):
        return
    try:
        if os.path.getsize(LOG_FILE) > max_bytes:
            with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.writelines(lines[-keep_lines:])
    except Exception:
        pass


def purge_temp():
    """Полное удаление всех временных файлов и картинок (Zero-Trash Policy)."""
    if not os.path.exists(TEMP_DIR):
        return
    deleted_count = 0
    for root, dirs, files in os.walk(TEMP_DIR, topdown=False):
        for f in files:
            p = os.path.join(root, f)
            try:
                os.remove(p)
                deleted_count += 1
            except Exception:
                pass
        for d in dirs:
            p = os.path.join(root, d)
            try:
                shutil.rmtree(p, ignore_errors=True)
            except Exception:
                pass
    if deleted_count > 0:
        log(f"🧹 Zero-Trash: очищено {deleted_count} временных файлов в папке temp.")


def is_bridge_online() -> bool:
    """Проверяет доступность и авторизацию локального WhatsApp Baileys моста."""
    try:
        req = urllib.request.Request(f"{WA_BRIDGE_URL}/status")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return bool(data.get("connected"))
    except Exception:
        return False


def ensure_bridge_running() -> bool:
    """Проверяет мост и автоматически поднимает его в фоне, если он упал."""
    if is_bridge_online():
        return True

    log("⚠️ WhatsApp мост оффлайн. Попытка фонового запуска node server.js...")
    wa_bridge_dir = os.path.join(BASE_DIR, "wa_bridge")
    server_js = os.path.join(wa_bridge_dir, "server.js")

    if not os.path.exists(server_js):
        log(f"❌ Ошибка: Файл {server_js} не найден!")
        return False

    try:
        # Запуск в отдельном независимом фоновом процессе Windows
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        subprocess.Popen(
            ["node", "server.js"],
            cwd=wa_bridge_dir,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        log(f"❌ Не удалось запустить node server.js: {e}")
        return False

    # Ожидание инициализации сокета и авторизации
    for i in range(12):
        time.sleep(2)
        if is_bridge_online():
            log("✅ WhatsApp мост успешно подключен и готов к работе!")
            return True

    log("❌ WhatsApp мост не ответил за 24 секунды. Проверьте QR-код или порт 3000.")
    return False


def stop_bridge() -> bool:
    """Удалённо останавливает WhatsApp мост и освобождает память ноутбука."""
    if not is_bridge_online():
        log("ℹ️ WhatsApp мост уже остановлен.")
        return True

    try:
        req = urllib.request.Request(
            f"{WA_BRIDGE_URL}/shutdown",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            log("🛑 WhatsApp мост успешно выключен.")
            return True
    except Exception:
        # Fallback на завершение процесса через OS Windows
        try:
            subprocess.run(["taskkill", "/F", "/IM", "node.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log("🛑 Процесс Node.js принудительно остановлен.")
            return True
        except Exception as e:
            log(f"⚠️ Не удалось остановить процесс node.exe: {e}")
            return False


def replenish_buffer_if_needed(min_threshold: int = 2, fetch_limit: int = 4):
    """
    Проверяет банк товаров каждой ниши.
    Если свободных товаров осталось меньше min_threshold — парсит Kaspi,
    синхронизирует с Google Sheets и готовит тексты.
    """
    parser = KaspiParser()
    sheets_sync = GoogleSheetsSync()
    cw = Copywriter()

    for n_key, n_cfg in NICHES.items():
        pending = get_pending_wa_posts(niche=n_key, limit=10)
        pending_count = len(pending)

        if pending_count < min_threshold:
            needed = fetch_limit
            log(f"📦 Ниша '{n_cfg.name}' ({n_key}): в буфере {pending_count} шт. (порог {min_threshold}). Ищем свежие находки на Kaspi...")
            try:
                found = parser.parse_niche(niche_key=n_key, limit=needed)
                added = 0
                for item in found:
                    if save_product(item):
                        added += 1
                        if sheets_sync.is_configured():
                            sheets_sync.send_product(item, n_cfg.name)
                log(f"  📥 Сохранено {added} новых товаров для '{n_cfg.name}', отправлено в Google Sheets.")
            except Exception as e:
                log(f"  ❌ Ошибка парсинга ниши {n_key}: {e}")

    # Предварительная генерация текстов для постов без caption
    all_pending = get_pending_wa_posts(limit=30)
    for p in all_pending:
        if not p.get("wa_caption"):
            try:
                caption = cw.generate_post(p)
                update_post_caption(p["id"], caption)
            except Exception as e:
                log(f"  ⚠️ Ошибка генерации текста для поста #{p['id']}: {e}")


def post_one_item_per_niche(dry_run: bool = False) -> tuple[int, List[Dict[str, Any]]]:
    """
    Публикует строго по 1 товару в каждую из 6 ниш.
    При утреннем и вечернем запуске суммарно дает ровно 2 товара в день на нишу.
    Возвращает (количество отправленных, список отправленных товаров).
    """
    cw = Copywriter()
    exporter = SocialExporter()
    tg = TelegramNotifier()
    os.makedirs(TEMP_DIR, exist_ok=True)

    sent_count = 0
    posted_items = []

    for n_key, n_cfg in NICHES.items():
        chat_id = get_chat_id_for_niche(n_key)
        if not chat_id:
            log(f"⚠️ Ниша '{n_cfg.name}': Chat ID не настроен в .env, пропуск.")
            continue

        pending = get_pending_wa_posts(niche=n_key, limit=1)
        if not pending:
            log(f"ℹ️ Ниша '{n_cfg.name}': нет товаров в очереди даже после пополнения.")
            continue

        post = pending[0]
        post_id = post["id"]
        kaspi_id = post["kaspi_id"]
        title = post.get("title", "")

        caption = post.get("wa_caption")
        if not caption:
            caption = cw.generate_post(post)
            update_post_caption(post_id, caption)

        images = post.get("images", [])
        image_url = images[0] if images else None

        image_to_send = image_url
        local_branded_img = os.path.join(TEMP_DIR, f"post_{kaspi_id}.jpg")

        if dry_run:
            log(f"🔍 [DRY-RUN] Ниша '{n_cfg.name}': был бы отправлен товар #{kaspi_id} ({title[:35]}...) в {chat_id}")
            sent_count += 1
            posted_items.append({
                "title": title,
                "niche": n_key,
                "niche_name": n_cfg.name,
                "price": post.get("price", 0),
                "kaspi_id": kaspi_id
            })
            continue

        try:
            # 1. Скачиваем и брендируем аватаркой Kaspi во временный файл
            if image_url and exporter.download_image(image_url, local_branded_img, add_badge=True):
                image_to_send = os.path.abspath(local_branded_img)

            # 2. Отправляем в WhatsApp через Baileys мост
            payload = {
                "chatId": chat_id,
                "imageUrl": image_to_send,
                "caption": caption
            }

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
                    mark_post_published_wa(post_id, chat_id, msg_id)
                    sent_count += 1
                    posted_items.append({
                        "title": title,
                        "niche": n_key,
                        "niche_name": n_cfg.name,
                        "price": post.get("price", 0),
                        "kaspi_id": kaspi_id
                    })
                    log(f"✅ [{n_cfg.name}] Опубликовано: #{kaspi_id} «{title[:30]}...» (MsgID: {msg_id})")

                    # Отправляем краткий отчёт по карточке в Telegram
                    tg.notify_product_posted(post, chat_name_or_id=n_cfg.name, success=True)
                else:
                    mark_post_failed_wa(post_id)
                    log(f"❌ [{n_cfg.name}] Ошибка отправки моста: {res}")
                    tg.notify_product_posted(post, chat_name_or_id=n_cfg.name, success=False, error=str(res))
        except Exception as e:
            mark_post_failed_wa(post_id)
            log(f"❌ [{n_cfg.name}] Исключение при отправке #{kaspi_id}: {e}")
            tg.notify_product_posted(post, chat_name_or_id=n_cfg.name, success=False, error=str(e))
        finally:
            # МГНОВЕННОЕ удаление временного файла — Zero Trash Policy
            if os.path.exists(local_branded_img):
                try:
                    os.remove(local_branded_img)
                except Exception:
                    pass

        # Пауза между сообщениями против спам-фильтров WhatsApp
        time.sleep(3.0)

    return sent_count, posted_items


def run_session(dry_run: bool = False):
    """Полная рабочая сессия (утренняя или вечерняя)."""
    start_time = time.time()
    session_label = "Утренний" if datetime.now().hour < 15 else "Вечерний"

    log("=" * 60)
    log(f"🚀 СТАРТ АВТОМАТИЧЕСКОЙ СЕССИИ [{session_label.upper()} ЗАПУСК]")
    log("=" * 60)

    # 1. Зачистка до начала работы
    purge_temp()
    truncate_log_if_needed()

    # 2. Проверка и поднятие моста
    if not dry_run and not ensure_bridge_running():
        log("❌ Сессия прервана: WhatsApp мост недоступен.")
        tg = TelegramNotifier()
        tg.send_message(f"⚠️ <b>Внимание:</b> Сессия {session_label} прервана, так как WhatsApp мост недоступен!")
        return

    # 3. Проверка и пополнение буфера товаров
    replenish_buffer_if_needed(min_threshold=2, fetch_limit=4)

    # 4. Отправка ровно по 1 товару в каждую нишу
    total_posted, posted_items = post_one_item_per_niche(dry_run=dry_run)

    # 5. Финальная зачистка временных файлов (Zero Trash Policy)
    purge_temp()

    elapsed = round(time.time() - start_time, 1)
    log("=" * 60)
    log(f"🎉 СЕССИЯ ЗАВЕРШЕНА: Опубликовано {total_posted} товаров за {elapsed} сек. Диск чист (0 мусора).")
    log("=" * 60 + "\n")

    # 6. Отправка сводного отчета и краткой аналитики в Telegram
    tg = TelegramNotifier()
    tg.send_session_report(
        session_name=session_label,
        posted_count=total_posted,
        elapsed_sec=elapsed,
        items_summary=posted_items
    )


if __name__ == "__main__":
    is_dry = "--dry-run" in sys.argv
    run_session(dry_run=is_dry)
