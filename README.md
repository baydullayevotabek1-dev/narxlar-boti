# Narxlar Boti

Telegram bot: foydalanuvchi model nomlarini yuboradi, bot barcha do'konlarning skidkali narxlarini qaytaradi.

## Lokal ishga tushirish

```bash
pip install -r requirements.txt
cp .env.example .env
# .env'ga BOT_TOKEN, GEMINI_API_KEY, ADMIN_IDS yozing
python -m bot.main
```

## Render.com'ga deploy (tekin, 24/7)

### 1. GitHub'ga yuklash
```bash
git init
git add .
git commit -m "narxlar boti"
git branch -M main
git remote add origin https://github.com/USERNAME/narxlar-boti.git
git push -u origin main
```

**Muhim:** `.env` faylni yuklamang (`.gitignore`'da bor).

### 2. Render'da yaratish
1. https://render.com — ro'yxatdan o'ting (GitHub bilan)
2. **New +** → **Web Service**
3. GitHub repositoriyani ulang
4. Sozlamalar:
   - Name: `narxlar-boti`
   - Environment: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python -m bot.main`
   - Plan: **Free**
5. **Environment Variables**:
   - `BOT_TOKEN` — Telegram token
   - `GEMINI_API_KEY` — Gemini API key
   - `ADMIN_IDS` — admin user ID (8999182542)
6. **Create Web Service**

### 3. 24/7 ishlashi uchun (Render free plan)
Render free plan 15 daqiqa harakatsizlikdan keyin uxlaydi. Uyg'oq turishi uchun:

1. https://uptimerobot.com — tekin ro'yxat
2. **Add New Monitor** → HTTP(s)
3. URL: `https://SIZNING-BOT.onrender.com/health`
4. Interval: 5 daqiqa
5. **Create Monitor**

Bot 24/7 ishlaydi. ✅

## Admin buyruqlar (faqat ADMIN_IDS)

- `/admin` — panel
- `/update DoкonNomi` — keyin Excel yuborish
- `/set_discount DoкonNomi 25` — skidka o'zgartirish
- `/list_stores` — do'konlar
- `/stats` — statistika

## Foydalanuvchi

Botga model yuboradi (bitta yoki bir nechta, vergul yoki yangi qator bilan) —
bot barcha do'konlardagi narxlarni skidka bilan qaytaradi.
