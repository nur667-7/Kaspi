import sqlite3
import json
import os
from typing import List, Dict, Optional, Any

DB_PATH = os.path.join(os.path.dirname(__file__), "kaspi_media.db")

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Инициализация таблиц базы данных."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Таблица продуктов
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            kaspi_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            brand TEXT,
            niche TEXT NOT NULL,
            price INTEGER NOT NULL,
            price_before_discount INTEGER,
            rating REAL,
            reviews_quantity INTEGER,
            shop_link TEXT NOT NULL,
            preview_images TEXT,  -- JSON list of URLs
            features TEXT,        -- JSON list or dict of features
            seller_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Таблица публикаций для WhatsApp и соцсетей
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kaspi_id TEXT NOT NULL,
            niche TEXT NOT NULL,
            wa_caption TEXT,
            wa_status TEXT DEFAULT 'pending', -- pending, posted, failed, skipped
            wa_chat_id TEXT,
            wa_message_id TEXT,
            wa_posted_at TIMESTAMP,
            tt_status TEXT DEFAULT 'new',      -- new, batched, posted, skipped
            tt_batch_id TEXT,
            ig_status TEXT DEFAULT 'new',      -- new, posted, skipped
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (kaspi_id) REFERENCES products(kaspi_id)
        )
        """)

        # Таблица пакетов каруселей для TikTok/Instagram
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS carousel_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_code TEXT UNIQUE,
            niche TEXT NOT NULL,
            product_ids TEXT, -- JSON list
            hook_text TEXT,
            export_dir TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Таблица кастомных настроек ниш (диапазон цен, рейтинг, направление поиска)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS niche_settings (
            niche TEXT PRIMARY KEY,
            min_price INTEGER DEFAULT 0,
            max_price INTEGER,
            min_rating REAL DEFAULT 4.7,
            min_reviews INTEGER DEFAULT 15,
            custom_focus TEXT,
            is_active INTEGER DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Индексы для быстрого поиска
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_niche ON products(niche)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_wa_status ON posts(wa_status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_tt_status ON posts(tt_status)")
        conn.commit()

def get_niche_settings(niche: str) -> Dict[str, Any]:
    """Возвращает настройки фильтрации и подниши для указанной ниши."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM niche_settings WHERE niche = ?", (niche,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return {
            "niche": niche,
            "min_price": 0,
            "max_price": None,
            "min_rating": 4.7,
            "min_reviews": 15,
            "custom_focus": "",
            "is_active": 1
        }

def save_niche_settings(niche: str, **kwargs):
    """Обновляет или создает настройки ниши в базе."""
    current = get_niche_settings(niche)
    current.update({k: v for k, v in kwargs.items() if v is not None})
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO niche_settings (niche, min_price, max_price, min_rating, min_reviews, custom_focus, is_active, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(niche) DO UPDATE SET
            min_price = excluded.min_price,
            max_price = excluded.max_price,
            min_rating = excluded.min_rating,
            min_reviews = excluded.min_reviews,
            custom_focus = excluded.custom_focus,
            is_active = excluded.is_active,
            updated_at = CURRENT_TIMESTAMP
        """, (
            niche,
            int(current.get("min_price") or 0),
            int(current["max_price"]) if current.get("max_price") is not None else None,
            float(current.get("min_rating") or 4.7),
            int(current.get("min_reviews") or 15),
            current.get("custom_focus") or "",
            int(current.get("is_active", 1))
        ))
        conn.commit()

def get_post_by_id(post_id: int) -> Optional[Dict[str, Any]]:
    """Возвращает пост со всеми данными товара по его ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT p.*, pr.title, pr.brand, pr.price, pr.price_before_discount, 
               pr.rating, pr.reviews_quantity, pr.shop_link, pr.preview_images, 
               pr.features, pr.seller_name
        FROM posts p
        JOIN products pr ON p.kaspi_id = pr.kaspi_id
        WHERE p.id = ?
        """, (post_id,))
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["images"] = json.loads(d["preview_images"]) if d.get("preview_images") else []
        d["features_parsed"] = json.loads(d["features"]) if d.get("features") else []
        return d

def product_exists(kaspi_id: str) -> bool:
    """Проверяет наличие товара в базе."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM products WHERE kaspi_id = ?", (str(kaspi_id),))
        return cursor.fetchone() is not None

def save_product(prod: Dict[str, Any]) -> bool:
    """Сохраняет товар и создает черновик поста. Возвращает True, если добавлен новый."""
    kaspi_id = str(prod["kaspi_id"])
    if product_exists(kaspi_id):
        return False

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO products (
            kaspi_id, title, brand, niche, price, price_before_discount,
            rating, reviews_quantity, shop_link, preview_images, features, seller_name
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            kaspi_id,
            prod.get("title", ""),
            prod.get("brand", ""),
            prod.get("niche", "general"),
            int(prod.get("price", 0)),
            int(prod.get("price_before_discount", 0)) if prod.get("price_before_discount") else None,
            float(prod.get("rating", 0.0)),
            int(prod.get("reviews_quantity", 0)),
            prod.get("shop_link", ""),
            json.dumps(prod.get("images", []), ensure_ascii=False),
            json.dumps(prod.get("features", []), ensure_ascii=False),
            prod.get("seller_name", "")
        ))

        cursor.execute("""
        INSERT INTO posts (kaspi_id, niche, wa_status, tt_status, ig_status)
        VALUES (?, ?, 'pending', 'new', 'new')
        """, (kaspi_id, prod.get("niche", "general")))

        conn.commit()
        return True

def get_pending_wa_posts(niche: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
    """Возвращает список товаров, готовых к публикации в WhatsApp."""
    with get_connection() as conn:
        cursor = conn.cursor()
        query = """
        SELECT p.*, pr.title, pr.brand, pr.price, pr.price_before_discount, 
               pr.rating, pr.reviews_quantity, pr.shop_link, pr.preview_images, 
               pr.features, pr.seller_name
        FROM posts p
        JOIN products pr ON p.kaspi_id = pr.kaspi_id
        WHERE p.wa_status = 'pending'
        """
        params = []
        if niche:
            query += " AND p.niche = ?"
            params.append(niche)
        
        query += " ORDER BY pr.rating DESC, pr.reviews_quantity DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["images"] = json.loads(d["preview_images"]) if d.get("preview_images") else []
            d["features_parsed"] = json.loads(d["features"]) if d.get("features") else []
            result.append(d)
        return result

def update_post_caption(post_id: int, caption: str):
    """Сохраняет сгенерированный текст для поста."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE posts SET wa_caption = ? WHERE id = ?", (caption, post_id))
        conn.commit()

def mark_post_published_wa(post_id: int, chat_id: str, message_id: str):
    """Помечает пост как опубликованный в WhatsApp."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE posts 
        SET wa_status = 'posted', wa_chat_id = ?, wa_message_id = ?, wa_posted_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (chat_id, message_id, post_id))
        conn.commit()

def mark_post_failed_wa(post_id: int, error_text: str = ""):
    """Помечает ошибку публикации в WhatsApp."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE posts SET wa_status = 'failed' WHERE id = ?", (post_id,))
        conn.commit()

def get_candidates_for_social_carousel(niche: str, count: int = 4, only_wa_posted: bool = False) -> List[Dict[str, Any]]:
    """Выбирает товары для TikTok-карусели (по умолчанию свежие с высоким рейтингом)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        query = """
        SELECT p.id as post_id, pr.*, p.wa_caption
        FROM posts p
        JOIN products pr ON p.kaspi_id = pr.kaspi_id
        WHERE p.niche = ? AND p.tt_status = 'new'
        """
        params = [niche]
        if only_wa_posted:
            query += " AND p.wa_status = 'posted'"
        
        query += " ORDER BY pr.rating DESC, pr.reviews_quantity DESC LIMIT ?"
        params.append(count)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["images"] = json.loads(d["preview_images"]) if d.get("preview_images") else []
            d["features_parsed"] = json.loads(d["features"]) if d.get("features") else []
            result.append(d)
        return result

def record_carousel_batch(batch_code: str, niche: str, product_ids: List[str], hook_text: str, export_dir: str):
    """Записывает пачку карусели и обновляет tt_status товаров."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO carousel_batches (batch_code, niche, product_ids, hook_text, export_dir)
        VALUES (?, ?, ?, ?, ?)
        """, (batch_code, niche, json.dumps(product_ids), hook_text, export_dir))

        for pid in product_ids:
            cursor.execute("""
            UPDATE posts SET tt_status = 'batched', tt_batch_id = ? 
            WHERE kaspi_id = ?
            """, (batch_code, pid))
        conn.commit()

def get_db_stats() -> Dict[str, Any]:
    """Возвращает сводную статистику по базе."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM products")
        total_products = cursor.fetchone()[0]

        cursor.execute("SELECT niche, COUNT(*) FROM products GROUP BY niche")
        by_niche = dict(cursor.fetchall())

        cursor.execute("SELECT wa_status, COUNT(*) FROM posts GROUP BY wa_status")
        by_wa_status = dict(cursor.fetchall())

        cursor.execute("SELECT tt_status, COUNT(*) FROM posts GROUP BY tt_status")
        by_tt_status = dict(cursor.fetchall())

        return {
            "total_products": total_products,
            "by_niche": by_niche,
            "by_wa_status": by_wa_status,
            "by_tt_status": by_tt_status
        }

def get_analytics_summary() -> Dict[str, Any]:
    """Возвращает детальную аналитику по товарам, публикации и буферу очереди."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Общие цифры
        cursor.execute("SELECT COUNT(*) FROM products")
        total_products = cursor.fetchone()[0]

        # Опубликовано сегодня
        cursor.execute("""
            SELECT COUNT(*) FROM posts 
            WHERE wa_status = 'posted' 
              AND DATE(wa_posted_at) = DATE('now')
        """)
        posted_today = cursor.fetchone()[0]

        # Всего опубликовано в WhatsApp
        cursor.execute("SELECT COUNT(*) FROM posts WHERE wa_status = 'posted'")
        total_posted = cursor.fetchone()[0]

        # Очередь (pending)
        cursor.execute("SELECT COUNT(*) FROM posts WHERE wa_status = 'pending'")
        total_pending = cursor.fetchone()[0]

        # Средний чек и средний рейтинг товаров
        cursor.execute("SELECT AVG(price), AVG(rating), MAX(price), MIN(price) FROM products")
        row = cursor.fetchone()
        avg_price = round(row[0] or 0)
        avg_rating = round(row[1] or 0.0, 2)
        max_price = row[2] or 0
        min_price = row[3] or 0

        # Статистика по нишам: сколько в очереди (pending) и сколько уже опубликовано
        cursor.execute("""
            SELECT 
                p.niche,
                COUNT(*) as total_niche,
                SUM(CASE WHEN po.wa_status = 'pending' THEN 1 ELSE 0 END) as pending_cnt,
                SUM(CASE WHEN po.wa_status = 'posted' THEN 1 ELSE 0 END) as posted_cnt,
                ROUND(AVG(p.price)) as avg_niche_price
            FROM products p
            LEFT JOIN posts po ON p.kaspi_id = po.kaspi_id
            GROUP BY p.niche
        """)
        niche_stats = {}
        for r in cursor.fetchall():
            niche_stats[r[0]] = {
                "total": r[1],
                "pending": r[2] or 0,
                "posted": r[3] or 0,
                "avg_price": r[4] or 0
            }

        return {
            "total_products": total_products,
            "posted_today": posted_today,
            "total_posted": total_posted,
            "total_pending": total_pending,
            "avg_price": avg_price,
            "avg_rating": avg_rating,
            "min_price": min_price,
            "max_price": max_price,
            "niches": niche_stats
        }

def get_all_products() -> List[Dict[str, Any]]:
    """Возвращает все товары из базы."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products ORDER BY created_at ASC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

# Автоматическая инициализация при импорте
init_db()
