---
name: nitra-waste
description: Rozvrh zvozu odpadu v Nitre (plast, papier, bio, komunál) z oficiálnych harmonogramov NKS. Použi VŽDY keď sa používateľ pýta kedy idú smeti / kedy je zvoz / kedy vyvezú plast, papier, bio alebo komunál v Nitre, čo má zajtra vyložiť, alebo si chce skontrolovať termíny zvozu pre svoju adresu.
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

## Mestské časti Nitry
Staré mesto, Zobor, Chrenová, Klokočina, Janíkovce, Dolný Čermáň, Horný Čermáň,
Dražovce, Dolné Krškany, Horné Krškany, Párovské Háje, Mlynárce, Kynek.
- Pri samotnom „Čermáň" sa spýtaj, či **Dolný** alebo **Horný**.
- Pri **Zobore** je dôležitá ulica (zaraďuje sa do zón).
