# 🏖️ Lastminuter Bot — Telegram

Bot monitoruje lastminuter.pl i wysyła powiadomienie na Telegrama gdy pojawi się oferta poniżej zadanej ceny.

---

## 🚀 Konfiguracja (15 minut)

### Krok 1 — Utwórz bota Telegram

1. Otwórz Telegram i napisz do **@BotFather**
2. Wyślij `/newbot`
3. Podaj nazwę bota (np. `Lastminuter Alert`)
4. Podaj username (np. `lastminuter_alert_bot`)
5. Skopiuj **token** — wygląda tak: `123456789:ABCdef...`

### Krok 2 — Znajdź swój Chat ID

1. Napisz do bota (wyślij mu cokolwiek, np. `/start`)
2. Wejdź w przeglądarkę na URL:
   ```
   https://api.telegram.org/bot<TWÓJ_TOKEN>/getUpdates
   ```
3. Znajdź pole `"chat": {"id": 123456789}` — to jest Twój **Chat ID**

### Krok 3 — Utwórz repozytorium GitHub

1. Zaloguj się na [github.com](https://github.com)
2. Kliknij **New repository**
3. Nazwa: `lastminuter-bot`, ustaw na **Private**
4. Kliknij **Create repository**
5. Wgraj wszystkie pliki z tego folderu do repozytorium

### Krok 4 — Dodaj sekrety w GitHub

1. Wejdź w repozytorium → **Settings** → **Secrets and variables** → **Actions**
2. Kliknij **New repository secret** i dodaj:
   - `TELEGRAM_TOKEN` → token z kroku 1
   - `TELEGRAM_CHAT_ID` → chat ID z kroku 2

### Krok 5 — Włącz GitHub Actions

1. Wejdź w zakładkę **Actions** w repozytorium
2. Jeśli Actions jest wyłączone, kliknij "Enable"
3. Bot uruchomi się automatycznie co 5 minut!

---

## ⚠️ Ważna uwaga — API strony

Lastminuter.pl to aplikacja React (SPA) — dane ładowane są dynamicznie przez JavaScript.

**Jeśli bot nie znajduje ofert**, musisz znaleźć endpoint API:

1. Otwórz lastminuter.pl w Chrome
2. Naciśnij `F12` → zakładka **Network**
3. Odfiltruj po **XHR** lub **Fetch**
4. Przewiń stronę z ofertami
5. Znajdź request do API (np. `api.lastminuter.pl/...`)
6. Skopiuj URL i dodaj go na początku listy `API_URLS` w `scraper.py`

---

## 🔧 Zmiana limitu ceny

W repozytorium → Settings → Variables → New variable:
- Nazwa: `MAX_PRICE`
- Wartość: np. `1200`

---

## 📊 Jak to działa

```
Co 5 minut:
  GitHub Actions uruchamia scraper.py
    ↓
  Pobiera oferty z lastminuter.pl API
    ↓
  Filtruje oferty poniżej MAX_PRICE zł
    ↓
  Porównuje z seen_offers.json (pamięć bota)
    ↓
  Wysyła Telegram alert dla nowych ofert
    ↓
  Zapisuje nowe ID do seen_offers.json
```

---

## 💡 Wskazówki

- GitHub Actions darmowy plan: 2000 minut/miesiąc → co 5 minut = ~8640 min/miesiąc (potrzebne konto Pro lub zmiana na co 15 min)
- Darmowy plan GitHub pozwala na **co 5 minut** dla publicznych repozytoriów i ma limit minut dla prywatnych
- Alternatywnie użyj **co 15 minut** — wystarczy zmienić cron na `*/15 * * * *`
