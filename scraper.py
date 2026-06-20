import requests
import json
import os
import hashlib
from datetime import datetime

# === KONFIGURACJA ===
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
MAX_PRICE = int(os.environ.get("MAX_PRICE", 1800))
SEEN_FILE = "seen_offers.json"

# --- FILTRY ---
# Kierunki do WYKLUCZENIA (małe litery, bez polskich znaków problem nie istnieje bo porównujemy dokładnie jak w API)
EXCLUDED_COUNTRIES = ["Tunezja", "Bułgaria", "Egipt"]

# Akceptowane lotniska wylotu
ALLOWED_AIRPORTS = ["Warszawa", "Łódź", "Lublin"]

# Minimalna liczba dni
MIN_DAYS = 7

# Akceptowane touroperatorzy (pole 'zrodlo')
ALLOWED_SOURCES = ["itaka.pl"]

# Wyżywienie: odrzucamy oferty z mniej niż 2 posiłkami.
# Słowa kluczowe oznaczające ZA MAŁO posiłków (odrzucamy jeśli board zawiera jedno z nich
# i NIE zawiera żadnego z słów oznaczających 2+ posiłki)
BOARD_REJECT_KEYWORDS = ["własne", "śniadania"]  # uwaga: "śniadania" samo = 1 posiłek
BOARD_ACCEPT_KEYWORDS = ["dwa posiłki", "all inclusive", "pełne wyżywienie",
                          "trzy posiłki", "full board", "half board", "hb", "fb", "ai"]

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
        print(f"Klucze w odpowiedzi: {list(data.keys())}")
    return []


def get_hotel_name(offer):
    """Pole 'hotel' jest stringiem zawierającym JSON, np. '{"name": "Sunny Day...", "img": "..."}'"""
    raw = offer.get("hotel", "")
    if isinstance(raw, dict):
        return raw.get("name", "Hotel")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed.get("name", raw)
        except Exception:
            return raw
    return "Hotel"


def get_price(offer):
    val = offer.get("pln")
    if val is None:
        return None
    try:
        return float(str(val).replace(",", ".").replace("zł", "").replace(" ", "").strip())
    except Exception:
        return None


def offer_id(offer):
    for field in ["id", "link"]:
        if field in offer:
            return str(offer[field])
    return hashlib.md5(json.dumps(offer, sort_keys=True).encode()).hexdigest()[:12]


def passes_filters(offer):
    """Sprawdza wszystkie kryteria filtrowania. Zwraca (True/False, powód_jeśli_odrzucone)."""

    # Kraj — wykluczenie
    country = offer.get("country", "")
    if country in EXCLUDED_COUNTRIES:
        return False, f"wykluczony kraj: {country}"

    # Lotnisko wylotu
    airport = offer.get("airport", "")
    if ALLOWED_AIRPORTS and airport not in ALLOWED_AIRPORTS:
        return False, f"lotnisko nie na liście: {airport}"

    # Minimalna liczba dni
    days = offer.get("days")
    try:
        days_num = int(days)
    except (TypeError, ValueError):
        days_num = None
    if days_num is not None and days_num < MIN_DAYS:
        return False, f"za mało dni: {days_num}"

    # Touroperator
    source = offer.get("zrodlo", "")
    if ALLOWED_SOURCES and source not in ALLOWED_SOURCES:
        return False, f"touroperator nie na liście: {source}"

    # Wyżywienie — minimum 2 posiłki
    board = (offer.get("board") or "").lower()
    has_accept_kw = any(kw in board for kw in BOARD_ACCEPT_KEYWORDS)
    has_reject_kw = any(kw in board for kw in BOARD_REJECT_KEYWORDS)
    if has_reject_kw and not has_accept_kw:
        return False, f"za mało posiłków: {board}"
    if not board:
        return False, "brak informacji o wyżywieniu"

    # Cena
    price = get_price(offer)
    if price is None or price >= MAX_PRICE:
        return False, f"cena: {price}"

    return True, None


def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
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
    name = get_hotel_name(offer)
    country = offer.get("country", "")
    city = offer.get("city", "")
    price = get_price(offer)
    link = offer.get("link", "")
    date = offer.get("date", "")
    days = offer.get("days", "")
    airport = offer.get("airport", "")
    board = offer.get("board", "")
    stars = offer.get("stars", "")
    source = offer.get("zrodlo", "")

    msg = f"🔥 <b>Nowa oferta poniżej {MAX_PRICE} zł!</b>\n\n"
    msg += f"🏨 <b>{name}</b>"
    if stars:
        msg += " " + "⭐" * int(stars) if str(stars).isdigit() else ""
    if country or city:
        msg += f" — {city or ''}{', ' if city and country else ''}{country or ''}"
    msg += "\n"
    if price:
        msg += f"💰 Cena: <b>{price:.0f} zł</b> / os.\n"
    if date:
        msg += f"✈️ Wylot: {date}"
        if airport:
            msg += f" z {airport}"
        msg += "\n"
    if days:
        msg += f"🌙 Dni: {days}\n"
    if board:
        msg += f"🍽️ Wyżywienie: {board}\n"
    if source:
        msg += f"🧳 Touroperator: {source}\n"
    if link:
        url = link if link.startswith("http") else "https://lastminuter.pl" + link
        msg += f"\n🔗 {url}"
    msg += f"\n\n⏰ {datetime.now().strftime('%H:%M:%S')}"
    return msg


def main():
    print(f"=== Lastminuter Bot — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    print(f"Filtr ceny: poniżej {MAX_PRICE} zł")
    print(f"Wykluczone kraje: {EXCLUDED_COUNTRIES}")
    print(f"Lotniska: {ALLOWED_AIRPORTS}")
    print(f"Min. dni: {MIN_DAYS}")
    print(f"Touroperatorzy: {ALLOWED_SOURCES}")

    data = fetch_offers()
    offers = extract_offers(data)
    print(f"📦 Pobrano {len(offers)} ofert")

    if not offers:
        print("⚠️ Brak ofert — sprawdź strukturę odpowiedzi powyżej")
        return

    # Filtrowanie
    passing = []
    for o in offers:
        ok, reason = passes_filters(o)
        if ok:
            passing.append(o)
    print(f"✅ Oferty spełniające kryteria: {len(passing)}")

    # Sprawdź które są nowe
    seen = load_seen()
    new_offers = [o for o in passing if offer_id(o) not in seen]
    print(f"🆕 Nowe oferty: {len(new_offers)}")

    for offer in new_offers:
        msg = format_offer(offer)
        print(f"→ Wysyłam: {get_hotel_name(offer)}")
        send_telegram(msg)

    all_ids = seen | {offer_id(o) for o in passing}
    save_seen(all_ids)
    print("✅ Gotowe!")


if __name__ == "__main__":
    main()
