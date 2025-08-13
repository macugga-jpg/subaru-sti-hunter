import os
import time
import json
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from bs4 import BeautifulSoup

TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT = os.getenv("TG_CHAT")
PORT = int(os.getenv("PORT", "10000"))
SENT_FILE = 'sent_ads.json'

# Wczytywanie zapisanych ofert
sent_ads = set()
if os.path.exists(SENT_FILE):
    try:
        with open(SENT_FILE, 'r') as f:
            sent_ads = set(json.load(f))
            print(f"Wczytano {len(sent_ads)} wcześniej wysłanych ogłoszeń.")
    except Exception as e:
        print("Błąd ładowania sent_ads:", e)


def send_telegram_message(text, photo_url=None):
    if not TG_TOKEN or not TG_CHAT:
        print("Brak TG_TOKEN lub TG_CHAT w zmiennych środowiskowych.")
        return False
    try:
        if photo_url:
            resp = requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
                data={
                    "chat_id": TG_CHAT,
                    "photo": photo_url,
                    "caption": text,
                    "parse_mode": "HTML"
                }
            )
        else:
            resp = requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                data={
                    "chat_id": TG_CHAT,
                    "text": text,
                    "parse_mode": "HTML"
                }
            )
        if resp.ok:
            print("✅ Wiadomość wysłana do Telegrama.")
            return True
        else:
            print(f"❌ Błąd API Telegrama: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        print("❌ Błąd wysyłki do Telegram:", e)
        return False


def pobierz_ogloszenia_otomoto():
    url = "https://www.otomoto.pl/osobowe/subaru/impreza?search%5Border%5D=relevance_web"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        print(f"Odpowiedź z Otomoto: status {r.status_code}, długość treści: {len(r.text)}")
        if r.ok:
            soup = BeautifulSoup(r.text, 'lxml')
            ads = []
            for article in soup.select('article[data-testid="listing-ad"]'):
                link_tag = article.select_one('a[data-testid="listing-ad-title"]')
                if link_tag:
                    link = link_tag['href']
                    if link.startswith('https://www.otomoto.pl/oferta/') and link not in sent_ads:
                        ads.append(link)
            print(f"🔍 Znaleziono {len(ads)} potencjalnych ofert przed filtrowaniem.")
            return ads
        else:
            print(f"❌ Błąd pobierania strony głównej: status {r.status_code}")
            return []
    except Exception as e:
        print("❌ Błąd pobierania Otomoto:", e)
        return []


def pobierz_detale(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.ok:
            soup = BeautifulSoup(r.text, 'lxml')

            # Nowe selektory Otomoto
            title_tag = soup.select_one('h1[data-testid="ad-title"]')
            title = title_tag.get_text(strip=True) if title_tag else 'Brak tytułu'

            price_tag = soup.select_one('span[data-testid="ad-price"]')
            price = price_tag.get_text(strip=True) if price_tag else 'Brak ceny'

            photo_tag = soup.select_one('img[data-testid="gallery-image"]')
            photo = photo_tag['src'] if photo_tag else None

            desc_tag = soup.select_one('div[data-testid="ad-description"]')
            desc_text = desc_tag.get_text(strip=True).lower() if desc_tag else ''

            print(f"📄 Sprawdzam: {title} | Cena: {price}")

            # Filtr "STI" w opisie lub tytule
            if 'sti' in desc_text or 'sti' in title.lower():
                return {
                    'title': title,
                    'price': price,
                    'photo': photo
                }
            else:
                print(f"⏩ Pomijam - brak 'sti' w tytule/opisie: {url}")
            return None
        else:
            print(f"❌ Błąd pobierania detali {url}: status {r.status_code}")
    except Exception as e:
        print(f"❌ Błąd pobierania detali {url}:", e)
    return None


def bot_loop():
    print("🤖 Bot uruchomiony!")
    send_telegram_message("Hej, bot Subaru STI już działa 🚀")
    while True:
        try:
            otomoto_ads = pobierz_ogloszenia_otomoto()
            new_ads_count = 0
            for ad in otomoto_ads:
                if ad not in sent_ads:
                    details = pobierz_detale(ad)
                    if details:
                        message = (
                            f"🚗 Nowe Subaru Impreza WRX STI:\n"
                            f"<b>{details['title']}</b>\n"
                            f"Cena: {details['price']}\n"
                            f"Link: {ad}"
                        )
                        success = send_telegram_message(message, photo_url=details['photo'])
                        if success:
                            sent_ads.add(ad)
                            new_ads_count += 1
                            with open(SENT_FILE, 'w') as f:
                                json.dump(list(sent_ads), f)
            print(f"✅ Runda zakończona - wysłano {new_ads_count} nowych ofert.")
            time.sleep(600)  # 10 minut
        except Exception as e:
            print("❌ Błąd w pętli bota:", e)
            time.sleep(60)


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
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("🛑 Stopping server")
        server.server_close()
