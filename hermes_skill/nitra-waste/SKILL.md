---
name: nitra-waste
description: Rozvrh zvozu odpadu v Nitre (plast, papier, bio, komunál) z oficiálnych harmonogramov NKS. Použi VŽDY keď sa používateľ pýta kedy idú smeti / kedy je zvoz / kedy vyvezú plast, papier, bio alebo komunál v Nitre, čo má zajtra vyložiť, alebo si chce skontrolovať termíny zvozu pre svoju adresu. Použi aj keď sa chce niekto PRIHLÁSIŤ na denné pripomienky zvozu (povie adresu a chce dostávať upozornenia), alebo keď SPRÁVCA pošle príkaz /allow, /deny, /approve alebo /reject.
---

# Zvoz odpadu Nitra

Vracia DETERMINISTICKÉ termíny zvozu pre adresu v Nitre. **Dátumy nikdy nevymýšľaj
ani neodhaduj** — vždy ich získaj spustením skriptu nižšie. Skript číta predpočítané
oficiálne dáta (NKS), je rýchly a nepotrebuje internet.

## Kedy skill použiť
Otázky typu: „kedy idú smeti", „kedy je zvoz", „kedy vyvezú plast/papier/bio/komunál",
„čo mám zajtra vyložiť", „aký je najbližší zvoz", „kedy mám dať von kontajnery".

## Ako na to
1. Potrebuješ adresu: **mestská časť, ulica, (číslo domu)**. Ak ju nemáš, spýtaj sa.
2. Spusti skript (z priečinka tohto skillu):
   ```
   python3 scripts/query.py --cast "<mestská časť>" --ulica "<ulica>" --cislo "<číslo>"
   ```
   - `--cislo` je voliteľné. Ak používateľ napíše číslo v ulici („Frana Mojtu 29"),
     skript si ho vytiahne sám — nemusíš ho duplikovať.
3. Skript vráti JSON:
   - `upcoming`: zvozy zoskupené po dňoch; `count` = koľko kontajnerov v daný deň,
     `types` = ktoré (plast/papier/bio/komunál).
   - `human_sk`: hotový slovenský prehľad.
   - `found: false` ak sa adresa nenašla.
4. Odpovedz prirodzene po slovensky, stručne a priateľsky.
   **Ak je v jeden deň viac nádob, jasne povedz, že treba pristaviť N kontajnerov**
   (napr. „V pondelok 29.6. pristav 2 kontajnery: 🔵 papier + 🟤 bio").
5. Ak `found: false`, povedz to a popýtaj presnejšiu mestskú časť alebo ulicu.

## Prihlásenie na denné pripomienky
Keď používateľ chce **dostávať pripomienky** zvozu („chcem upozornenia", „prihlás
ma", „nech mi pošleš deň pred zvozom"):
1. Zisti adresu (mestská časť, ulica, číslo) — rovnako ako vyššie.
2. Spusti:
   ```
   python3 scripts/subscribe.py --name "<meno>" --cast "<časť>" \
       --ulica "<ulica>" --cislo "<číslo>" --chat-id <TELEGRAM_ID_ODOSIELATEĽA>
   ```
   - `--chat-id` je **Telegram ID toho, kto píše** (z kontextu správy), NIE admina.
3. Skript vráti JSON `{ok, message}`. **Prerozprávaj `message`** — nezapisuj nič
   sám, skript len odoslal žiadosť správcovi na schválenie.
4. Pripomienky NEvytváraj, neprogramuj ani nenavrhuj cron/skripty — o doručovanie
   sa stará nasadený `notify.py` (deň pred zvozom). Tvojou úlohou je len spustiť
   `subscribe.py`.

## Príkazy správcu (admin)
**POZOR:** príkazy chodia BEZ lomky (správy s `/` gateway zachytí a agentovi ich
nepošle). Ak správa znie ako `allow <číslo>`, `deny <číslo>`, `approve <číslo>`
alebo `reject <číslo>` (aj keby tam omylom bola lomka), spusti rovno:
```
python3 scripts/admin.py <allow|deny|approve|reject> <číslo>
```
- `allow <ID>` / `deny <ID>` — `<ID>` je Telegram ID z upozornenia „Pokus o kontakt".
- `approve <č>` / `reject <č>` — `<č>` je číslo žiadosti z „Žiadosť o pripomienky".
- **NIKDY sa nepýtaj používateľa na jeho Telegram ID** — netreba ho. Ochranu
  rieši allowlist (k botovi sa dostane len povolená rodina).
- Vždy iba spusti skript a **prerozprávaj jeho `message`**. Nič nedomýšľaj.

## Mestské časti Nitry
Staré mesto, Zobor, Chrenová, Klokočina, Janíkovce, Dolný Čermáň, Horný Čermáň,
Dražovce, Dolné Krškany, Horné Krškany, Párovské Háje, Mlynárce, Kynek.
- Pri samotnom „Čermáň" sa spýtaj, či **Dolný** alebo **Horný**.
- Pri **Zobore** je dôležitá ulica (zaraďuje sa do zón).
