import argparse
import sys
import json
import urllib.request
import os
from typing import Optional

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Загружаем переменные из .env, если файл существует
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

from config import NICHES, get_niche, get_chat_id_for_niche, WA_BRIDGE_URL
from storage import (
    save_product, get_pending_wa_posts, update_post_caption,
    mark_post_published_wa, mark_post_failed_wa, get_db_stats
)
from kaspi_parser import KaspiParser
from copywriter import Copywriter
from social_exporter import SocialExporter
from google_sheets_sync import GoogleSheetsSync

def cmd_list_niches(args):
    """Выводит список всех настроенных ниш."""
    print("\n" + "="*60)
    print("СПИСОК ПОДДЕРЖИВАЕМЫХ НИШ И КАНАЛОВ:")
    print("="*60)
    for slug, n in NICHES.items():
        chat_id = get_chat_id_for_niche(slug)
        chat_status = chat_id if chat_id else "(не задан в .env)"
        print(f"• [{slug}] {n.name}")
        print(f"  Макс. цена по умолчанию: {n.default_max_price:,} ₸".replace(",", " "))
        print(f"  Ключевые слова: {', '.join(n.keywords[:3])}...")
        print(f"  Привязанный Chat ID: {chat_status}\n")

def cmd_parse(args):
    """Парсит товары с Kaspi по выбранной нише или всем нишам."""
    parser = KaspiParser()
    target_niches = list(NICHES.keys()) if args.niche == "all" else [args.niche]

    total_added = 0
    for n_key in target_niches:
        n_cfg = get_niche(n_key)
        if not n_cfg:
            print(f"Ошибка: Неизвестная ниша '{n_key}'. Используйте команду 'list-niches'.")
            continue

        print(f"\n>>> Поиск товаров для ниши: {n_cfg.name} (лимит: {args.limit}) <<<")
        found = parser.parse_niche(
            niche_key=n_key,
            max_price=args.max_price,
            limit=args.limit
        )

        added_for_niche = 0
        sheets_sync = GoogleSheetsSync()
        for item in found:
            if save_product(item):
                added_for_niche += 1
                if sheets_sync.is_configured():
                    sheets_sync.send_product(item, n_cfg.name)

        total_added += added_for_niche
        print(f"Успешно сохранено новых товаров в БД: {added_for_niche}")

    print(f"\nВсего добавлено новых находок в банк: {total_added}")

def cmd_generate(args):
    """Генерирует продающие тексты для товаров, ожидающих публикации."""
    cw = Copywriter()
    pending = get_pending_wa_posts(niche=args.niche if args.niche != "all" else None, limit=args.limit)

    if not pending:
        print("Нет товаров, ожидающих генерации текста. Запустите парсинг (команда 'parse').")
        return

    print(f"\nГенерация продающих текстов для {len(pending)} товаров...")
    for post in pending:
        title = post.get("title", "")
        print(f"\n--- Обработка: {title[:40]}... [{post.get('niche')}] ---")
        caption = cw.generate_post(post)
        update_post_caption(post["id"], caption)
        print("Сгенерированный текст:\n")
        print(caption)
        print("\n" + "-"*40)

def cmd_post_wa(args):
    """Отправляет готовые посты в сообщество WhatsApp через локальный мост."""
    # Проверяем статус моста
    try:
        req = urllib.request.Request(f"{WA_BRIDGE_URL}/status")
        with urllib.request.urlopen(req, timeout=3) as resp:
            status_data = json.loads(resp.read().decode('utf-8'))
            if not status_data.get("connected"):
                print("❌ Ошибка: WhatsApp мост запущен, но не авторизован! Отсканируйте QR-код в консоли моста.")
                return
    except Exception:
        print(f"❌ Ошибка: WhatsApp мост не запущен на {WA_BRIDGE_URL}!")
        print("Запустите мост в отдельном терминале: cd wa_bridge && npm start")
        return

    cw = Copywriter()
    import time

    target_niches = list(NICHES.keys()) if (not args.niche or args.niche == "all") else [args.niche]
    total_sent = 0
    processed_niches = set()

    for niche_key in target_niches:
        pending = get_pending_wa_posts(niche=niche_key, limit=args.limit)
        if not pending:
            print(f"ℹ️ Ниша '{niche_key}': нет постов, ожидающих отправки.")
            continue

        n_cfg = NICHES.get(niche_key)
        n_name = n_cfg.name if n_cfg else niche_key
        print(f"\n" + "="*50)
        print(f"🚀 Ниша: {n_name} [{niche_key}] — отправка {len(pending)} товаров...")
        print("="*50)

        for post in pending:
            post_id = post["id"]
            chat_id = args.chat_id or get_chat_id_for_niche(niche_key)

            if not chat_id:
                print(f"⚠️ Пропуск: Для ниши '{niche_key}' не указан Chat ID! Укажите его в .env.")
                continue

            caption = post.get("wa_caption")
            if not caption:
                caption = cw.generate_post(post)
                update_post_caption(post_id, caption)

            images = post.get("images", [])
            image_url = images[0] if images else None

            # Брендируем фото фирменной круглой аватаркой Kaspi
            exporter = SocialExporter()
            image_to_send = image_url
            if image_url:
                temp_dir = os.path.join(os.path.dirname(__file__), "temp")
                os.makedirs(temp_dir, exist_ok=True)
                local_branded_img = os.path.join(temp_dir, f"post_{post['kaspi_id']}.jpg")
                if exporter.download_image(image_url, local_branded_img, add_badge=True):
                    image_to_send = os.path.abspath(local_branded_img)

            print(f"Отправка товара #{post['kaspi_id']} в {n_name} ({chat_id})...")
            payload = {
                "chatId": chat_id,
                "imageUrl": image_to_send,
                "caption": caption
            }

            try:
                req = urllib.request.Request(
                    f"{WA_BRIDGE_URL}/send",
                    data=json.dumps(payload).encode('utf-8'),
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=20) as resp:
                    res = json.loads(resp.read().decode('utf-8'))
                    if res.get("success"):
                        msg_id = res.get("messageId", "ok")
                        mark_post_published_wa(post_id, chat_id, msg_id)
                        processed_niches.add(niche_key)
                        total_sent += 1
                        print(f"  ✅ Успешно опубликовано! (ID: {msg_id})")
                    else:
                        mark_post_failed_wa(post_id)
                        print(f"  ❌ Ошибка отправки: {res}")
            except Exception as e:
                mark_post_failed_wa(post_id)
                print(f"  ❌ Ошибка при отправке через мост: {e}")
            finally:
                # Мгновенное удаление временного брендированного фото — zero trash policy
                if image_to_send and os.path.exists(image_to_send) and "temp" in image_to_send:
                    try:
                        os.remove(image_to_send)
                    except Exception:
                        pass

            time.sleep(2.5)

    # Гарантированная зачистка папки temp
    temp_dir = os.path.join(os.path.dirname(__file__), "temp")
    if os.path.exists(temp_dir):
        for f in os.listdir(temp_dir):
            try:
                os.remove(os.path.join(temp_dir, f))
            except Exception:
                pass

    # Сборка слайдов в Google Drive ТОЛЬКО если явно передан флаг --carousels
    if getattr(args, 'carousels', False) and processed_niches:
        print("\n" + "="*50)
        print("АВТОМАТИЧЕСКАЯ ГЕНЕРАЦИЯ СЛАЙДОВ ДЛЯ GOOGLE DRIVE:")
        print("="*50)
        from storage import get_candidates_for_social_carousel
        for n_key in processed_niches:
            candidates = get_candidates_for_social_carousel(n_key, count=4)
            if len(candidates) >= 3:
                print(f"\n🚀 Ниша '{n_key}': Найдено {len(candidates)} товара! Собираем 9:16 слайды и 4-в-1 коллаж...")
                exporter.export_niche_carousel(niche_key=n_key, count=min(len(candidates), 4))
            else:
                print(f"ℹ️ Ниша '{n_key}': сейчас {len(candidates)} товара (для полного пакета нужно 3-4).")

def cmd_pipeline(args):
    """Полный автоматический запуск от парсинга Kaspi до выгрузки в WhatsApp и Google Drive."""
    print("\n" + "="*60)
    print("🚀 СТАРТ ПОЛНОГО ЦИКЛА АВТОМАТИЗАЦИИ KASPI")
    print("="*60)
    print("1. Поиск свежих топовых находок на Kaspi...")
    cmd_parse(args)
    print("\n2. Создание продающих описаний...")
    cmd_generate(args)
    print("\n3. Публикация в каналы WhatsApp и сохранение слайдов в Google Drive...")
    cmd_post_wa(args)
    print("\n" + "="*60)
    print("🎉 ВЕСЬ ПРОЦЕСС УСПЕШНО ЗАВЕРШЕН!")
    print("="*60)

def cmd_build_slides(args):
    """Генерирует готовые графические слайды 9:16 и коллажи 4-в-1 для Google Drive."""
    exporter = SocialExporter()
    target_niches = list(NICHES.keys()) if args.niche == "all" else [args.niche]

    for n_key in target_niches:
        n_cfg = get_niche(n_key)
        name = n_cfg.name if n_cfg else n_key
        print(f"\n>>> Обработка ниши: {name} [{n_key}] <<<")
        batch_dir = exporter.export_niche_carousel(niche_key=n_key, count=args.count)
        if batch_dir:
            print(f"🎉 Готово! Папка: {batch_dir}")
        else:
            print(f"ℹ️ Нет новых товаров для карусели в нише '{name}'.")

def cmd_sync_sheets(args):
    """Синхронизирует все ссылки и товары из базы в онлайн Google Таблицу."""
    from google_sheets_sync import GoogleSheetsSync
    sync = GoogleSheetsSync()
    sync.sync_all_from_db()

def cmd_status(args):
    """Выводит сводную статистику по БД и мосту."""
    stats = get_db_stats()
    print("\n" + "="*50)
    print("СТАТИСТИКА БАНКА НАХОДОК KASPI:")
    print("="*50)
    print(f"Всего товаров в базе: {stats['total_products']}")
    
    print("\nПо нишам:")
    for niche, count in stats.get("by_niche", {}).items():
        n_cfg = get_niche(niche)
        name = n_cfg.name if n_cfg else niche
        print(f"  • {name} ({niche}): {count} шт.")

    print("\nСтатусы публикаций WhatsApp:")
    for st, count in stats.get("by_wa_status", {}).items():
        print(f"  • {st}: {count}")

    print("\nСтатусы для TikTok каруселей:")
    for st, count in stats.get("by_tt_status", {}).items():
        print(f"  • {st}: {count}")

    # Проверка моста
    print("\nСтатус WhatsApp моста:")
    try:
        req = urllib.request.Request(f"{WA_BRIDGE_URL}/status")
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get("connected"):
                u = data.get("user", {})
                print(f"  ✅ Подключен (Номер: {u.get('id')}, Имя: {u.get('name')})")
            else:
                print("  ⚠️ Запущен, но ожидает сканирования QR-кода.")
    except Exception:
        print(f"  ❌ Не запущен (ожидает запуска: 'cd wa_bridge && npm start')")
    print("="*50 + "\n")

def cmd_list_chats(args):
    """Запрашивает список доступных чатов и сообществ из WhatsApp моста."""
    try:
        req = urllib.request.Request(f"{WA_BRIDGE_URL}/chats")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            chats = data.get("chats", [])
            print("\n" + "="*60)
            print("ДОСТУПНЫЕ ГРУППЫ И СООБЩЕСТВА В ВАШЕМ WHATSAPP:")
            print("="*60)
            for c in chats:
                print(f"Название: {c.get('subject')}")
                print(f"Chat ID:  {c.get('id')}")
                print(f"Участников: {c.get('size')}\n")
            print("Скопируйте нужный Chat ID в файл .env для соответствующей ниши.")
    except Exception as e:
        print(f"Не удалось получить список чатов: {e}")
        print(f"Убедитесь, что мост запущен ('cd wa_bridge && npm start') и QR-код отсканирован.")

def update_env_var(key: str, value: str):
    """Обновляет или добавляет переменную в файл .env."""
    env_file = os.path.join(os.path.dirname(__file__), ".env")
    lines = []
    found = False
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}=") or line.strip() == key:
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"{key}={value}\n")

    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

def cmd_resolve_channel(args):
    """Определяет точный Chat ID канала WhatsApp по его ссылке."""
    try:
        payload = {"url": args.url}
        req = urllib.request.Request(
            f"{WA_BRIDGE_URL}/resolve-channel",
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get("success"):
                channel_id = data.get("id")
                name = data.get("name")
                print("\n" + "="*50)
                print("✅ КАНАЛ WHATSAPP УСПЕШНО НАЙДЕН!")
                print("="*50)
                print(f"Название:   {name}")
                print(f"Channel ID: {channel_id}")
                print("="*50)

                if args.save_as:
                    var_name = args.save_as.strip()
                    update_env_var(var_name, channel_id)
                    print(f"💾 ID автоматически записан в .env как: {var_name}={channel_id}\n")
                else:
                    print(f"\nСкопируйте этот ID или строку ниже в файл .env:")
                    print(f"WA_CHAT_DEFAULT={channel_id}\n")
            else:
                print(f"❌ Ошибка: {data}")
    except Exception as e:
        print(f"❌ Не удалось определить канал: {e}")
def cmd_create_channels(args):
    """Автоматически создает WhatsApp-каналы под все оставшиеся ниши и записывает их в .env."""
    import time
    default_chat = os.getenv("WA_CHAT_DEFAULT", "").strip()
    if default_chat and not os.getenv("WA_CHAT_MEN_CLOTHING", "").strip():
        update_env_var("WA_CHAT_MEN_CLOTHING", default_chat)
        print(f"✅ Мужской канал уже существует: {default_chat} (записан в WA_CHAT_MEN_CLOTHING)")

    channels_to_create = [
        {
            "niche": "gadgets",
            "env_key": "WA_CHAT_GADGETS",
            "name": "Каспи находки | Гаджеты и техника",
            "description": NICHES["gadgets"].description
        },
        {
            "niche": "kitchen",
            "env_key": "WA_CHAT_KITCHEN",
            "name": "Каспи находки | Кухня и уют",
            "description": NICHES["kitchen"].description
        },
        {
            "niche": "care",
            "env_key": "WA_CHAT_CARE",
            "name": "Каспи находки | Красота и уход",
            "description": NICHES["care"].description
        },
        {
            "niche": "auto",
            "env_key": "WA_CHAT_AUTO",
            "name": "Каспи находки | Автотовары",
            "description": NICHES["auto"].description
        },
        {
            "niche": "sport",
            "env_key": "WA_CHAT_SPORT",
            "name": "Каспи находки | Спорт и фитнес",
            "description": NICHES["sport"].description
        }
    ]

    for ch in channels_to_create:
        current_val = os.getenv(ch["env_key"], "").strip()
        if current_val:
            print(f"ℹ️ Канал '{ch['name']}' уже привязан: {current_val}")
            continue

        print(f"\nСоздаем канал: '{ch['name']}'...")
        payload = {"name": ch["name"], "description": ch["description"]}
        try:
            req = urllib.request.Request(
                f"{WA_BRIDGE_URL}/create-channel",
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if data.get("success"):
                    cid = data.get("id")
                    inv = data.get("inviteLink")
                    update_env_var(ch["env_key"], cid)
                    print(f"✅ Создан! ID: {cid}")
                    if inv:
                        print(f"🔗 Ссылка: {inv}")
                else:
                    print(f"❌ Ошибка: {data}")
        except Exception as e:
            print(f"❌ Ошибка создания канала: {e}")
        time.sleep(3)

def cmd_create_community(args):
    """Автоматически создает WhatsApp Сообщество и 6 тематических подгрупп."""
    import time
    print("\n" + "="*60)
    print("🚀 СОЗДАНИЕ WHATSAPP СООБЩЕСТВА (KASPI НАХОДКИ KZ)")
    print("="*60)

    comm_name = args.name or "Kaspi Находки KZ | Скидки и Акции"
    comm_desc = "Официальное сообщество лучших находок и скидок на Kaspi.kz.\n\nТолько проверенные товары с высоким рейтингом 4.8+.\n📩 Сотрудничество: wa.me/87064222007"

    print(f"\n1. Создаем корневое Сообщество: '{comm_name}'...")
    try:
        payload = {"name": comm_name, "description": comm_desc}
        req = urllib.request.Request(
            f"{WA_BRIDGE_URL}/create-community",
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get("success"):
                cid = data.get("id")
                inv = data.get("inviteLink")
                update_env_var("WA_COMMUNITY_ID", cid)
                print(f"✅ Сообщество создано! ID: {cid}")
                if inv:
                    print(f"🔗 Ссылка на Сообщество: {inv}")
            else:
                print(f"⚠️ Ответ создания сообщества: {data}")
    except Exception as e:
        print(f"⚠️ Ошибка вызова create-community: {e}")

    time.sleep(2)

    groups_to_create = [
        {"niche": "men_clothing", "env_key": "WA_CHAT_MEN_CLOTHING", "name": "👔 Kaspi Находки | Мужской стиль"},
        {"niche": "gadgets", "env_key": "WA_CHAT_GADGETS", "name": "⚡ Kaspi Находки | Гаджеты и техника"},
        {"niche": "kitchen", "env_key": "WA_CHAT_KITCHEN", "name": "🍳 Kaspi Находки | Кухня и уют"},
        {"niche": "care", "env_key": "WA_CHAT_CARE", "name": "🌸 Kaspi Находки | Красота и уход"},
        {"niche": "auto", "env_key": "WA_CHAT_AUTO", "name": "🚗 Kaspi Находки | Автотовары"},
        {"niche": "sport", "env_key": "WA_CHAT_SPORT", "name": "💪 Kaspi Находки | Спорт и фитнес"}
    ]

    print("\n2. Создаем 6 тематических подгрупп (режим: только админы)...")
    for grp in groups_to_create:
        n_cfg = NICHES.get(grp["niche"])
        desc = n_cfg.description if n_cfg else ""
        print(f"\nСоздаем группу: '{grp['name']}'...")
        payload = {
            "name": grp["name"],
            "description": desc,
            "announcementOnly": True
        }
        try:
            req = urllib.request.Request(
                f"{WA_BRIDGE_URL}/create-community-group",
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if data.get("success"):
                    gid = data.get("id")
                    inv = data.get("inviteLink")
                    update_env_var(grp["env_key"], gid)
                    print(f"✅ Создана! ID: {gid}")
                    if inv:
                        print(f"🔗 Ссылка: {inv}")
                else:
                    print(f"❌ Ошибка: {data}")
        except Exception as e:
            print(f"❌ Ошибка вызова create-community-group: {e}")
        time.sleep(3)

    print("\n" + "="*60)
    print("🎉 Все группы сообщества созданы и привязаны в .env!")
    print("="*60 + "\n")

def cmd_set_avatar(args):
    """Устанавливает фирменную аватарку Kaspi на выбранный канал WhatsApp."""
    chat_id = args.chat_id or os.getenv("WA_CHAT_DEFAULT", "")
    if not chat_id:
        print("Укажите --chat-id или задайте WA_CHAT_DEFAULT в .env")
        return
    image_path = os.path.abspath(args.image or os.path.join(os.path.dirname(__file__), "kaspi_avatar.png"))
    payload = {"chatId": chat_id, "imagePath": image_path}
    try:
        req = urllib.request.Request(
            f"{WA_BRIDGE_URL}/set-channel-avatar",
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get("success"):
                print(f"✅ Аватарка успешно установлена для канала {chat_id}!")
            else:
                print(f"❌ Ошибка: {data}")
    except Exception as e:
        print(f"❌ Ошибка установки аватарки: {e}")

def cmd_update_descriptions(args):
    """Обновляет описания во всех 7 WhatsApp-каналах на конверсионные."""
    script_path = os.path.join(os.path.dirname(__file__), "wa_bridge", "update_descriptions.js")
    import subprocess
    print("🚀 Запускаем обновление описаний для всех 7 каналов...")
    res = subprocess.run(["node", script_path], cwd=os.path.join(os.path.dirname(__file__), "wa_bridge"))
    if res.returncode == 0:
        print("\n✅ Все 7 описаний успешно обновлены в каналах!")
    else:
        print(f"\n❌ Ошибка обновления описаний (код {res.returncode})")

def main():
    parser = argparse.ArgumentParser(description="Kaspi to WhatsApp & Social Media Automation Pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list-niches
    subparsers.add_parser("list-niches", help="Показать список доступных ниш и настройки")

    # parse
    p_parse = subparsers.add_parser("parse", help="Спарсить товары с Kaspi по нише")
    p_parse.add_argument("--niche", required=True, help="Ключ ниши (kitchen, auto, gadgets, etc.) или 'all'")
    p_parse.add_argument("--max-price", type=int, default=None, help="Максимальная цена в ₸")
    p_parse.add_argument("--limit", type=int, default=5, help="Сколько товаров найти")

    # generate
    p_gen = subparsers.add_parser("generate", help="Сгенерировать продающие тексты")
    p_gen.add_argument("--niche", default="all", help="Ключ ниши или 'all'")
    p_gen.add_argument("--limit", type=int, default=5, help="Сколько текстов сгенерировать")

    # post-wa
    p_post = subparsers.add_parser("post-wa", help="Опубликовать в WhatsApp")
    p_post.add_argument("--niche", required=False, help="Ключ ниши")
    p_post.add_argument("--chat-id", required=False, help="Принудительный Chat ID")
    p_post.add_argument("--limit", type=int, default=1, help="Сколько постов отправить за раз")

    # export-tt
    p_tt = subparsers.add_parser("export-tt", help="Собрать пачку товаров для TikTok / Reels карусели")
    p_tt.add_argument("--niche", required=True, help="Ключ ниши")
    p_tt.add_argument("--count", type=int, default=4, help="Сколько товаров объединить в карусель (3-5)")

    # build-slides
    p_slides = subparsers.add_parser("build-slides", help="Генерировать слайды 9:16 и коллажи 4-в-1 для Google Drive")
    p_slides.add_argument("--niche", default="all", help="Ключ ниши или 'all'")
    p_slides.add_argument("--count", type=int, default=4, help="Количество товаров в слайд-пакете (3-4)")

    # pipeline
    p_pipe = subparsers.add_parser("pipeline", help="Полный автоматический цикл (Kaspi -> WhatsApp -> Google Drive)")
    p_pipe.add_argument("--niche", default="all", help="Ключ ниши или 'all'")
    p_pipe.add_argument("--limit", type=int, default=4, help="Сколько товаров обработать")
    p_pipe.add_argument("--max-price", type=int, default=None, help="Максимальная цена в ₸")
    p_pipe.add_argument("--chat-id", required=False, help="Принудительный Chat ID")

    # sync-sheets
    subparsers.add_parser("sync-sheets", help="Выгрузить все ссылки и товары в онлайн Google Таблицу")

    # status
    subparsers.add_parser("status", help="Показать статистику базы и статус подключения")

    # list-chats
    subparsers.add_parser("list-chats", help="Получить список Chat ID из WhatsApp")

    # resolve-channel
    p_res = subparsers.add_parser("resolve-channel", help="Определить Channel ID канала WhatsApp по ссылке-приглашению")
    p_res.add_argument("--url", required=True, help="Ссылка на канал WhatsApp (скопированная по кнопке 'Копировать ссылку')")
    p_res.add_argument("--save-as", required=False, default=None, help="Имя переменной в .env (например, WA_CHAT_DEFAULT или WA_CHAT_MEN_CLOTHING)")

    # create-community
    p_comm = subparsers.add_parser("create-community", help="Автоматически создать WhatsApp Сообщество и 6 тематических подгрупп")
    p_comm.add_argument("--name", required=False, default=None, help="Название сообщества")

    # create-channels
    subparsers.add_parser("create-channels", help="Автоматически создать каналы WhatsApp для всех остальных ниш")

    # set-avatar
    p_ava = subparsers.add_parser("set-avatar", help="Установить аватарку Kaspi на канал WhatsApp")
    p_ava.add_argument("--chat-id", required=False, default=None, help="ID канала WhatsApp (по умолчанию берется из .env)")
    p_ava.add_argument("--image", required=False, default=None, help="Путь к картинке (по умолчанию kaspi_avatar.png)")

    # set-descriptions
    subparsers.add_parser("set-descriptions", help="Обновить конверсионные описания во всех 6 нишах WhatsApp")
    subparsers.add_parser("update-descriptions", help="Обновить конверсионные описания во всех 6 нишах WhatsApp (синоним set-descriptions)")

    args = parser.parse_args()

    dispatch = {
        "list-niches": cmd_list_niches,
        "parse": cmd_parse,
        "generate": cmd_generate,
        "post-wa": cmd_post_wa,
        "export-tt": cmd_build_slides,
        "build-slides": cmd_build_slides,
        "pipeline": cmd_pipeline,
        "sync-sheets": cmd_sync_sheets,
        "status": cmd_status,
        "list-chats": cmd_list_chats,
        "resolve-channel": cmd_resolve_channel,
        "create-channels": cmd_create_channels,
        "create-community": cmd_create_community,
        "set-avatar": cmd_set_avatar,
        "set-descriptions": cmd_update_descriptions,
        "update-descriptions": cmd_update_descriptions
    }

    dispatch[args.command](args)

if __name__ == "__main__":
    main()
