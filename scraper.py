import requests
import json
import os
import re
import hashlib
from datetime import datetime

# === KONFIGURACJA ===
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
TELEGRAM_CHAT_ID_2 = "8938826689"  # Twoje Chat ID
MAX_PRICE = int(os.environ.get("MAX_PRICE", 1800))
TEST_MODE = os.environ.get("TEST_MODE", "false").lower() == "false"
SEEN_FILE = "seen_offers.json"

# --- FILTRY ---
EXCLUDED_COUNTRIES = ["tunezja", "bułgaria", "egipt"]
ALLOWED_AIRPORTS = []  # wyłączone - tagi lotnisk bywają niekompletne
MIN_DAYS = 6
REQUIRE_ITAKA = False
BOARD_ACCEPT_KEYWORDS = ["dwa posiłki", "all inclusive", "pełne wyżywienie",
                          "trzy posiłki", "full board", "half board"]
BOARD_REJECT_KEYWORDS = ["własne", "śniadania"]

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


def fetch_data():
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


def get_tag_names(deal):
    tags = deal.get("tags", [])
    return [t.get("name", "").lower() for t in tags if isinstance(t, dict)]


def get_tag_slugs(deal):
    tags = deal.get("tags", [])
    return [t.get("slug", "").lower() for t in tags if isinstance(t, dict)]


def get_price(deal):
    val = deal.get("cena")
    if val is None:
        return None
    try:
        return float(str(val).replace(",", ".").replace("zł", "").replace(" ", "").strip())
    except Exception:
        return None


def get_min_days(deal):
    for slug in get_tag_slugs(deal):
        m = re.match(r"(\d+)-(\d+)-dni", slug)
        if m:
            return int(m.group(1))
        m2 = re.match(r"(\d+)-dni", slug)
        if m2:
            return int(m2.group(1))
    return None


def get_airports(deal):
    """Wyciąga lotniska z tagów (typ 'source')."""
    airports = []
    for t in deal.get("tags", []):
        if isinstance(t, dict) and t.get("icon") == "source":
            airports.append(t.get("name", ""))
    return airports


def mentions_itaka(deal):
    haystack = " ".join([
        deal.get("title", ""),
        deal.get("content", ""),
        deal.get("excerpt", ""),
        deal.get("cta_link", ""),
    ]).lower()
    return "itaka" in haystack


def offer_id(deal):
    return str(deal.get("id") or deal.get("link") or hashlib.md5(json.dumps(deal, sort_keys=True).encode()).hexdigest()[:12])


def passes_filters(deal):
    tag_names = get_tag_names(deal)
    tag_text = " ".join(tag_names)

    # Kraj - wykluczenie
    for excluded in EXCLUDED_COUNTRIES:
        if excluded in tag_text:
            return False, f"wykluczony kraj (tag): {excluded}"

    # Lotnisko - wyłączone, ale zbieramy dane do wyświetlenia
    if ALLOWED_AIRPORTS:
        has_allowed_airport = any(a in tag_names for a in ALLOWED_AIRPORTS)
        if not has_allowed_airport:
            return False, f"brak dozwolonego lotniska w tagach: {tag_names}"

    # Min. dni
    min_days = get_min_days(deal)
    if min_days is not None and min_days < MIN_DAYS:
        return False, f"za mało dni: {min_days}"

    # Itaka
    if REQUIRE_ITAKA and not mentions_itaka(deal):
        return False, "nie wzmiankuje Itaki"

    # Wyżywienie - minimum 2 posiłki
    has_accept = any(kw in tag_text for kw in BOARD_ACCEPT_KEYWORDS)
    has_reject = any(kw in tag_text for kw in BOARD_REJECT_KEYWORDS)
    if has_reject and not has_accept:
        return False, f"za mało posiłków: {tag_text}"
    if not has_accept and not has_reject:
        # brak info o wyżywieniu - przepuszczamy żeby nie pomijać dobrych ofert
        pass

    # Cena
    price = get_price(deal)
    if price is None or price >= MAX_PRICE:
        return False, f"cena: {price}"

    # Czy oferta jeszcze aktualna
    if deal.get("expired"):
        return False, "wygasła"

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


def send_telegram(message, chat_id):
    if not TELEGRAM_TOKEN or not chat_id:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print(f"✅ Telegram ({chat_id}): wiadomość wysłana")
        else:
            print(f"❌ Telegram błąd ({chat_id}): {resp.text}")
    except Exception as e:
        print(f"❌ Telegram wyjątek ({chat_id}): {e}")


def format_deal(deal):
    title = deal.get("title", "Oferta")
    price = get_price(deal)
    link = deal.get("link", "")
    cta_link = deal.get("cta_link", "")
    excerpt = deal.get("excerpt", "")
    tag_names = [t.get("name") for t in deal.get("tags", []) if isinstance(t, dict)]
    date_ago = deal.get("date_ago", "")
    airports = get_airports(deal)

    msg = f"🔥 <b>{title}</b>\n\n"
    if excerpt:
        msg += f"{excerpt}\n\n"
    if price:
        msg += f"💰 Cena: <b>{price:.0f} zł</b>\n"
    if airports:
        msg += f"✈️ Lotniska: {', '.join(airports)}\n"
    if tag_names:
        msg += f"🏷️ {', '.join(tag_names)}\n"
    if date_ago:
        msg += f"🕐 Dodano: {date_ago}\n"

    full_link = ""
    if link:
        full_link = link if link.startswith("http") else "https://lastminuter.pl" + link
    msg += f"\n🔗 {full_link or cta_link}"
    msg += f"\n\n⏰ Wysłano: {datetime.now().strftime('%H:%M:%S')}"
    return msg


def main():
    print(f"=== Lastminuter Bot — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    print(f"Filtr ceny: poniżej {MAX_PRICE} zł")
    print(f"Wykluczone kraje: {EXCLUDED_COUNTRIES}")
    print(f"Lotniska: {ALLOWED_AIRPORTS or 'wszystkie (wyświetlane w wiadomości)'}")
    print(f"Min. dni: {MIN_DAYS}")
    print(f"Wymagana Itaka: {REQUIRE_ITAKA}")

    if TEST_MODE:
        msg = "✅ <b>Bot działa poprawnie!</b>\n\nBuongiorno Alessandra! Czy jesteś zadowolona z usług robota?\n\n⏰ " + datetime.now().strftime('%H:%M:%S')
        print("🧪 Tryb testowy — wysyłam wiadomość testową")
        send_telegram(msg, TELEGRAM_CHAT_ID)
        send_telegram(msg, TELEGRAM_CHAT_ID_2)
        return

    data = fetch_data()
    if data is None:
        print("⚠️ Brak danych z API")
        return

    deals = data.get("deals", [])
    print(f"📦 Pobrano {len(deals)} okazji ('deals')")

    if not deals:
        print("⚠️ Brak okazji do przetworzenia")
        return

    passing = []
    for d in deals:
        ok, reason = passes_filters(d)
        if ok:
            passing.append(d)
            print(f"✅ {d.get('title', '')[:50]}")
        else:
            print(f"❌ {d.get('title', '')[:50]} → {reason}")
    print(f"✅ Okazje spełniające kryteria: {len(passing)}")

    seen = load_seen()
    new_deals = [d for d in passing if offer_id(d) not in seen]
    print(f"🆕 Nowe okazje: {len(new_deals)}")

    for deal in new_deals:
        msg = format_deal(deal)
        print(f"→ Wysyłam: {deal.get('title', '')[:50]}")
        send_telegram(msg, TELEGRAM_CHAT_ID)
        send_telegram(msg, TELEGRAM_CHAT_ID_2)

    all_ids = seen | {offer_id(d) for d in passing}
    save_seen(all_ids)
    print("✅ Gotowe!")


if __name__ == "__main__":
    main()
