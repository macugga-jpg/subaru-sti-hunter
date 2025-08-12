import os
import time
import json
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

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
    url = ("https://www.otomoto.pl/osobowe/subaru/impreza/sti/?"
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
        if r.ok:
            soup = BeautifulSoup(r.text, 'lxml')
            ads = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith('https://www.otomoto.pl/oferta/') and href not in sent_ads:
                    ads.append(href)
            return list(set(ads))
        return []
    except Exception as e:
        print("Błąd pobierania Otomoto:", e)
        return []

def pobierz_ogloszenia_mobilede():
    url = ("https://suchen.mobile.de/fahrzeuge/search.html?"
           "makeModelVariant1.makeId=20900&"
           "makeModelVariant1.modelId=26&"
           "minFirstRegistrationDate=2004&"
           "maxFirstRegistrationDate=2012&"
           "usage=USED&"
           "powerunit=PETROL&"
           "transmission=MANUAL&"
           "priceCurrency=EUR&"
           "sortOption.sortBy=creationTime&"
           "sortOption.sortOrder=DESC")
    try:
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.get(url)
        time.sleep(5)  # Wait for JS to load
        soup = BeautifulSoup(driver.page_source, 'lxml')
        driver.quit()
        ads = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if 'https://suchen.mobile.de/fahrzeuge/details' in href and href not in sent_ads:
                ads.append(href)
        return list(set(ads))
    except Exception as e:
        print("Błąd pobierania mobile.de:", e)
        return []

def pobierz_detale(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.ok:
            soup = BeautifulSoup(r.text, 'lxml')
            # Adjust selectors based on site (Otomoto or mobile.de)
            title = soup.find('h1') or soup.find('h2') or 'Brak tytułu'
            price = soup.find('span', class_='offer-price__number') or soup.find('div', class_='price') or 'Brak ceny'
            year = soup.find('span', class_='offer-meta__value') or soup.find('div', class_='g-col-6') or 'Brak roku'
            photo = soup.find('img', class_='bigImage')['src'] if soup.find('img', class_='bigImage') else None
            return {
                'title': title.text.strip() if hasattr(title, 'text') else 'Brak tytułu',
                'price': price.text.strip() if hasattr(price, 'text') else 'Brak ceny',
                'year': year.text.strip() if hasattr(year, 'text') else 'Brak roku',
                'photo': photo
            }
    except Exception as e:
        print(f"Błąd pobierania detali {url}:", e)
    return {'title': 'Brak detali', 'price': '', 'year': '', 'photo': None}

def bot_loop():
    print("Bot loop started")
    while True:
        try:
            otomoto_ads = pobierz_ogloszenia_otomoto()
            mobilede_ads = pobierz_ogloszenia_mobilede()
            new_ads = otomoto_ads + mobilede_ads

            for ad in new_ads:
                if ad not in sent_ads:
                    sent_ads.add(ad)
                    details = pobierz_detale(ad)
                    message = f"🚗 Nowe Subaru WRX STI:\n<b>{details['title']}</b>\nCena: {details['price']}\nRok: {details['year']}\nLink: {ad}"
                    print("Wysyłam:", ad)
                    send_telegram_message(message, photo_url=details['photo'])
                    # Save sent_ads to file
                    with open(SENT_FILE, 'w') as f:
                        json.dump(list(sent_ads), f)
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
