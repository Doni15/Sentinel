"""
Router správ (Sentinel core). Rozhoduje, ktorý skill spracuje voľnú správu
používateľa a vráti odpoveď.

Teraz je registrovaný jeden skill (waste_collection). Sem sa neskôr napojí lokálny
LLM (Ollama), ktorý z textu vyberie skill + zámer. LLM ale NIKDY netvorí dáta —
odpoveď vždy vracia skill nad reálnymi dátami.
"""
from __future__ import annotations

from typing import Protocol


class WasteSkill(Protocol):
    def answer_waste_query(self, user_profile, text: str) -> str: ...


class Router:
    def __init__(self, waste_service: WasteSkill):
        self.waste = waste_service

    def handle(self, user_profile, text: str) -> str:
        """Vráti textovú odpoveď pre daného používateľa.

        ⚠️ DOČASNÉ: každú voľnú správu posiela do waste skillu. Akceptovateľné, kým
        je registrovaný jediný skill.

        TODO(ďalšia fáza): keď pribudnú ďalšie skilly, doplniť intent routing —
        buď keyword pravidlá, alebo lokálny LLM klasifikátor, ktorý z textu vyberie
        SKILL + ZÁMER. LLM smie len klasifikovať/vybrať skill; NIKDY nesmie generovať
        dátumy ani fakty — tie vždy vracia skill nad reálnymi dátami (resolver).
        """
        return self.waste.answer_waste_query(user_profile, text)
