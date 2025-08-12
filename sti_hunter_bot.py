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
    except Exception as e:
        print("Błąd ładowania sent_ads:", e)

def send_telegram_message(text, photo_url=None):
    if not TG_TOKEN or not TG_CHAT:
        print("Brak TG_TOKEN lub TG_CHAT w zmiennych środowiskowych.")
        return False
    try:
        if photo_url:
            requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
                data={"chat_id": TG_CHAT, "photo": photo_url, "caption": text, "parse_mode": "HTML"}
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
    url = ("https://www.otomoto.pl/osobowe/subaru/impreza/?"
           "search%5Bfilter_float_year%3Afrom%5D=2004&"
           "search%5Bfilter_float_year%3Ato%5D=2012&"
           "search%5Border%5D=created_at_first%3Adesc")
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
                link = article.select_one('a[data-cy="listing-ad-title"]')['href']
                if link.startswith('https://www.otomoto.pl/oferta/') and link not in sent_ads:
                    ads.append(link)
            print(f"Znaleziono {len(ads)} potencjalnych ofert przed filtrem opisu.")
            return ads
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
            title = soup.select_one('h1.offer-title') or 'Brak tytułu'
            price = soup.select_one('span.offer-price__number') or 'Brak ceny'
            photo = soup.select_one('img.bigImage')['src'] if soup.select_one('img.bigImage') else None
            description = soup.select_one('div.offer-description') or ''
            if hasattr(description, 'text') and 'wrx sti' in description.text.lower():
                return {
                    'title': title.text.strip() if hasattr(title, 'text') else 'Brak tytułu',
                    'price': price.text.strip() if hasattr(price, 'text') else 'Brak ceny',
                    'photo': photo
                }
            return None
    except Exception as e:
        print(f"Błąd pobierania detali {url}:", e)
    return None

def bot_loop():
    print("Bot loop started")
    # Send test message to confirm Telegram connection
    send_telegram_message("Hej już działam!")
    while True:
        try:
            otomoto_ads = pobierz_ogloszenia_otomoto()
            for ad in otomoto_ads:
                if ad not in sent_ads:
                    details = pobierz_detale(ad)
                    if details:  # Tylko jeśli opis zawiera "wrx sti"
                        sent_ads.add(ad)
                        message = f"🚗 Nowe Subaru Impreza WRX STI:\n<b>{details['title']}</b>\nCena: {details['price']}\nLink: {ad}"
                        print("Wysyłam:", ad)
                        send_telegram_message(message, photo_url=details['photo'])
                        # Save sent_ads to file
                        with open(SENT_FILE, 'w') as f:
                            json.dump(list(sent_ads), f)
            print(f"Znaleziono {len(otomoto_ads) - len(sent_ads)} nowych ofert po filtrze opisu.")
            time.sleep(600)  # 10 minutes
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
