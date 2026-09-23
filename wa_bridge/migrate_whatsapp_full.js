const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = require('@whiskeysockets/baileys');
const pino = require('pino');
const path = require('path');
const fs = require('fs');

const AUTH_DIR = path.join(__dirname, 'auth_info_baileys');
const AVATAR_PATH = path.join(__dirname, '..', 'kaspi_avatar.png');
const ENV_PATH = path.join(__dirname, '..', '.env');

// Старые каналы на удаление
const OLD_CHANNELS = [
    { name: "Мужская одежда (old)", jid: "120363430185108642@newsletter" },
    { name: "Женская одежда (old)", jid: "120363430715267986@newsletter" },
    { name: "Гаджеты (old)", jid: "120363429023799447@newsletter" },
    { name: "Кухня (old)", jid: "120363410736563686@newsletter" },
    { name: "Красота и уход (old)", jid: "120363428844422821@newsletter" },
    { name: "Автотовары (old)", jid: "120363414275221327@newsletter" },
    { name: "Спорт (old)", jid: "120363430021919561@newsletter" }
];

// 6 ниш сообществ для создания
const NICHES = [
    {
        slug: "men_clothing",
        env_key: "WA_CHAT_MEN_CLOTHING",
        name: "👔 Kaspi Находки | Мужской стиль",
        description: `Мужской гардероб — стиль, уверенность и практичность\n\n👟 Повседневная одежда, база и готовые мужские образы\n🧥 Куртки, худи, джинсы и удобная качественная обувь\n⌚ Аксессуары, ремни, часы и акцентные детали стиля\n🏷️ Топовые находки на Kaspi по честным ценам и с высоким рейтингом\n💡 Лайфхаки по подбору размеров, уходу за вещами и посадке\n🔥 Скидки, акции и проверенные продавцы\n\nБез лишней воды — только качественные вещи, которые реально носятся.\n\n📩 Сотрудничество: wa.me/87064222007`
    },
    {
        slug: "gadgets",
        env_key: "WA_CHAT_GADGETS",
        name: "⚡ Kaspi Находки | Гаджеты и техника",
        description: `Гаджеты и технологии — умные девайсы для жизни и работы\n\n📱 Топовые аксессуары для смартфонов, планшетов и ноутбуков\n🎧 Беспроводные наушники, портативные колонки и чистый звук\n🔋 Мощные павербанки, сверхбыстрые зарядки и надежные кабели\n⌚ Смарт-часы, фитнес-браслеты, поисковые метки и трекеры\n💡 Умные девайсы для дома, рабочего стола и авто\n🔥 Проверенные находки на Kaspi с рейтингом 4.8+ до 12 000 ₸\n\nБез лишней воды — только техника, которая упрощает каждый день.\n\n📩 Сотрудничество: wa.me/87064222007`
    },
    {
        slug: "kitchen",
        env_key: "WA_CHAT_KITCHEN",
        name: "🍳 Kaspi Находки | Кухня и уют",
        description: `Кухня и уют — эстетика, порядок и кулинарное вдохновение\n\n🥢 Умные кухонные гаджеты, измельчители и полезные лайфхаки\n🍽️ Красивая посуда, сервировка и стильные аксессуары\n📦 Идеальное хранение продуктов, контейнеры и организация пространства\n☕ Полезные мелочи, экономящие время и силы при готовке\n✨ Текстиль, декор и уютные детали для кухни вашей мечты\n🏷️ Находки на Kaspi дешевле 8 000 ₸ с реальными отзывами 4.8+\n\nБез лишней воды — только то, что делает дом по-настоящему уютным.\n\n📩 Сотрудничество: wa.me/87064222007`
    },
    {
        slug: "care",
        env_key: "WA_CHAT_CARE",
        name: "🌸 Kaspi Находки | Красота и уход",
        description: `Красота и уход — сияющая кожа, здоровые волосы и забота о себе\n\n✨ Проверенный уход за лицом: сыворотки, кремы, SPF и очищение\n💆‍♀️ Средства для густоты, блеска и салонного ухода за волосами\n🧴 Уход за телом, скрабы, масла и домашний SPA-релакс\n🔍 Честные разборы составов, топ-рейтинги и средства без переплат\n🌸 Наборы для ухода, подарки и бьюти-лайфхаки на каждый день\n🛍️ Топовая косметика с Kaspi с рейтингом 4.8+ и сотнями отзывов\n\nБез лишней воды — только средства с доказанным результатом.\n\n📩 Сотрудничество: wa.me/87064222007`
    },
    {
        slug: "auto",
        env_key: "WA_CHAT_AUTO",
        name: "🚗 Kaspi Находки | Автотовары и гараж",
        description: `Автотовары — комфорт, чистота и надежность вашего авто\n\n🧼 Автохимия, уход за кузовом и качественная химчистка салона\n📱 Надежные держатели, органайзеры, накидки и уют в поездках\n🔧 Инструменты, компрессоры, аварийные наборы и безопасность\n💡 Полезные лайфхаки для водителей, защита салона и уход за стеклами\n🚗 Мелочи для тюнинга, ароматизаторы и аксессуары в авто\n🏷️ Проверенные автонаходки на Kaspi по самым выгодным ценам\n\nБез лишней воды — только то, что реально пригодится на дороге.\n\n📩 Сотрудничество: wa.me/87064222007`
    },
    {
        slug: "sport",
        env_key: "WA_CHAT_SPORT",
        name: "💪 Kaspi Находки | Спорт и фитнес",
        description: `Спорт и фитнес — форма, выносливость и заряд энергии\n\n🏋️ Инвентарь для домашних тренировок: резинки, гантели, упоры\n🎽 Удобная спортивная одежда, шейкеры, бутылки и экипировка\n🏃‍♂️ Кардио, товары для бега, массажеры и восстановление мышц\n🧘‍♀️ Коврики для йоги, растяжка и товары для здоровья спины\n💡 Лайфхаки по домашним тренировкам, режиму и мотивации\n🔥 Лучшие спортивные находки на Kaspi до 10 000 ₸ с топ-рейтингом\n\nБез лишней воды — только то, что помогает строить сильное тело.\n\n📩 Сотрудничество: wa.me/87064222007`
    }
];

function updateEnv(newVars) {
    if (!fs.existsSync(ENV_PATH)) return;
    let content = fs.readFileSync(ENV_PATH, 'utf8');
    let lines = content.split('\n');

    for (const [key, val] of Object.entries(newVars)) {
        let found = false;
        lines = lines.map(line => {
            if (line.trim().startsWith(`${key}=`) || line.trim() === key) {
                found = true;
                return `${key}=${val}`;
            }
            return line;
        });
        if (!found) {
            lines.push(`${key}=${val}`);
        }
    }
    fs.writeFileSync(ENV_PATH, lines.join('\n'), 'utf8');
}

async function runMigration() {
    console.log("=" .repeat(60));
    console.log("🚀 МИГРАЦИЯ WHATSAPP: УДАЛЕНИЕ КАНАЛОВ И СОЗДАНИЕ СООБЩЕСТВ");
    console.log("=" .repeat(60) + "\n");

    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    const { version } = await fetchLatestBaileysVersion().catch(() => ({ version: [2, 3000, 1015901307] }));

    const sock = makeWASocket({
        version,
        logger: pino({ level: 'silent' }),
        printQRInTerminal: false,
        auth: state,
        browser: ['Kaspi Migration Bot', 'Chrome', '1.0.0']
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect } = update;

        if (connection === 'close') {
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            console.log(`[WhatsApp] Соединение закрыто (код: ${statusCode})`);
            if (statusCode === DisconnectReason.loggedOut) {
                console.error("❌ Сессия не авторизована! Запустите 'npm start' для сканирования QR.");
                process.exit(1);
            }
        } else if (connection === 'open') {
            console.log(`✅ WhatsApp успешно подключен как ${sock.user?.id?.split(':')[0]} (${sock.user?.name || 'Админ'})\n`);

            // --- ШАГ 1: УДАЛЕНИЕ СТАРЫХ КАНАЛОВ ---
            console.log("--- 1. Удаление старых каналов (@newsletter) ---");
            for (const ch of OLD_CHANNELS) {
                try {
                    console.log(`⏳ Удаляем канал: ${ch.name} (${ch.jid})...`);
                    await sock.newsletterDelete(ch.jid);
                    console.log(`  ✅ Канал удален: ${ch.name}`);
                } catch (err) {
                    console.warn(`  ⚠️ Не удалось удалить ${ch.name}: ${err.message || err}`);
                }
                await new Promise(r => setTimeout(r, 1200));
            }

            // --- ШАГ 2: СОЗДАНИЕ СООБЩЕСТВ / ГРУПП ДЛЯ 6 НИШ ---
            console.log("\n--- 2. Создание Сообществ / Групп под каждую нишу ---");
            const newEnvVars = {};
            const createdResults = [];
            const avatarBuffer = fs.existsSync(AVATAR_PATH) ? fs.readFileSync(AVATAR_PATH) : null;

            for (const n of NICHES) {
                console.log(`\n⏳ Создаем сообщество/группу для ниши: ${n.name}...`);
                let targetId = null;
                let inviteLink = null;

                // Пробуем создать как WhatsApp Community
                try {
                    const comm = await sock.communityCreate(n.name, n.description);
                    if (comm && comm.id) {
                        targetId = comm.id;
                        console.log(`  ✅ Сообщество создано! ID: ${targetId}`);
                        try {
                            const code = await sock.communityInviteCode(targetId);
                            if (code) inviteLink = `https://chat.whatsapp.com/${code}`;
                        } catch (_) {}
                    }
                } catch (commErr) {
                    console.log(`  ℹ️ communityCreate не сработал (${commErr.message}), создаем как группу с режимом объявлений...`);
                    try {
                        const grp = await sock.groupCreate(n.name, []);
                        targetId = grp.id;
                        console.log(`  ✅ Группа создана! ID: ${targetId}`);
                        // Ставим только админам
                        await sock.groupSettingUpdate(targetId, 'announcement').catch(() => {});
                        await sock.groupUpdateDescription(targetId, n.description).catch(() => {});
                        const code = await sock.groupInviteCode(targetId).catch(() => null);
                        if (code) inviteLink = `https://chat.whatsapp.com/${code}`;
                    } catch (grpErr) {
                        console.error(`  ❌ Ошибка создания группы: ${grpErr.message}`);
                    }
                }

                if (targetId) {
                    newEnvVars[n.env_key] = targetId;

                    // Установка аватарки
                    if (avatarBuffer) {
                        try {
                            console.log(`  🖼️ Устанавливаем аватарку Kaspi для ${n.name}...`);
                            await sock.updateProfilePicture(targetId, avatarBuffer);
                            console.log(`  ✅ Аватарка успешно установлена!`);
                        } catch (avaErr) {
                            console.warn(`  ⚠️ Не удалось установить аватарку: ${avaErr.message}`);
                        }
                    }

                    createdResults.push({
                        name: n.name,
                        id: targetId,
                        link: inviteLink || "ссылка формируется в приложении"
                    });
                }
                await new Promise(r => setTimeout(r, 2000));
            }

            // Назначаем первый чат чатом по умолчанию
            if (createdResults.length > 0) {
                newEnvVars["WA_CHAT_DEFAULT"] = createdResults[0].id;
                newEnvVars["WA_COMMUNITY_ANNOUNCEMENT"] = createdResults[0].id;
            }

            // Обновляем .env
            console.log("\n--- 3. Обновление .env файла ---");
            updateEnv(newEnvVars);
            console.log("✅ .env успешно обновлен с новыми ID групп!");

            console.log("\n" + "=" .repeat(60));
            console.log("🎉 МИГРАЦИЯ УСПЕШНО ЗАВЕРШЕНА!");
            console.log("=" .repeat(60));
            console.log("\nСозданные сообщества:");
            for (const res of createdResults) {
                console.log(`• ${res.name}`);
                console.log(`  ID: ${res.id}`);
                console.log(`  Инвайт: ${res.link}\n`);
            }

            setTimeout(() => process.exit(0), 2000);
        }
    });
}

runMigration().catch(err => {
    console.error("Фатальная ошибка миграции:", err);
    process.exit(1);
});
