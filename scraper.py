import requests
import json
import os
import hashlib
from datetime import datetime

# === KONFIGURACJA ===
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
MAX_PRICE = int(os.environ.get("MAX_PRICE", 1500))
SEEN_FILE = "seen_offers.json"

# === NAGŁÓWKI (udajemy przeglądarkę) ===
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pl-PL,pl;q=0.9",
    "Referer": "https://lastminuter.pl/",
    "Origin": "https://lastminuter.pl",
}

# === MOŻLIWE ENDPOINTY API (próbujemy każdy) ===
API_URLS = [
    "https://api.lastminuter.pl/v1/offers",
    "https://api.lastminuter.pl/offers",
    "https://lastminuter.pl/api/offers",
    "https://lastminuter.pl/api/v1/offers",
]


def fetch_offers():
    """Próbuje pobrać oferty z różnych możliwych endpointów."""
    for url in API_URLS:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                print(f"✅ Znaleziono API: {url}")
                return data
            else:
                print(f"❌ {url} → HTTP {resp.status_code}")
        except Exception as e:
            print(f"❌ {url} → {e}")

    # Fallback: scraping strony z ofertami (nasze hity / znaleziska)
    return fetch_offers_fallback()


def fetch_offers_fallback():
    """Fallback: scraping strony HTML z ofertami."""
    try:
        # Próba pobrania danych przez stronę znalezisk
        resp = requests.get(
            "https://lastminuter.pl/ostatnie-znaleziska",
            headers=HEADERS,
            timeout=15
        )
        print(f"Strona znalezisk: HTTP {resp.status_code}, rozmiar: {len(resp.text)} bajtów")

        # Szukamy danych JSON osadzonych w stronie
        text = resp.text
        json_start = text.find('{"offers"')
        if json_start == -1:
            json_start = text.find('window.__INITIAL_STATE__')
        if json_start > 0:
            # Spróbuj wyciągnąć JSON
            json_end = text.find('</script>', json_start)
            json_str = text[json_start:json_end]
            try:
                return json.loads(json_str)
            except:
                pass

        print("⚠️ Nie udało się sparsować danych — strona może być w pełni dynamiczna (JS).")
        print("   Sprawdź ręcznie w przeglądarce DevTools → Network → XHR jakie requesty robi strona.")
        return None
    except Exception as e:
        print(f"❌ Fallback scraping: {e}")
        return None


def extract_offers(data):
    """Wyciąga listę ofert z odpowiedzi API (dostosuj do struktury)."""
    if data is None:
        return []

    # Próbuj różnych struktur JSON
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ["offers", "results", "data", "items", "wycieczki"]:
            if key in data and isinstance(data[key], list):
                return data[key]

    return []


def get_price(offer):
    """Wyciąga cenę z oferty (dostosuj do struktury)."""
    for field in ["price", "cena", "pricePerPerson", "cena_od", "min_price"]:
        if field in offer:
            val = offer[field]
            try:
                return float(str(val).replace(",", ".").replace("zł", "").strip())
            except:
                pass
    return None


def offer_id(offer):
    """Unikalny identyfikator oferty."""
    for field in ["id", "offerId", "offerUrl", "url", "link"]:
        if field in offer:
            return str(offer[field])
    # Fallback: hash z zawartości
    return hashlib.md5(json.dumps(offer, sort_keys=True).encode()).hexdigest()[:12]


def load_seen():
    """Wczytuje poprzednio widziane oferty."""
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r") as f:
                return set(json.load(f))
        except:
            pass
    return set()


def save_seen(seen_ids):
    """Zapisuje widziane oferty (max 5000)."""
    ids = list(seen_ids)[-5000:]
    with open(SEEN_FILE, "w") as f:
        json.dump(ids, f)


def send_telegram(message):
    """Wysyła wiadomość na Telegrama."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[TELEGRAM nie skonfigurowany] {message}")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print("✅ Telegram: wiadomość wysłana")
        else:
            print(f"❌ Telegram błąd: {resp.text}")
    except Exception as e:
        print(f"❌ Telegram wyjątek: {e}")


def format_offer(offer):
    """Formatuje ofertę do wiadomości Telegram."""
    # Spróbuj wyciągnąć dane z różnych możliwych pól
    name = (offer.get("name") or offer.get("title") or offer.get("hotel")
            or offer.get("nazwa") or "Oferta")
    dest = (offer.get("destination") or offer.get("country") or offer.get("kraj")
            or offer.get("kierunek") or "")
    price = get_price(offer)
    url = (offer.get("url") or offer.get("link") or offer.get("offerUrl") or "")
    date = (offer.get("departureDate") or offer.get("dataWylotu") or offer.get("date") or "")
    nights = (offer.get("nights") or offer.get("noce") or offer.get("duration") or "")

    msg = f"🔥 <b>Nowa oferta poniżej {MAX_PRICE} zł!</b>\n\n"
    msg += f"🏨 <b>{name}</b>"
    if dest:
        msg += f" — {dest}"
    msg += "\n"
    if price:
        msg += f"💰 Cena: <b>{price:.0f} zł</b> / os.\n"
    if date:
        msg += f"✈️ Wylot: {date}\n"
    if nights:
        msg += f"🌙 Noclegi: {nights}\n"
    if url:
        if not url.startswith("http"):
            url = "https://lastminuter.pl" + url
        msg += f"\n🔗 {url}"

    msg += f"\n\n⏰ {datetime.now().strftime('%H:%M:%S')}"
    return msg


def main():
    print(f"=== Lastminuter Bot — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    print(f"Filtr: oferty poniżej {MAX_PRICE} zł")

    # Pobierz oferty
    data = fetch_offers()
    offers = extract_offers(data)
    print(f"📦 Pobrano {len(offers)} ofert")

    if not offers:
        print("⚠️  Brak ofert do przetworzenia.")
        print("\n💡 WAŻNE: Strona lastminuter.pl używa React/SPA.")
        print("   Otwórz DevTools (F12) → Network → XHR/Fetch podczas przeglądania strony")
        print("   i sprawdź jakie requesty są wysyłane — wklej URL do API_URLS w skrypcie.")
        return

    # Filtrowanie po cenie
    cheap = [o for o in offers if (p := get_price(o)) is not None and p < MAX_PRICE]
    print(f"💸 Oferty poniżej {MAX_PRICE} zł: {len(cheap)}")

    # Sprawdź które są nowe
    seen = load_seen()
    new_offers = [o for o in cheap if offer_id(o) not in seen]
    print(f"🆕 Nowe oferty: {len(new_offers)}")

    # Wyślij powiadomienia
    for offer in new_offers:
        msg = format_offer(offer)
        print(f"→ Wysyłam: {offer.get('name', offer_id(offer))}")
        send_telegram(msg)

    # Zaktualizuj widziane
    all_ids = seen | {offer_id(o) for o in cheap}
    save_seen(all_ids)

    print("✅ Gotowe!")


if __name__ == "__main__":
    main()
