# sti_hunter_bot.py
import os
import time
import re
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler

TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT = os.getenv("TG_CHAT")
PORT = int(os.getenv("PORT", "10000"))

sent_ads = set()

def send_telegram_message(text, photo_url=None):
    if not TG_TOKEN or not TG_CHAT:
        print("Brak TG_TOKEN lub TG_CHAT w zmiennych środowiskowych.")
        return False
    try:
        if photo_url:
            requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
                data={"chat_id": TG_CHAT, "photo": photo_url, "caption": text}
            )
        else:
            requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                data={"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML"}
            )
        return True
    except Exception as e:
        print("Błąd wysyłki do Telegram:", e)
        return False

def pobierz_ogloszenia_otomoto():
    url = ("https://www.otomoto.pl/osobowe/subaru/impreza/sti/?"
           "search%5Bfilter_enum_generation%5D%5B0%5D=blobeye&"
           "search%5Bfilter_enum_generation%5D%5B1%5D=hawkeye&"
           "search%5Bfilter_enum_generation%5D%5B2%5D=gr&"
           "search%5Bfilter_enum_generation%5D%5B3%5D=gv&"
           "search%5Bfilter_enum_type%5D=limitowana-edition&"
           "search%5Border%5D=created_at_first%3Adesc")
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        ads = []
        if r.ok:
            matches = re.findall(r'href="(https://www.otomoto.pl/oferta/[^"]+)"', r.text)
            for link in set(matches):
                if link not in sent_ads:
                    ads.append(link)
        return ads
    except Exception as e:
        print("Błąd pobierania Otomoto:", e)
        return []

def pobierz_ogloszenia_mobilede():
    url = ("https://suchen.mobile.de/fahrzeuge/search.html?"
           "makeModelVariant1.makeId=20900&"
           "makeModelVariant1.modelId=26&"
           "usage=USED&"
           "powerunit=PETROL&"
           "transmission=MANUAL&"
           "priceCurrency=EUR&"
           "sortOption.sortBy=creationTime&"
           "sortOption.sortOrder=DESC")
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        ads = []
        if r.ok:
            matches = re.findall(r'href="(https://suchen.mobile.de/fahrzeuge/details[^"]+)"', r.text)
            for link in set(matches):
                if link not in sent_ads:
                    ads.append(link)
        return ads
    except Exception as e:
        print("Błąd pobierania mobile.de:", e)
        return []

def bot_loop():
    print("Bot loop started")
    # Przy pierwszym uruchomieniu wyśle wszystko co znajdzie (zgodnie z Twoim życzeniem)
    while True:
        try:
            otomoto_ads = pobierz_ogloszenia_otomoto()
            mobilede_ads = pobierz_ogloszenia_mobilede()
            new_ads = otomoto_ads + mobilede_ads

            for ad in new_ads:
                if ad not in sent_ads:
                    sent_ads.add(ad)
                    message = f"🚗 Nowe Subaru STI:\n{ad}"
                    print("Wysyłam:", ad)
                    send_telegram_message(message)
            # Sleep między kolejnymi sprawdzeniami
            time.sleep(600)  # 10 minut
        except Exception as e:
            print("Błąd w pętli bota:", e)
            time.sleep(60)

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type','text/plain')
        self.end_headers()
        self.wfile.write(b'OK')

if __name__ == "__main__":
    # Start bot in background thread
    t = threading.Thread(target=bot_loop, daemon=True)
    t.start()

    # Start simple HTTP server (Render wymaga nasłuchu na $PORT dla web services)
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"HTTP health server listening on port {PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping server")
        server.server_close()

