# BOT.CTL — Ubuntu Sunucu Kurulum Kılavuzu

Bu rehber, BOT.CTL panelini kendi Ubuntu sunucunda nasıl kuracağını **adım adım** anlatır.
Sıfır bir Ubuntu 22.04 / 24.04 sunucusu olduğunu varsayıyoruz.

> Panel: Telegram botlarını tek yerden başlat / durdur / izle / zamanla.  
> Stack: FastAPI + React + MongoDB + APScheduler.

---

## 0 — Önkoşullar

- Bir Ubuntu sunucusu (22.04 ya da 24.04 önerilir)
- `root` veya `sudo` yetkisi
- Sunucuya `ssh` erişimi
- Açık port: **80** (web), **22** (ssh). MongoDB ve backend yalnızca local çalışır.

---

## 1 — Sistem paketlerini kur

```bash
sudo apt update && sudo apt upgrade -y

# Python 3.11, Node 20, MongoDB, Nginx, supervisor, build araçları
sudo apt install -y python3 python3-venv python3-pip python3-dev \
                    build-essential curl wget unzip git nginx supervisor

# Node 20 (NodeSource)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash -
sudo apt install -y nodejs

# Yarn (frontend için)
sudo npm install -g yarn

# MongoDB 7.0 community
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | \
   sudo gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor
echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] \
  https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | \
  sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list
sudo apt update
sudo apt install -y mongodb-org
sudo systemctl enable --now mongod
```

---

## 2 — BOT.CTL kodunu sunucuya kopyala

Aşağıdaki klasör yapısını hazırla:

```
/opt/botctl/
├── backend/   # FastAPI server.py + auth.py + bot_manager.py + requirements.txt + .env
├── frontend/  # React uygulaması
└── bot_storage/  # uploaded bot dosyaları (otomatik oluşur)
```

```bash
sudo mkdir -p /opt/botctl && sudo chown -R $USER:$USER /opt/botctl
cd /opt/botctl
# Bu pencereden indirip aktarmak için:
#  - Emergent panelinden "Save to GitHub" ile repo oluştur ve clone et, ya da
#  - scp ile yerel makineden gönder:
#    scp -r ./app/backend  user@SUNUCU:/opt/botctl/
#    scp -r ./app/frontend user@SUNUCU:/opt/botctl/
```

---

## 3 — Backend kurulumu

```bash
cd /opt/botctl/backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### `backend/.env`'i sunucuya uyarla

```bash
nano .env
```

İçeriği:

```env
MONGO_URL="mongodb://localhost:27017"
DB_NAME="botctl_database"
CORS_ORIGINS="https://senin-domainin.com"
JWT_SECRET="GENERATED_RANDOM_64_HEX"   # aşağıdaki komutla üret
ADMIN_USERNAME="admin"
ADMIN_PASSWORD="9800102496Uu"
BOT_STORAGE_DIR="/opt/botctl/bot_storage"
```

Rastgele JWT_SECRET üretmek için:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

> **Önemli:** JWT_SECRET'ı muhakkak değiştir. Sunucuya özel olmalı.

---

## 4 — Frontend build

```bash
cd /opt/botctl/frontend
nano .env
```

```env
REACT_APP_BACKEND_URL=https://senin-domainin.com
```

> Eğer domain yok, IP ile de gidebilirsin: `http://SUNUCU_IP`

```bash
yarn install
yarn build
```

`build/` klasörü oluşur, nginx bunu serve edecek.

---

## 5 — Supervisor ile backend'i daemon yap

```bash
sudo nano /etc/supervisor/conf.d/botctl.conf
```

```ini
[program:botctl-backend]
command=/opt/botctl/backend/.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8001
directory=/opt/botctl/backend
user=root
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
stdout_logfile=/var/log/botctl-backend.out.log
stderr_logfile=/var/log/botctl-backend.err.log
environment=PYTHONUNBUFFERED=1
```

Yükle ve başlat:

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl status
# botctl-backend  RUNNING  pid 1234, uptime 0:00:05
```

---

## 6 — Nginx reverse proxy

```bash
sudo nano /etc/nginx/sites-available/botctl
```

```nginx
server {
    listen 80;
    server_name senin-domainin.com;   # ya da SUNUCU_IP
    client_max_body_size 200M;        # büyük .zip / session yüklemek için

    # Frontend (React build)
    root /opt/botctl/frontend/build;
    index index.html;

    # API
    location /api/ {
        proxy_pass         http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }

    # SPA fallback
    location / {
        try_files $uri /index.html;
    }
}
```

Etkinleştir:

```bash
sudo ln -sf /etc/nginx/sites-available/botctl /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 7 — (Opsiyonel) HTTPS ile Let's Encrypt

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d senin-domainin.com
```

Otomatik yenileme zaten kuruludur (`systemctl status certbot.timer`).

---

## 8 — Erişim ve ilk giriş

Tarayıcıdan **https://senin-domainin.com** (ya da http://IP) aç.

Giriş bilgileri (`.env` dosyasındaki):

```
kullanıcı: admin
şifre:     9800102496Uu
```

> İlk girişten sonra `.env`'deki şifreyi mutlaka değiştir, sonra
> `sudo supervisorctl restart botctl-backend` ile yeniden başlat — yeni şifre
> otomatik olarak veritabanına yazılır (idempotent admin seed).

---

## 9 — Bot ekleme (web panelden)

1. **Bot Ekle** düğmesine bas.
2. Bot adını ver (örn. *Kod Botu*).
3. Dosya alanına şunlardan birini seç:
   - Tek bir `.py` dosyası, ya da
   - Tüm botu içeren bir `.zip` (içinde session, json, media, vs.)
4. ZIP'te birden fazla `.py` varsa, giriş (entry) dosyasını seç.
5. **Otomatik yeniden başlat** açıksa bot çökse bile 5 sn içinde yeniden başlar.
6. Listede yeşil kareli "RUNNING" yazana kadar **Başlat** butonuna bas.

---

## 10 — Botları yönetmek

| Düğme         | İşlev                                         |
| ------------- | --------------------------------------------- |
| ▶ Başlat     | Bot process'ini başlatır                       |
| ■ Durdur     | SIGTERM → 8sn → SIGKILL ile durdurur           |
| ↻ Yeniden başlat | Durdur + Başlat                              |
| ▮ Loglar     | Canlı stdout/stderr (her 2 sn yenilenir)       |
| ⚙ Ayarlar    | İsim, açıklama, entry dosya, cron, dosya yönetimi |
| 🗑 Sil        | Bot ve tüm dosyalarını **kalıcı** olarak siler |

### Cron zamanlama örnekleri (Ayarlar → Zamanlama)

| Açıklama                  | start_cron   | stop_cron     |
| ------------------------- | ------------ | ------------- |
| Her gün 09:00'da başlat   | `0 9 * * *`  | —             |
| Her gün 23:00'te durdur   | —            | `0 23 * * *`  |
| Hafta içi 08–18           | `0 8 * * 1-5`| `0 18 * * 1-5`|

---

## 11 — Bot'lara özel paket gerekiyorsa

Bot kodun ek bir pip paketine ihtiyaç duyuyorsa (ör. `python-telegram-bot`,
`telethon`, `nest_asyncio`, `requests`) bunlar `backend/requirements.txt`
içinde tanımlıdır. Yeni bir paket lazım olursa:

```bash
cd /opt/botctl/backend && source .venv/bin/activate
pip install <yeni-paket>
pip freeze | grep <yeni-paket> >> requirements.txt
sudo supervisorctl restart botctl-backend
```

---

## 12 — Sorun giderme

| Belirti                                | Çözüm                                                       |
| -------------------------------------- | ----------------------------------------------------------- |
| Panel `/login`'e takılı kalıyor        | `sudo supervisorctl status` — backend çalışıyor mu?         |
| Botlar başlamıyor, "entry not found"   | Ayarlar'dan doğru `.py` entry dosyasını seç                |
| 500 hata                                | `tail -f /var/log/botctl-backend.err.log`                    |
| MongoDB bağlanmıyor                    | `sudo systemctl status mongod`                              |
| Frontend güncellenmedi                 | `cd frontend && yarn build`, `sudo systemctl reload nginx`  |
| Şifre değiştirmek                      | `.env`'de değiştir → `sudo supervisorctl restart botctl-backend` |

---

## 13 — Yedekleme

Yedeklemen gereken dizinler:

```bash
# MongoDB
mongodump --db botctl_database --out /backup/$(date +%F)

# Bot dosyaları (session, json, media — kritik)
tar czf /backup/bot_storage_$(date +%F).tgz /opt/botctl/bot_storage
```

Cron ile günlük otomatik yedekleme yapabilirsin.

---

## 14 — Güncelleme

Yeni bir sürüm geldiğinde:

```bash
cd /opt/botctl
git pull   # ya da yeni dosyaları scp ile aktar
cd backend && source .venv/bin/activate && pip install -r requirements.txt && deactivate
cd ../frontend && yarn install && yarn build
sudo supervisorctl restart botctl-backend
sudo systemctl reload nginx
```

---

İşin bitti. Tarayıcıdan **admin / 9800102496Uu** ile giriş yap ve botlarını yüklemeye başla.
