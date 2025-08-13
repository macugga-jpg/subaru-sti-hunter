import os
import time
import json
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler

# ===== KONFIGURACJA =====
TG_TOKEN = os.getenv("TG_TOKEN")  # Token Telegram bota
TG_CHAT = os.getenv("TG_CHAT")    # ID czatu/kanalu
PORT = int(os.getenv("PORT", "10000"))
SENT_FILE = 'sent_ads.json'

# Parametry wyszukiwania
SEARCH_URL = "https://www.otomoto.pl/api/v1/search"

SEARCH_PARAMS = {
    "category_id": "29",          # samochody osobowe
    "brand": "subaru",
    "model": "impreza",
    "page": "1",
    "size": "50",                 # maks. liczba wyników na stronę
    "sort": "created_at:desc"     # najnowsze ogłoszenia
}

# ===== ŁADOWANIE WYSŁANYCH =====
sent_ads = set()
if os.path.exists(SENT_FILE):
    try:
        with open(SENT_FILE, 'r') as f:
            sent_ads = set(json.load(f))
            print(f"✅ Wczytano {len(sent_ads)} wcześniej wysłanych ogłoszeń.")
    except Exception as e:
        print("⚠️ Błąd ładowania sent_ads:", e)

# ===== FUNKCJE =====
def send_telegram_message(text, photo_url=None):
    if not TG_TOKEN or not TG_CHAT:
        print("❌ Brak TG_TOKEN lub TG_CHAT.")
        return False
    try:
        if photo_url:
            resp = requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
                data={"chat_id": TG_CHAT, "photo": photo_url, "caption": text, "parse_mode": "HTML"}
            )
        else:
            resp = requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                data={"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML"}
            )
        if resp.ok:
            print("📩 Wiadomość wysłana.")
            return True
        else:
            print(f"⚠️ Błąd API Telegrama: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        print("⚠️ Błąd wysyłki do Telegram:", e)
        return False

def pobierz_ogloszenia_otomoto():
    try:
        r = requests.get(SEARCH_URL, params=SEARCH_PARAMS, timeout=15)
        print(f"🌍 API Otomoto: {r.status_code}")
        if r.ok:
            data = r.json()
            ads = []
            for ad in data.get("ads", []):
                ad_id = str(ad.get("id"))
                title = ad.get("title", "").lower()
                desc = (ad.get("description", "") or "").lower()
                if "sti" in title or "sti" in desc:
                    if ad_id not in sent_ads:
                        ads.append({
                            "id": ad_id,
                            "title": ad.get("title"),
                            "price": ad.get("price", {}).get("value", "Brak ceny"),
                            "currency": ad.get("price", {}).get("currency", ""),
                            "photo": ad.get("photos", [{}])[0].get("url", None),
                            "url": f"https://www.otomoto.pl/oferta/{ad.get('slug', '')}"
                        })
            print(f"🔍 Znaleziono {len(ads)} ofert po filtrze STI.")
            return ads
        else:
            return []
    except Exception as e:
        print("⚠️ Błąd pobierania ogłoszeń:", e)
        return []

def bot_loop():
    print("🤖 Bot uruchomiony!")
    send_telegram_message("Bot STI wystartował 🚗🔥")
    while True:
        ads = pobierz_ogloszenia_otomoto()
        for ad in ads:
            msg = f"<b>{ad['title']}</b>\nCena: {ad['price']} {ad['currency']}\n{ad['url']}"
            if send_telegram_message(msg, photo_url=ad['photo']):
                sent_ads.add(ad["id"])
                with open(SENT_FILE, 'w') as f:
                    json.dump(list(sent_ads), f)
        time.sleep(600)  # co 10 minut

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')

if __name__ == "__main__":
    t = threading.Thread(target=bot_loop, daemon=True)
    t.start()
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"🌍 HTTP health server listening on port {PORT}")
    server.serve_forever()
