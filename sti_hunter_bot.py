import os
import re
import time
import json
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlsplit, urlunsplit

TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT = os.getenv("TG_CHAT")
PORT = int(os.getenv("PORT", "10000"))
SENT_FILE = 'sent_ads.json'

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.otomoto.pl/"
}

LISTING_URL = "https://www.otomoto.pl/osobowe/subaru/impreza?search%5Border%5D=relevance_web"

# --- pamięć wysłanych ogłoszeń ---
sent_ads = set()
if os.path.exists(SENT_FILE):
    try:
        with open(SENT_FILE, 'r') as f:
            sent_ads = set(json.load(f))
            print(f"Wczytano {len(sent_ads)} wcześniej wysłanych ogłoszeń.")
    except Exception as e:
        print("Błąd ładowania sent_ads:", e)

def normalize_url(u: str) -> str:
    """Usuwa query/hash, robi absolutny URL."""
    try:
        parts = urlsplit(u)
        if not parts.scheme:
            u = urljoin("https://www.otomoto.pl/", u)
            parts = urlsplit(u)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    except Exception:
        return u

def send_telegram_message(text, photo_url=None):
    if not TG_TOKEN or not TG_CHAT:
        print("Brak TG_TOKEN lub TG_CHAT w zmiennych środowiskowych.")
        return False
    try:
        if photo_url:
            resp = requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
                data={"chat_id": TG_CHAT, "caption": text, "parse_mode": "HTML"},
                files=None,
                params={"disable_web_page_preview": True},
                json=None
            )
            # Telegram oczekuje 'photo' w data, gdy to URL – podajemy w data:
            if not resp.ok:
                resp = requests.post(
                    f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
                    data={"chat_id": TG_CHAT, "photo": photo_url, "caption": text, "parse_mode": "HTML"}
                )
        else:
            resp = requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                data={"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
            )
        if resp.ok:
            print("✅ Wiadomość wysłana do Telegrama.")
            return True
        print(f"❌ Błąd API Telegrama: {resp.status_code} {resp.text}")
    except Exception as e:
        print("❌ Błąd wysyłki do Telegram:", e)
    return False

def pobierz_ogloszenia_otomoto():
    """Z listingu łapiemy WSZYSTKIE linki zawierające '/oferta/' (również względne)."""
    try:
        r = requests.get(LISTING_URL, headers=BASE_HEADERS, timeout=20)
        print(f"Odpowiedź z Otomoto: status {r.status_code}, długość treści: {len(r.text)}")
        if not r.ok:
            return []
        soup = BeautifulSoup(r.text, 'lxml')

        # 1) Spróbujmy „oficjalnych” selektorów (gdyby były obecne)
        links = set()
        for a in soup.select('a[href]'):
            href = a.get('href', '')
            if '/oferta/' in href:
                links.add(normalize_url(href))

        # Fallback: wyciągnij linki regexem z całego HTML (na wypadek shadow DOM / dynamic SSR)
        if not links:
            regex = re.compile(r'href=["\']([^"\']+/oferta/[^"\']+)["\']')
            for m in regex.finditer(r.text):
                links.add(normalize_url(m.group(1)))

        # Odfiltruj już wysłane
        fresh = [u for u in links if u.startswith("https://www.otomoto.pl/oferta/") and u not in sent_ads]
        print(f"🔍 Znaleziono {len(fresh)} linków ofert (po normalizacji/duplikatach).")
        return sorted(fresh)
    except Exception as e:
        print("❌ Błąd pobierania listy Otomoto:", e)
        return []

def extract_meta(soup, prop):
    m = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
    return m["content"].strip() if m and m.get("content") else None

def pobierz_detale(url):
    try:
        r = requests.get(url, headers=BASE_HEADERS, timeout=20)
        if not r.ok:
            print(f"❌ Błąd pobierania detali {url}: {r.status_code}")
            return None

        soup = BeautifulSoup(r.text, 'lxml')

        # --- Tytuł: najpierw data-testid, potem og:title, potem <h1> ---
        title = None
        t = soup.select_one('h1[data-testid="ad-title"]')
        if t:
            title = t.get_text(strip=True)
        if not title:
            title = extract_meta(soup, "og:title")
        if not title:
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else "Brak tytułu"

        # --- Cena: data-testid, potem og:priceAmount / product:price:amount, fallback tekst ---
        price = None
        p = soup.select_one('span[data-testid="ad-price"]')
        if p:
            price = p.get_text(strip=True)
        if not price:
            price = extract_meta(soup, "product:price:amount") or extract_meta(soup, "og:price:amount")
        if not price:
            # Czasem cena bywa w atrybucie content JSON-LD – prosty fallback:
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        if "offers" in data and isinstance(data["offers"], dict):
                            price = data["offers"].get("price") or data["offers"].get("priceSpecification", {}).get("price")
                            if price:
                                break
                except Exception:
                    pass
        if not price:
            price = "Brak ceny"

        # --- Opis: data-testid, potem og:description, potem JSON-LD description ---
        desc_text = ""
        d = soup.select_one('div[data-testid="ad-description"]')
        if d:
            desc_text = d.get_text(" ", strip=True)
        if not desc_text:
            ogd = extract_meta(soup, "og:description")
            desc_text = ogd or ""
        if not desc_text:
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict) and "description" in data:
                        desc_text = str(data["description"])
                        break
                except Exception:
                    pass
        desc_low = desc_text.lower()

        # --- Zdjęcie: og:image najsolidniejsze ---
        photo = extract_meta(soup, "og:image")
        if not photo:
            img = soup.select_one('img[data-testid="gallery-image"], img[alt]')
            photo = img.get("src") if img and img.get("src") else None

        print(f"📄 Sprawdzam: {title} | Cena: {price} | URL: {url}")

        # Filtr „STI” w tytule/opisie
        if "sti" in (title or "").lower() or "sti" in desc_low:
            return {"title": title, "price": price, "photo": photo}
        else:
            print(f"⏩ Pomijam - brak 'sti' w tytule/opisie: {url}")
            return None

    except Exception as e:
        print(f"❌ Błąd pobierania detali {url}:", e)
        return None

def bot_loop():
    print("🤖 Bot uruchomiony!")
    send_telegram_message("Hej, bot Subaru STI już działa 🚀 (Otomoto)")
    while True:
        try:
            links = pobierz_ogloszenia_otomoto()
            new_ads = 0
            for ad in links:
                if ad in sent_ads:
                    continue
                details = pobierz_detale(ad)
                time.sleep(1.2)  # delikatna pauza, mniej banów
                if not details:
                    continue
                msg = (
                    "🚗 Nowe Subaru Impreza (STI):\n"
                    f"<b>{details['title']}</b>\n"
                    f"Cena: {details['price']}\n"
                    f"Link: {ad}"
                )
                ok = send_telegram_message(msg, photo_url=details.get("photo"))
                if ok:
                    sent_ads.add(ad)
                    new_ads += 1
                    with open(SENT_FILE, 'w') as f:
                        json.dump(list(sent_ads), f)
            print(f"✅ Runda zakończona - wysłano {new_ads} nowych ofert.")
            time.sleep(600)  # 10 minut
        except Exception as e:
            print("❌ Błąd w pętli bota:", e)
            time.sleep(60)

class HealthHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain; charset=utf-8')
        self.end_headers()
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain; charset=utf-8')
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
