"""Zdieľané fixtures pre testy. Resolver (číta obe PDF) sa načíta raz za session."""
from __future__ import annotations

import datetime

import pytest

import config
from sentinel.core.db import Database, WasteSubscription
from sentinel.skills.waste_collection.resolver import WasteResolver
from sentinel.skills.waste_collection.service import WasteService

# pevný „dnes" pre deterministické testy (v rámci platnosti harmonogramu)
TODAY = datetime.date(2026, 6, 7)


@pytest.fixture(scope="session")
def resolver() -> WasteResolver:
    return WasteResolver(config.TRIEDENY_PDF, config.KOMUNAL_PDF)


@pytest.fixture
def service_with_db(resolver):
    """WasteService nad in-memory DB s jedným odberateľom (8.mája 5, Staré mesto)."""
    db = Database(":memory:")
    db.upsert_subscription(WasteSubscription(
        user_id=42, cast="Staré mesto", ulica="8.mája", cislo="5",
        komunal_desc=None))
    return WasteService(resolver, subscriptions=db), db
