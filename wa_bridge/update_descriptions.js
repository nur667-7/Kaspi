const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = require('@whiskeysockets/baileys');
const pino = require('pino');
const path = require('path');
const fs = require('fs');

const AUTH_DIR = path.join(__dirname, 'auth_info_baileys');

// Читаем .env для получения актуальных ID
function getEnvChannels() {
    const envPath = path.join(__dirname, '..', '.env');
    const content = fs.readFileSync(envPath, 'utf8');
    const map = {};
    for (const line of content.split('\n')) {
        const trimmed = line.trim();
        if (trimmed && !trimmed.startsWith('#') && trimmed.includes('=')) {
            const idx = trimmed.indexOf('=');
            const key = trimmed.slice(0, idx).trim();
            const val = trimmed.slice(idx + 1).trim();
            map[key] = val;
        }
    }
    return map;
}

const DESCRIPTIONS = [
    {
        name: "1. 👔 Мужская одежда",
        env_key: "WA_CHAT_MEN_CLOTHING",
        description: `Мужской гардероб — стиль, уверенность и практичность

👟 Повседневная одежда, база и готовые мужские образы
🧥 Куртки, худи, джинсы и удобная качественная обувь
⌚ Аксессуары, ремни, часы и акцентные детали стиля
🏷️ Топовые находки на Kaspi по честным ценам и с высоким рейтингом
💡 Лайфхаки по подбору размеров, уходу за вещами и посадке
🔥 Скидки, акции и проверенные проверенные продавцы

Без лишней воды — только качественные вещи, которые реально носятся.

📩 Сотрудничество: wa.me/87064222007`
    },
    {
        name: "2. ⚡ Гаджеты и аксессуары",
        env_key: "WA_CHAT_GADGETS",
        description: `Гаджеты и технологии — умные девайсы для жизни и работы

📱 Топовые аксессуары для смартфонов, планшетов и ноутбуков
🎧 Беспроводные наушники, портативные колонки и чистый звук
🔋 Мощные павербанки, сверхбыстрые зарядки и надежные кабели
⌚ Смарт-часы, фитнес-браслеты, поисковые метки и трекеры
💡 Умные девайсы для дома, рабочего стола и авто
🔥 Проверенные находки на Kaspi с рейтингом 4.8+ до 12 000 ₸

Без лишней воды — только техника, которая упрощает каждый день.

📩 Сотрудничество: wa.me/87064222007`
    },
    {
        name: "3. 🍳 Товары для кухни и дома",
        env_key: "WA_CHAT_KITCHEN",
        description: `Кухня и уют — эстетика, порядок и кулинарное вдохновение

🥢 Умные кухонные гаджеты, измельчители и полезные лайфхаки
🍽️ Красивая посуда, сервировка и стильные аксессуары
📦 Идеальное хранение продуктов, контейнеры и организация пространства
☕ Полезные мелочи, экономящие время и силы при готовке
✨ Текстиль, декор и уютные детали для кухни вашей мечты
🏷️ Находки на Kaspi дешевле 8 000 ₸ с реальными отзывами 4.8+

Без лишней воды — только то, что делает дом по-настоящему уютным.

📩 Сотрудничество: wa.me/87064222007`
    },
    {
        name: "4. 🌸 Товары для ухода и красоты",
        env_key: "WA_CHAT_CARE",
        description: `Красота и уход — сияющая кожа, здоровые волосы и забота о себе

✨ Проверенный уход за лицом: сыворотки, кремы, SPF и очищение
💆♀️ Средства для густоты, блеска и салонного ухода за волосами
🧴 Уход за телом, скрабы, масла и домашний SPA-релакс
🔍 Честные разборы составов, топ-рейтинги и средства без переплат
🌸 Наборы для ухода, подарки и бьюти-лайфхаки на каждый день
🛍️ Топовая косметика с Kaspi с рейтингом 4.8+ и сотнями отзывов

Без лишней воды — только средства с доказанным результатом.

📩 Сотрудничество: wa.me/87064222007`
    },
    {
        name: "5. 🚗 Автотовары и гараж",
        env_key: "WA_CHAT_AUTO",
        description: `Автотовары — комфорт, чистота и надежность вашего авто

🧼 Автохимия, уход за кузовом и качественная химчистка салона
📱 Надежные держатели, органайзеры, накидки и уют в поездках
🔧 Инструменты, компрессоры, аварийные наборы и безопасность
💡 Полезные лайфхаки для водителей, защита салона и уход за стеклами
🚗 Мелочи для тюнинга, ароматизаторы и аксессуары в авто
🏷️ Проверенные автонаходки на Kaspi по самым выгодным ценам

Без лишней воды — только то, что реально пригодится на дороге.

📩 Сотрудничество: wa.me/87064222007`
    },
    {
        name: "6. 💪 Спорт и фитнес",
        env_key: "WA_CHAT_SPORT",
        description: `Спорт и фитнес — форма, выносливость и заряд энергии

🏋️ Инвентарь для домашних тренировок: резинки, гантели, упоры
🎽 Удобная спортивная одежда, шейкеры, бутылки и экипировка
🏃♂️ Кардио, товары для бега, массажеры и восстановление мышц
🧘♀️ Коврики для йоги, растяжка и товары для здоровья спины
💡 Лайфхаки по домашним тренировкам, режиму и мотивации
🔥 Лучшие спортивные находки на Kaspi до 10 000 ₸ с топ-рейтингом

Без лишней воды — только то, что помогает строить сильное тело.

📩 Сотрудничество: wa.me/87064222007`
    }
];

async function run() {
    const envVars = getEnvChannels();
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    const { version } = await fetchLatestBaileysVersion().catch(() => ({ version: [2, 3000, 1015901307] }));

    console.log("Подключение к WhatsApp...");
    const sock = makeWASocket({
        version,
        logger: pino({ level: 'silent' }),
        printQRInTerminal: false,
        auth: state,
        browser: ['Kaspi Poster Bot', 'Chrome', '1.0.0']
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            console.error("❌ Требуется сканирование QR-кода! Сессия не авторизована.");
            process.exit(1);
        }

        if (connection === 'close') {
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            console.log(`[WhatsApp] Соединение закрыто (код: ${statusCode})`);
        } else if (connection === 'open') {
            console.log("✅ Успешно подключено к WhatsApp!");
            console.log("Начинаем обновление описаний для всех 7 каналов...\n");

            let successCount = 0;
            let failCount = 0;

            for (const item of DESCRIPTIONS) {
                const jid = envVars[item.env_key];
                if (!jid) {
                    console.warn(`⚠️ Пропуск: не найден ${item.env_key} в .env`);
                    continue;
                }

                console.log(`⏳ Обновляем ${item.name} (${jid})...`);
                try {
                    const res = await sock.newsletterUpdateDescription(jid, item.description);
                    console.log(`✅ ${item.name}: описание успешно обновлено!`);
                    successCount++;
                } catch (err) {
                    console.error(`❌ Ошибка обновления ${item.name}:`, err.message || err);
                    failCount++;
                }
                // Небольшая пауза между запросами к GraphQL
                await new Promise(r => setTimeout(r, 1500));
            }

            console.log(`\nИтог: успешно ${successCount}, ошибок ${failCount}`);
            // Даем время на запись сессии и завершаем
            setTimeout(() => {
                process.exit(failCount === 0 ? 0 : 1);
            }, 2000);
        }
    });
}

run().catch(err => {
    console.error("Фатальная ошибка:", err);
    process.exit(1);
});
