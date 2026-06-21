# Sentinel — Rodinný AI agent · Detailný plán

> **Cieľ projektu:** modulárny rodinný AI agent. Prvý modul (skill): sledovanie
> zvozu odpadu v Nitre (NKS) + Telegram notifikácie + odpovedanie na otázky.
> Architektúra je navrhnutá tak, aby sa ďalšie rodinné funkcie pridávali ako
> samostatné „skills" bez zásahu do jadra.

---

## 1. Zhrnutie rozhodnutí

| Oblasť | Voľba | Poznámka |
|---|---|---|
| Hosting | Lacný cloud VPS | odporúčam **min. 8 GB RAM** kvôli lokálnemu LLM (viď §3) |
| Mozog (LLM) | Lokálny open-source model cez **Ollama** | Hermes / Llama / Qwen |
| Jazyk | Python 3.11+ | najlepšie nástroje na scraping, PDF, Telegram |
| Telegram | `python-telegram-bot` | notifikácie + Q&A |
| Úložisko | SQLite | lokálne, jednoduché, žiadny server navyše |
| Plánovač | APScheduler | denné úlohy (scraping, notifikácie) |
| PDF | `pdfplumber` (BEZ LLM, BEZ OCR) | čisto deterministické čítanie mriežky |

**Zdroje dát (2 PDF):**
1. **Triedený odpad** (plast/papier/bio) — `https://www.nks.sk/s/Harmonogram-TZ-2026-27.pdf`
   (zo stránky `/triedenie-odpadu-obcania-nitra`). Pevný kalendár pre **12 mestských
   častí**. Platnosť 1.4.2026–31.3.2027. ✅ parser HOTOVÝ (627 zvozov, 0 chýb).
2. **Komunál / čierny smetiak** — `https://www.nks.sk/s/Stanovitia-v-meste-k-1822026-komplet.pdf`
   (zo stránky `/harmonogram-zvozu`). **13 972 adries** s `deň + parita(párny/nepárny
   týždeň) + interval(1x7/1x14/2x7/3x7)`. Dátumy sa **dopočítavajú**. ✅ parser overený.

Sklo (zvony) = na zavolanie, BRKO/textil = mimo MVP.

---

## 2. Architektúra

```
                ┌──────────────────────────────────────────┐
                │                  SENTINEL                  │
                │                                            │
   cron ──────► │  CORE                                      │
                │   ├─ scheduler   (APScheduler)             │
                │   ├─ db          (SQLite)                  │
                │   ├─ llm         (Ollama klient)           │
                │   └─ telegram_bot                          │
                │                                            │
                │  SKILLS                                    │
                │   └─ waste_collection                      │
                │        ├─ scraper   (stiahni PDF — vzácne) │
                │        ├─ parser    (PDF → dáta + platnosť)│
                │        ├─ notifier  (deň vopred → Telegram)│
                │        └─ qa        (otázky nad dátami)    │
                └──────────────────────────────────────────┘
                         │                      ▲
                         ▼                      │
                   nks.sk PDF            Telegram používateľ
```

**Princíp:** CORE nevie nič o odpadoch. Každý skill sa registruje (cron úlohy +
Telegram príkazy). Pridať nový rodinný modul = pridať priečinok do `skills/`.

---

## 2.4 Onboarding + resolver adresy ⭐

Agent **neposiela nič, kým nemá adresu používateľa.** Pri prvom kontakte (`/start`)
sa opýta na **mestskú časť + ulicu (+ číslo domu)**. Z toho `resolver` vyrieši
všetky 4 typy odpadu naraz:

- **triedený (plast/papier/bio)** → mapovanie časť → jedna z 12 oblastí kalendára
- **komunál** → presná zhoda podľa ulice+čísla → `deň + parita + interval` → dopočet

Overené end-to-end: *„Staré mesto, Andreja Šulgana 4"* → vráti všetky 4 termíny.

**Známe medzery v mapovaní (doriešiť):**
- **Zobor** — triedený delí na Zobor 1–4 podľa ulice (strana 2 triedeného PDF má
  zoznam ulíc → zóna). Treba použiť toto mapovanie pre Zoboranov.
- **Čermáň** — komunál má jednu časť „Čermáň", ale triedený delí „Dolný Čermáň/Šúdol"
  vs „Horný Čermáň". Potreba mapovania na úrovni ulice alebo doplniť otázkou.
- **Viac nádob na jednom čísle** — niektoré adresy majú 2 komunál rozvrhy → agent
  sa spýta, ktorá nádoba je tvoja.

---

## 2.5 Logika plánovania (self-scheduling) ⭐

PDF má v sebe **obdobie platnosti** (napr. „oD 1.4.2026 dO 31.3.2027"). Agent ho
prečíta a **sám si naplánuje** ďalšiu kontrolu — nescrapuje denne.

```
1. Scrapni PDF teraz  →  parsuj  →  ulož dáta + valid_to (31.3.2027)
2. Naplánuj kontrolu na:  valid_to − 14 dní   (≈ 17.3.2027)
3. Keď príde ten deň → skús stiahnuť nové PDF (obdobie 2027–28).
      ├─ nájdené & zmenené → parsuj, ulož, naplánuj ďalšiu kontrolu
      └─ ešte nezverejnené → skús znova o pár dní (a upozorni v Telegrame)
```

**Dve nezávislé časové slučky:**
- **Scraping/parsing** — vzácne, riadené `valid_to` z PDF (raz teraz, potom ~1×/rok).
- **Notifikácie** — denne; čítajú len z databázy, nič nescrapujú.

**Voliteľná poistka:** veľmi lacná kontrola hashu PDF napr. 1×/mesiac pre prípad,
že NKS zverejní opravu mimo plánovaného cyklu (len HTTP request, bez LLM).

---

## 3. ⚠️ Lokálny LLM na VPS — kľúčové rozhodnutie

Najlacnejšie VPS (2–4 GB RAM, bez GPU) **nestačia** na použiteľný LLM.
Odporúčania podľa rozpočtu:

| Model | RAM (Q4) | Slovenčina | VPS náklad | Vhodnosť |
|---|---|---|---|---|
| Llama 3.2 **3B** | ~3–4 GB | slabá | ~6 €/mes | núdzovo, krátke odpovede |
| **Qwen 2.5 7B** | ~6–8 GB | **dobrá** | ~15 €/mes | ⭐ odporúčam |
| Hermes 3 (Llama 3.1 8B) | ~7–8 GB | priemerná | ~15 €/mes | dobré |
| Gemma 2 9B | ~8–9 GB | dobrá | ~20 €/mes | dobré |

**Dôležité:** parsovanie PDF je jednorazové pri zmene harmonogramu — tam kvalita
modelu rozhoduje. Ak by lokálny model robil chyby v dátumoch, je to riziko
(zmeškaný zvoz). **Bezpečnostná poistka:** parsovanie necháme prejsť aj
validáciou pravidlami (regex na dátumy + kontrola rozsahu platnosti), nie len
LLM. LLM je len na pochopenie štruktúry, finálne dátumy validujeme kódom.

> **Otvorená otázka pre teba:** akceptuješ VPS ~15 €/mes (Qwen 2.5 7B), alebo
> trváš na najlacnejšom (~6 €) s 3B modelom a obmedzenejšou kvalitou? Viem
> navrhnúť aj hybrid: parsovanie raz za čas cez kvalitnejší cloud open-model
> (Groq/Together, pár centov), Q&A lokálne.

---

## 4. Štruktúra projektu

```
Sentinel/
├── README.md
├── PLAN.md                  # tento súbor
├── pyproject.toml           # závislosti
├── .env.example             # TELEGRAM_TOKEN, OLLAMA_HOST, ...
├── config.py                # načítanie konfigurácie
├── main.py                  # štart: bot + scheduler
├── sentinel/
│   ├── core/
│   │   ├── db.py            # SQLite schéma + prístup
│   │   ├── scheduler.py     # registrácia cron úloh
│   │   ├── llm.py           # Ollama wrapper (+ fallback)
│   │   └── telegram_bot.py  # bootstrap bota, routing príkazov
│   └── skills/
│       └── waste_collection/
│           ├── scraper.py
│           ├── parser.py
│           ├── notifier.py
│           └── qa.py
├── data/
│   ├── sentinel.db
│   └── pdfs/                # archív stiahnutých PDF (na audit)
└── tests/
```

---

## 5. Dátový model (SQLite)

```sql
-- verzie stiahnutého PDF (detekcia zmien + self-scheduling)
pdf_versions(
  id, url, file_hash, downloaded_at, parsed_at,
  valid_from, valid_to,   -- prečítané z PDF
  next_check_date,        -- valid_to − 14 dní → kedy znova kontrolovať
  status                  -- 'new' | 'parsed' | 'failed'
)

-- vyparsovaný harmonogram
collection(
  id, waste_type,        -- 'plast'|'papier'|'sklo'|'bio'|'brko'|'textil'
  household_type,        -- 'rodinny_dom' | 'bytovka'
  area,                  -- mestská časť / okrsok (ak je v PDF)
  collection_date,       -- konkrétny dátum zvozu
  valid_from, valid_to,
  source_hash            -- z ktorého PDF pochádza
)

-- odberatelia notifikácií
subscribers(
  chat_id, household_type, area,
  notify_time,           -- napr. '18:00'
  active
)

-- log odoslaných notifikácií (anti-duplicita)
notifications_log(id, chat_id, collection_date, waste_type, sent_at)
```

---

## 6. Telegram príkazy

| Príkaz | Funkcia |
|---|---|
| `/start` | registrácia, výber typu domácnosti + mestskej časti |
| `/dnes` `/zajtra` | čo sa zváža dnes / zajtra |
| `/tyzden` | prehľad na týždeň |
| `/dalsi plast` | najbližší termín konkrétneho typu |
| voľná otázka | LLM odpovie nad dátami z DB (napr. „kedy idú smeti?") |
| `/nastav 18:00` | čas dennej notifikácie |

Automaticky: deň vopred o nastavenom čase → „🟡 Zajtra zvoz plastov".

---

## 7. Fázy implementácie

**Fáza 0 — kostra (½ dňa)**
- projekt, závislosti, `.env`, `config.py`
- SQLite schéma, `db.py`
- Telegram bot, ktorý odpovie na `/start` (echo) → overenie, že beží

**Fáza 1 — scraper + detekcia zmien**
- nájdi odkaz na PDF na stránke (dynamicky, nie natvrdo URL), stiahni, ulož hash
- ak sa hash zmenil → označ `new`, archivuj PDF do `data/pdfs/`

**Fáza 2 — parser PDF → DB + self-scheduling**
- `pdfplumber` vytiahne text/tabuľky
- LLM ich preloží do štruktúry `{typ, domácnosť, dátum}` + **prečíta obdobie platnosti**
- **validácia pravidlami** (regex dátumov, kontrola rozsahu platnosti)
- zápis do `collection`, ulož `valid_to` a nastav `next_check_date = valid_to − 14 dní`
- naplánuj ďalšiu kontrolu na `next_check_date` (žiadne denné scrapovanie)

**Fáza 3 — notifikátor**
- denne o `notify_time` nájdi zajtrajšie zvozy pre odberateľa
- pošli Telegram správu, zapíš do `notifications_log` (žiadne duplikáty)

**Fáza 4 — Q&A**
- na voľnú otázku → LLM dostane relevantné riadky z DB ako kontext → odpoveď
- bezpečné: LLM nehádže dátumy, len formuluje nad reálnymi dátami z DB

**Fáza 5 — nasadenie na VPS**
- Ollama + zvolený model
- `systemd` služby (bot + scheduler), reštart pri páde
- logovanie, jednoduchý health-check

**Fáza 6 — rozšíriteľnosť**
- dokumentovať „ako pridať nový skill"
- ďalšie rodinné moduly (mestské kontajnery, pripomienky, ...)

---

## 8. Riziká a poistky

| Riziko | Poistka |
|---|---|
| LLM zle prečíta dátum z PDF | validácia pravidlami + log + (voliteľne) potvrdenie pred odoslaním |
| NKS zmení URL/formát PDF | scraper hľadá odkaz na PDF dynamicky na stránke, alert pri zlyhaní |
| Malý model slabý v SK | voľba Qwen 2.5 7B / hybrid parsovanie |
| VPS výpadok | systemd auto-restart, denný health-check do Telegramu |
| Zmeškaná notifikácia | idempotentný notifier + log |

---

## 9. Čo potrebujem od teba pred kódením

1. **Rozpočet VPS / model** (viď §3): ~6 € (3B) vs. ~15 € (Qwen 7B) vs. hybrid?
2. **Telegram:** je to pre celú rodinu (skupina) alebo súkromné chaty? Treba viac
   odberateľov s rôznymi mestskými časťami?
3. **Typ domácnosti:** bývate v rodinnom dome alebo bytovke (kvôli prvému MVP)?
4. Máš už **Telegram bot token** (z @BotFather), alebo ho vytvoríme?
```
