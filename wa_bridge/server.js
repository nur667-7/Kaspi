const express = require('express');
const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = require('@whiskeysockets/baileys');
const pino = require('pino');
const qrcode = require('qrcode-terminal');
const path = require('path');
const fs = require('fs');

const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3000;
const AUTH_DIR = path.join(__dirname, 'auth_info_baileys');

let sock = null;
let isConnected = false;
let userInfo = null;
let cachedGroups = [];

async function connectToWhatsApp() {
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    const { version } = await fetchLatestBaileysVersion().catch(() => ({ version: [2, 3000, 1015901307] }));

    sock = makeWASocket({
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
            console.log('\n' + '='.repeat(50));
            console.log('📌 ОТСКАНИРУЙТЕ ЭТОТ QR-КОД В WHATSAPP НА ТЕЛЕФОНЕ:');
            console.log('(WhatsApp -> Связанные устройства -> Привязка устройства)');
            console.log('='.repeat(50) + '\n');
            qrcode.generate(qr, { small: true });
        }

        if (connection === 'close') {
            isConnected = false;
            userInfo = null;
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
            console.log(`[WhatsApp] Соединение закрыто (код: ${statusCode}). Переподключение: ${shouldReconnect}`);
            if (shouldReconnect) {
                setTimeout(connectToWhatsApp, 3000);
            } else {
                console.log('[WhatsApp] Сессия сброшена. Удалите auth_info_baileys для новой авторизации.');
            }
        } else if (connection === 'open') {
            isConnected = true;
            userInfo = sock.user;
            console.log('\n' + '='.repeat(50));
            console.log(`✅ WHATSAPP УСПЕШНО ПОДКЛЮЧЕН!`);
            console.log(`Номер: ${userInfo.id.split(':')[0]}`);
            console.log(`Имя: ${userInfo.name || 'Пользователь'}`);
            console.log('='.repeat(50) + '\n');

            // Загружаем список групп/сообществ
            try {
                const groups = await sock.groupFetchAllParticipating();
                cachedGroups = Object.values(groups).map(g => ({
                    id: g.id,
                    subject: g.subject,
                    size: g.participants?.length || 0,
                    isCommunity: g.isCommunity || false,
                    isAnnouncement: g.announce || false
                }));
                console.log(`[WhatsApp] Загружено доступных групп/сообществ: ${cachedGroups.length}`);
            } catch (err) {
                console.warn('[WhatsApp] Не удалось загрузить список групп:', err.message);
            }
        }
    });

    // Обновление списка групп при изменениях
    sock.ev.on('groups.update', async () => {
        try {
            const groups = await sock.groupFetchAllParticipating();
            cachedGroups = Object.values(groups).map(g => ({
                id: g.id,
                subject: g.subject,
                size: g.participants?.length || 0
            }));
        } catch (_) {}
    });
}

// Эндпоинт статуса подключения
app.get('/status', (req, res) => {
    res.json({
        connected: isConnected,
        user: userInfo ? { id: userInfo.id.split(':')[0], name: userInfo.name } : null
    });
});

// Эндпоинт списка доступных чатов и сообществ
app.get('/chats', async (req, res) => {
    if (!isConnected) {
        return res.status(503).json({ error: 'WhatsApp не подключен. Отсканируйте QR-код.' });
    }
    try {
        if (!cachedGroups.length) {
            const groups = await sock.groupFetchAllParticipating();
            cachedGroups = Object.values(groups).map(g => ({
                id: g.id,
                subject: g.subject,
                size: g.participants?.length || 0
            }));
        }
        res.json({ chats: cachedGroups });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// Эндпоинт получения ID канала по ссылке-приглашению или коду
app.post('/resolve-channel', async (req, res) => {
    if (!isConnected || !sock) {
        return res.status(503).json({ error: 'WhatsApp не подключен. Отсканируйте QR-код.' });
    }

    let { url, code } = req.body;
    if (url) {
        const match = url.match(/whatsapp\.com\/channel\/([a-zA-Z0-9_-]+)/);
        if (match) {
            code = match[1];
        } else {
            code = url.trim();
        }
    }

    if (!code) {
        return res.status(400).json({ error: 'Укажите ссылку на канал или invite-код.' });
    }

    try {
        const metadata = await sock.newsletterMetadata('INVITE', code);
        console.log(`[WhatsApp] Канал найден: ${metadata.name} (ID: ${metadata.id})`);
        res.json({
            success: true,
            id: metadata.id,
            name: metadata.name,
            subscribers: metadata.subscribers,
            role: metadata.viewer_metadata?.role
        });
    } catch (err) {
        console.error('[WhatsApp] Ошибка резолва канала:', err);
        res.status(500).json({ error: 'Не удалось получить данные канала: ' + err.message });
    }
});

// Эндпоинт создания нового сообщества WhatsApp (Community)
app.post('/create-community', async (req, res) => {
    if (!isConnected || !sock) {
        return res.status(503).json({ error: 'WhatsApp не подключен. Отсканируйте QR-код.' });
    }

    const { name, description } = req.body;
    if (!name) {
        return res.status(400).json({ error: 'Укажите название сообщества (name).' });
    }

    try {
        console.log(`[WhatsApp] Создаем Сообщество: "${name}"...`);
        const result = await sock.communityCreate(name, description || '');
        console.log(`[WhatsApp] Сообщество создано! ID: ${result.id}`);
        
        let inviteCode = null;
        try {
            inviteCode = await sock.communityInviteCode(result.id);
        } catch (_) {}

        res.json({
            success: true,
            id: result.id,
            name: result.subject || name,
            inviteCode: inviteCode,
            inviteLink: inviteCode ? `https://chat.whatsapp.com/${inviteCode}` : null
        });
    } catch (err) {
        console.error('[WhatsApp] Ошибка создания сообщества:', err);
        res.status(500).json({ error: 'Не удалось создать сообщество: ' + err.message });
    }
});

// Эндпоинт создания группы (в том числе подгруппы сообщества)
app.post('/create-community-group', async (req, res) => {
    if (!isConnected || !sock) {
        return res.status(503).json({ error: 'WhatsApp не подключен. Отсканируйте QR-код.' });
    }

    const { name, description, announcementOnly } = req.body;
    if (!name) {
        return res.status(400).json({ error: 'Укажите название группы (name).' });
    }

    try {
        console.log(`[WhatsApp] Создаем группу: "${name}"...`);
        const group = await sock.groupCreate(name, []);
        const groupId = group.id;
        console.log(`[WhatsApp] Группа создана! ID: ${groupId}`);

        if (announcementOnly) {
            try {
                await sock.groupSettingUpdate(groupId, 'announcement');
                console.log(`[WhatsApp] Включен режим 'Только админы' для ${groupId}`);
            } catch (e) {
                console.warn(`[WhatsApp] Не удалось установить режим объявлений:`, e.message);
            }
        }

        if (description) {
            try {
                await sock.groupUpdateDescription(groupId, description);
            } catch (_) {}
        }

        let inviteCode = null;
        try {
            inviteCode = await sock.groupInviteCode(groupId);
        } catch (_) {}

        res.json({
            success: true,
            id: groupId,
            name: group.subject || name,
            inviteCode: inviteCode,
            inviteLink: inviteCode ? `https://chat.whatsapp.com/${inviteCode}` : null
        });
    } catch (err) {
        console.error('[WhatsApp] Ошибка создания группы:', err);
        res.status(500).json({ error: 'Не удалось создать группу: ' + err.message });
    }
});

// Эндпоинт получения invite-ссылки для любой группы или сообщества
app.post('/get-invite', async (req, res) => {
    if (!isConnected || !sock) {
        return res.status(503).json({ error: 'WhatsApp не подключен. Отсканируйте QR-код.' });
    }

    const { chatId } = req.body;
    if (!chatId) {
        return res.status(400).json({ error: 'Укажите chatId группы/сообщества.' });
    }

    try {
        let code = null;
        if (chatId.includes('@newsletter')) {
            const meta = await sock.newsletterMetadata('JID', chatId);
            code = meta.invite;
            return res.json({ success: true, inviteLink: `https://whatsapp.com/channel/${code}` });
        } else {
            code = await sock.groupInviteCode(chatId);
            return res.json({ success: true, inviteLink: `https://chat.whatsapp.com/${code}` });
        }
    } catch (err) {
        res.status(500).json({ error: 'Не удалось получить ссылку-приглашение: ' + err.message });
    }
});

// Эндпоинт создания нового канала (Newsletter)
app.post('/create-channel', async (req, res) => {
    if (!isConnected || !sock) {
        return res.status(503).json({ error: 'WhatsApp не подключен. Отсканируйте QR-код.' });
    }

    const { name, description } = req.body;
    if (!name) {
        return res.status(400).json({ error: 'Укажите название канала (name).' });
    }

    try {
        console.log(`[WhatsApp] Создаем канал: "${name}"...`);
        const result = await sock.newsletterCreate(name, description || '');
        console.log(`[WhatsApp] Канал создан: ${result.name} (ID: ${result.id}, Invite: ${result.invite})`);
        res.json({
            success: true,
            id: result.id,
            name: result.name,
            invite: result.invite,
            inviteLink: result.invite ? `https://whatsapp.com/channel/${result.invite}` : null
        });
    } catch (err) {
        console.error('[WhatsApp] Ошибка создания канала:', err);
        res.status(500).json({ error: 'Не удалось создать канал: ' + err.message });
    }
});

// Эндпоинт установки аватарки канала
app.post('/set-channel-avatar', async (req, res) => {
    if (!isConnected || !sock) {
        return res.status(503).json({ error: 'WhatsApp не подключен. Отсканируйте QR-код.' });
    }

    const { chatId, imagePath } = req.body;
    if (!chatId || !imagePath) {
        return res.status(400).json({ error: 'Укажите chatId и imagePath.' });
    }

    try {
        if (!fs.existsSync(imagePath)) {
            return res.status(404).json({ error: `Файл не найден: ${imagePath}` });
        }
        console.log(`[WhatsApp] Устанавливаем аватарку для ${chatId} из ${imagePath}...`);
        const imgBuffer = fs.readFileSync(imagePath);
        await sock.newsletterUpdatePicture(chatId, imgBuffer);
        console.log(`[WhatsApp] Аватарка успешно обновлена!`);
        res.json({ success: true, message: 'Аватарка успешно установлена!' });
    } catch (err) {
        console.error('[WhatsApp] Ошибка установки аватарки:', err);
        res.status(500).json({ error: 'Не удалось установить аватарку: ' + err.message });
    }
});

// Эндпоинт установки описания канала
app.post('/set-channel-description', async (req, res) => {
    if (!isConnected || !sock) {
        return res.status(503).json({ error: 'WhatsApp не подключен. Отсканируйте QR-код.' });
    }

    const { chatId, description } = req.body;
    if (!chatId || description === undefined) {
        return res.status(400).json({ error: 'Укажите chatId и description.' });
    }

    try {
        console.log(`[WhatsApp] Обновляем описание для ${chatId}...`);
        await sock.newsletterUpdateDescription(chatId, description);
        console.log(`[WhatsApp] Описание успешно обновлено для ${chatId}!`);
        res.json({ success: true, message: 'Описание успешно обновлено!' });
    } catch (err) {
        console.error('[WhatsApp] Ошибка обновления описания:', err);
        res.status(500).json({ error: 'Не удалось обновить описание: ' + err.message });
    }
});

// Эндпоинт отправки сообщения с фото в группу/сообщество/канал
app.post('/send', async (req, res) => {
    if (!isConnected || !sock) {
        return res.status(503).json({ error: 'WhatsApp не подключен. Отсканируйте QR-код.' });
    }

    const { chatId, imageUrl, caption } = req.body;

    if (!chatId || !caption) {
        return res.status(400).json({ error: 'Параметры chatId и caption обязательны.' });
    }

    try {
        let sentMessage;
        if (imageUrl) {
            const isRemote = imageUrl.startsWith('http://') || imageUrl.startsWith('https://');
            const imageContent = isRemote ? { url: imageUrl } : fs.readFileSync(imageUrl);
            sentMessage = await sock.sendMessage(chatId, {
                image: imageContent,
                caption: caption
            });
        } else {
            sentMessage = await sock.sendMessage(chatId, {
                text: caption
            });
        }

        console.log(`[WhatsApp] Пост успешно отправлен в ${chatId}`);
        res.json({
            success: true,
            messageId: sentMessage.key.id,
            timestamp: sentMessage.messageTimestamp
        });
    } catch (err) {
        console.error(`[WhatsApp] Ошибка отправки в ${chatId}:`, err);
        res.status(500).json({ error: err.message });
    }
});

// Эндпоинт для удалённой корректной остановки сервера из Python/Telegram
app.post('/shutdown', (req, res) => {
    console.log('[Bridge Server] Получена команда на завершение работы...');
    res.json({ success: true, message: 'Сервер останавливается' });
    setTimeout(() => {
        if (sock) {
            try { sock.end(); } catch (e) {}
        }
        process.exit(0);
    }, 1000);
});

app.listen(PORT, '127.0.0.1', () => {
    console.log(`[Bridge Server] HTTP API запущен на http://127.0.0.1:${PORT}`);
    connectToWhatsApp();
});
