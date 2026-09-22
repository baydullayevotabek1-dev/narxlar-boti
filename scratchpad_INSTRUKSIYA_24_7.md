# 🌙 Botni 24/7 uyg'oq qilish — YOSHBOLKAGA MOS INSTRUKSIYA

**Kim bajaradi:** Siz (yoki xo'jayin)
**Vaqti:** 10 daqiqa
**Xarajat:** Tekin

---

## 📌 QADAM 1 — Render'dan bot URL'ini olish

1. Brauzer oching (Chrome, Edge yoki boshqa)
2. Yozing: **`dashboard.render.com`** → Enter bosing
3. Agar login so'rasa — GitHub bilan kiring
4. Ochilgan sahifada bot ro'yxati bor. **`narxlar-boti`** ustiga bosing
5. Yuqorida bot nomi tagida yashil rangdagi havola turadi, masalan:

    ```
    https://narxlar-boti-abc1.onrender.com
    ```

6. Bu havolani **sichqoncha bilan tanlab**, **Ctrl+C** bosing (nusxa oling)
7. Ochilgan brauzer sahifasini yopmang — keyin kerak bo'ladi

---

## 📌 QADAM 2 — UptimeRobot'ga ro'yxatdan o'ting

1. **Yangi tab** oching (yuqoridagi + belgisini bosing)
2. Adress qatoriga yozing: **`uptimerobot.com`** → Enter
3. Yuqori o'ng burchakda **"Register for FREE"** (yashil tugma) — bosing
4. Kichik forma ochiladi. To'ldiring:
   - **Full Name:** ismingiz (masalan: `Otabek`)
   - **Email:** email manzilingiz
   - **Password:** kuchli parol (masalan: `Narx2026!`)
5. **"Register now"** ni bosing
6. Emailingizga tasdiqlash xati keladi. Emailni oching → xatdagi **tugma/havolani** bosing
7. UptimeRobot dashboard'iga qaytadan tushasiz

---

## 📌 QADAM 3 — Monitor qo'shish (bot uyg'oq turishi uchun)

1. Yuqorida yashil **"+ New monitor"** tugmasini bosing

2. **Monitor Type** — **`HTTP(s)`** ni tanlang (odatda avtomatik tanlangan)

3. **Friendly Name** maydoniga yozing:
   ```
   Narxlar Boti
   ```

4. **URL (or IP)** maydoniga QADAM 1 da nusxa olgan havolangizni qo'ying (**Ctrl+V**).
   ⚠️ **MUHIM:** Havola oxiriga **`/health`** qo'shing!

   Masalan:
   ```
   https://narxlar-boti-abc1.onrender.com/health
   ```

5. **Monitoring interval** — **`5 minutes`** ni tanlang (past variant)

6. Sahifani pastga aylantiring va **"Create monitor"** tugmasini bosing

---

## 📌 QADAM 4 — Botni uyg'otish (birinchi marta)

Bot hozir uxlab yotgan bo'lishi mumkin. Uni uyg'otamiz:

1. QADAM 1 dagi Render sahifasiga qayting
2. Bot havolasini brauzerda oching (havola ustiga bosing)
3. **30-60 sekund kuting** — sahifada "OK" yozuvi chiqishi kerak
4. Endi bot uyg'oq ✅

## 📌 QADAM 5 — Telegram'da tekshirish

1. Telegram'ni oching
2. **@Mushikvisionkonkurent_bot** ni oching
3. **`/start`** yuboring
4. Salom xabari kelishi kerak

Agar kelmasa — 1 daqiqa kutib qayta yuboring (bot uyg'onmoqda).

---

## ✅ TAYYOR — endi bot 24/7 ishlaydi

- UptimeRobot har 5 daqiqada botni "chertadi" → uyqu bosmaydi
- Render tekin plan chegarasi: **oyiga 750 soat** (30 kun × 24 soat = 720 soat) — sig'adi
- Har hafta bot ishlab turibdi

---

## 🚨 Agar biror qadamda qiynalsangiz

**"Login qanaqa qilaman?"** — GitHub bilan tugmasini bosing, GitHub'ga bir marta kirasiz

**"URL qayerda?"** — Render dashboard'da bot nomi ostida yashil rangda turadi

**"Monitor yaratilmadi"** — havolaga `/health` qo'shdingizmi? Tekshiring

**"Bot javob bermayapti"** — birinchi marta 1-2 daqiqa uyg'onishi kerak. Kuting

---

## 📞 Nima qilsam bo'lmadi?

Screenshot oling → menga yuboring → hal qilaman.
