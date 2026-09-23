# 📖 Инструкция по получению данных из Google Таблицы (GET API)

Данный документ описывает протокол взаимодействия любого внешнего бота (Telegram, WhatsApp, Web, Cron) с базой товаров Kaspi через Google Таблицу.

---

## 1. Базовый URL (Endpoint)
```http
https://script.google.com/macros/s/AKfycbygYwiIYd6oOe_OihdE6inCzHS3a4RTZpUVOVtoVHuINUA8bpohyAjcfmEFxuY7YQmd/exec
```

---

## 2. Метод и Параметры (GET Query Params)

| Параметр | Тип | Описание | Пример |
| :--- | :--- | :--- | :--- |
| `status` *(опц.)* | `string` | Фильтр по статусу строки в таблице | `status=new` |
| `niche` *(опц.)* | `string` | Название ниши (нужно кодировать пробелы как `%20`) | `niche=Товары%20для%20кухни` |

### Примеры URL:
- Получить только новые товары:
  ```http
  https://script.google.com/macros/s/AKfycbygYwiIYd6oOe_OihdE6inCzHS3a4RTZpUVOVtoVHuINUA8bpohyAjcfmEFxuY7YQmd/exec?status=new
  ```
- Получить товары конкретной ниши:
  ```http
  https://script.google.com/macros/s/AKfycbygYwiIYd6oOe_OihdE6inCzHS3a4RTZpUVOVtoVHuINUA8bpohyAjcfmEFxuY7YQmd/exec?status=new&niche=Гаджеты%20и%20аксессуары
  ```

---

## 3. Формат ответа сервера (JSON Response)
Сервер отдает статус `200 OK` (после стандартного для Google Apps Script редиректа 302):

```json
{
  "count": 107,
  "items": [
    {
      "kaspi_id": "139884771",
      "niche": "Товары для тренировок и спорта",
      "date": "2026-09-22T19:00:00.000Z",
      "title": "Лента, фитнес-резинка SND-GO CAMCH-24585 5 шт 18 кг",
      "price": 2990,
      "rating": 4.9,
      "reviews": 66,
      "link": "https://kaspi.kz/shop/p/lenta-fitnes-rezinka-snd-go-camch-24585-5-sht-18-kg-139884771/?c=750000000",
      "status": "new"
    }
  ]
}
```

### Структура каждого объекта:
- `kaspi_id` (`string`): Уникальный ID товара на Kaspi.
- `niche` (`string`): Название тематической категории.
- `title` (`string`): Полное название товара.
- `price` (`number`): Актуальная цена в тенге (₸).
- `rating` (`number`): Рейтинг покупателей (от 1.0 до 5.0).
- `reviews` (`number`): Количество реальных отзывов.
- `link` (`string`): Прямая кликабельная ссылка на товар в магазине Kaspi.
- `status` (`string`): Текущий статус (`new`, `posted` и др.).
- `date` (`string`): Дата добавления.

---

## 4. Готовые примеры кода

### 🐍 Python (Стандартная библиотека без зависимостей)
```python
import urllib.request
import json

URL = "https://script.google.com/macros/s/AKfycbygYwiIYd6oOe_OihdE6inCzHS3a4RTZpUVOVtoVHuINUA8bpohyAjcfmEFxuY7YQmd/exec?status=new"

req = urllib.request.Request(URL, headers={"User-Agent": "Bot/1.0"})
with urllib.request.urlopen(req, timeout=15) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    items = data.get("items", [])
    print(f"Найдено {len(items)} товаров")
```

### ⚡ JavaScript / Node.js
```javascript
const URL = "https://script.google.com/macros/s/AKfycbygYwiIYd6oOe_OihdE6inCzHS3a4RTZpUVOVtoVHuINUA8bpohyAjcfmEFxuY7YQmd/exec?status=new";

async function getProducts() {
    const response = await fetch(URL, { redirect: "follow" });
    const data = await response.json();
    console.log(`Получено товаров: ${data.count}`);
    return data.items;
}

getProducts().then(items => console.log(items[0]));
```

### 💻 cURL
```bash
curl -L -X GET "https://script.google.com/macros/s/AKfycbygYwiIYd6oOe_OihdE6inCzHS3a4RTZpUVOVtoVHuINUA8bpohyAjcfmEFxuY7YQmd/exec?status=new"
```
*(Флаг `-L` обязателен для автоматического перехода по редиректу Google).*
