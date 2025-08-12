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

# Load sent ads from file
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
                data={"chat_id": TG_CHAT, "photo": photo_url, "caption": text, "parse_mode": "HTML"}
            )
        else:
            resp = requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                data={"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML"}
            )
        if resp.ok:
            print("Wiadomość wysłana do Telegrama.")
            return True
        else:
            print(f"Błąd API Telegrama: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        print("Błąd wysyłki do Telegram:", e)
        return False

def pobierz_ogloszenia_otomoto():
    url = "https://www.otomoto.pl/osobowe/subaru/impreza?search%5Border%5D=relevance_web"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        print(f"Odpowiedź z Otomoto: status {r.status_code}, długość treści: {len(r.text)}")
        if r.ok:
            soup = BeautifulSoup(r.text, 'lxml')
            ads = []
            for article in soup.select('article[data-testid="listing-ad"]'):
                link_tag = article.select_one('a[data-cy="listing-ad-title"]')
                if link_tag:
                    link = link_tag['href']
                    if link.startswith('https://www.otomoto.pl/oferta/') and link not in sent_ads:
                        ads.append(link)
            print(f"Znaleziono {len(ads)} potencjalnych ofert przed filtrem opisu.")
            return ads
        else:
            print(f"Błąd pobierania strony głównej: status {r.status_code}")
            return []
    except Exception as e:
        print("Błąd pobierania Otomoto:", e)
        return []

def pobierz_detale(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.ok:
            soup = BeautifulSoup(r.text, 'lxml')

            # Tytuł ogłoszenia
            title_tag = soup.select_one('h1.offer-title')
            title = title_tag.text.strip() if title_tag else 'Brak tytułu'

            # Cena
            price_tag = soup.select_one('span.offer-price__number')
            price = price_tag.text.strip() if price_tag else 'Brak ceny'

            # Główne zdjęcie - teraz jest w elemencie img[data-testid="gallery-image-0"]
            photo_tag = soup.select_one('img[data-testid="gallery-image-0"]')
            photo = photo_tag['src'] if photo_tag else None

            # Opis
            desc_tag = soup.select_one('div.offer-description__content')
            desc_text = desc_tag.text.lower() if desc_tag else ''

            print(f"Debug opisu dla {url}: {desc_text[:200]}...")  # debug pierwszych 200 znaków opisu

            # Sprawdzamy czy "sti" jest w opisie lub w tytule (małe litery)
            if 'sti' in desc_text or 'sti' in title.lower():
                return {
                    'title': title,
                    'price': price,
                    'photo': photo
                }
            else:
                print(f"Oferta pominięta - brak 'sti' w tytule lub opisie: {url}")
            return None
        else:
            print(f"Błąd pobierania detali {url}: status {r.status_code}")
    except Exception as e:
        print(f"Błąd pobierania detali {url}:", e)
    return None

def bot_loop():
    print("Bot loop started")
    send_telegram_message("Hej już działam!")
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
                        print("Wysyłam:", ad)
                        success = send_telegram_message(message, photo_url=details['photo'])
                        if success:
                            sent_ads.add(ad)
                            new_ads_count += 1
                            # Zapisujemy tylko po udanym wysłaniu
                            with open(SENT_FILE, 'w') as f:
                                json.dump(list(sent_ads), f)
            print(f"Zakończono rundę - wysłano {new_ads_count} nowych ofert.")
            time.sleep(600)  # 10 minut
        except Exception as e:
            print("Błąd w pętli bota:", e)
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
    print(f"HTTP health server listening on port {PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping server")
        server.server_close()
