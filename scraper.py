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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pl-PL,pl;q=0.9",
    "Content-Type": "application/json",
    "Referer": "https://lastminuter.pl/",
    "Origin": "https://lastminuter.pl",
}

PAYLOAD = {
    "filters_not": "",
    "filters_and": "",
    "sorting": "price",
    "page": 0,
    "filters_ext": 0,
    "context": {"slugs": []}
}


def fetch_offers():
    try:
        resp = requests.post(
            "https://lastminuter.pl/offers/",
            headers=HEADERS,
            json=PAYLOAD,
            timeout=15
        )
        print(f"API: HTTP {resp.status_code}, rozmiar: {len(resp.content)} bajtów")
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"Błąd: {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"Wyjątek: {e}")
        return None


def extract_offers(data):
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ["trips", "deals", "offers", "results", "data", "items"]:
            if key in data and isinstance(data[key], list):
                return data[key]
        # Pokaż klucze żeby debugować strukturę
        print(f"Klucze w odpowiedzi: {list(data.keys())}")
    return []


def get_price(offer):
    for field in ["price", "cena", "pricePerPerson", "cena_od", "min_price", "price_pax"]:
        if field in offer:
            val = offer[field]
            try:
                return float(str(val).replace(",", ".").replace("zł", "").replace(" ", "").strip())
            except:
                pass
    return None


def offer_id(offer):
    for field in ["id", "offerId", "offer_id", "offerUrl", "url", "link"]:
        if field in offer:
            return str(offer[field])
    return hashlib.md5(json.dumps(offer, sort_keys=True).encode()).hexdigest()[:12]


def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r") as f:
                return set(json.load(f))
        except:
            pass
    return set()


def save_seen(seen_ids):
    ids = list(seen_ids)[-5000:]
    with open(SEEN_FILE, "w") as f:
        json.dump(ids, f)


def send_telegram(message):
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
    name = (offer.get("name") or offer.get("title") or offer.get("hotel")
            or offer.get("nazwa") or offer.get("hotel_name") or "Oferta")
    dest = (offer.get("destination") or offer.get("country") or offer.get("kraj")
            or offer.get("kierunek") or offer.get("country_name") or "")
    price = get_price(offer)
    url = (offer.get("url") or offer.get("link") or offer.get("offer_url") or "")
    date = (offer.get("departureDate") or offer.get("dataWylotu") or offer.get("date")
            or offer.get("departure_date") or "")
    nights = (offer.get("nights") or offer.get("noce") or offer.get("duration") or "")
    city = (offer.get("departureCity") or offer.get("departure_city") or offer.get("miasto") or "")

    msg = f"🔥 <b>Nowa oferta poniżej {MAX_PRICE} zł!</b>\n\n"
    msg += f"🏨 <b>{name}</b>"
    if dest:
        msg += f" — {dest}"
    msg += "\n"
    if price:
        msg += f"💰 Cena: <b>{price:.0f} zł</b> / os.\n"
    if date:
        msg += f"✈️ Wylot: {date}"
        if city:
            msg += f" z {city}"
        msg += "\n"
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

    data = fetch_offers()

    # Debug: pokaż surową odpowiedź jeśli mało ofert
    if data and isinstance(data, dict):
        print(f"Struktura odpowiedzi (klucze): {list(data.keys())}")

    offers = extract_offers(data)
    print(f"📦 Pobrano {len(offers)} ofert")

    if offers:
        print(f"Przykładowa oferta: {offers[0]}")

    if not offers:
        print("⚠️ Brak ofert — sprawdź strukturę odpowiedzi powyżej")
        if data:
            print(f"Surowa odpowiedź (pierwsze 500 znaków): {str(data)[:500]}")
        return

    # Filtrowanie po cenie
    cheap = [o for o in offers if (p := get_price(o)) is not None and p < MAX_PRICE]
    print(f"💸 Oferty poniżej {MAX_PRICE} zł: {len(cheap)}")

    # Sprawdź które są nowe
    seen = load_seen()
    new_offers = [o for o in cheap if offer_id(o) not in seen]
    print(f"🆕 Nowe oferty: {len(new_offers)}")

    for offer in new_offers:
        msg = format_offer(offer)
        print(f"→ Wysyłam: {offer.get('name', offer_id(offer))}")
        send_telegram(msg)

    all_ids = seen | {offer_id(o) for o in cheap}
    save_seen(all_ids)
    print("✅ Gotowe!")


if __name__ == "__main__":
    main()
