"""
Telegram adapter (Sentinel core). Sentinel vlastní bota, používateľov a routing.
Onboarding zozbiera adresu a uloží ju do `waste_subscriptions`. Dopyty a voľné
otázky deleguje na waste service / router. Notifikácie posiela scheduler+dispatcher.
"""
from __future__ import annotations

import datetime
import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, ApplicationHandlerStop, CallbackQueryHandler, CommandHandler,
    ContextTypes, ConversationHandler, MessageHandler, TypeHandler, filters,
)

from ..skills.waste_collection.notifications import (
    fmt_bins, fmt_date, group_by_date, pluralize_kontajner, relative,
)
from ..skills.waste_collection.normalize import split_street_number
from ..skills.waste_collection.service import WasteService
from . import timeutil
from .access import AccessGuard
from .db import Database, WasteSubscription
from .dispatcher import NotificationDispatcher
from .logging_setup import configure_logging
from .router import Router
from .scheduler import register_daily_notifications

# Bezpečné logovanie: stíši httpx (logoval by token v URL) + redaguje tokeny.
configure_logging(logging.INFO)
log = logging.getLogger("sentinel.telegram")

CAST, ULICA, CISLO, KOMUNAL_PICK = range(4)


def _db(ctx) -> Database: return ctx.application.bot_data["db"]
def _svc(ctx) -> WasteService: return ctx.application.bot_data["waste"]
def _router(ctx) -> Router: return ctx.application.bot_data["router"]


# ---------- onboarding ----------
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    _db(ctx).ensure_profile(update.effective_chat.id,
                            update.effective_user.full_name)
    await update.message.reply_text(
        "👋 Ahoj, som *Sentinel* — tvoj smetiarsky špión. 🕵️\n"
        "Postrážim, kedy idú smeti, nech ťa už nikdy nezastihne auto "
        "s plným košom doma. 🚛💨\n\n"
        "Najprv potrebujem tvoju adresu, inak ti neviem nič posielať.\n\n"
        "Napíš *mestskú časť* (napr. Staré mesto, Zobor, Janíkovce, Chrenová, "
        "Klokočina, Dolný Čermáň ...):", parse_mode="Markdown")
    return CAST


async def got_cast(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["cast"] = update.message.text.strip()
    await update.message.reply_text("📍 A teraz *ulicu*:", parse_mode="Markdown")
    return ULICA


async def got_ulica(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    # používateľ často napíše ulicu aj s číslom („Frana Mojtu 29") → oddelíme ho,
    # aby sa adresa nezdvojila a aby sedel komunál (matchuje sa na čistú ulicu)
    street, num = split_street_number(update.message.text.strip())
    ctx.user_data["ulica"] = street
    ctx.user_data["cislo_from_street"] = num
    await update.message.reply_text(
        "🔢 *Číslo domu* (alebo „-“ ak nevieš):", parse_mode="Markdown")
    return CISLO


async def got_cislo(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    c = update.message.text.strip()
    if c in ("-", ""):
        # nezadal číslo → použijeme to, čo prípadne bolo v názve ulice
        c = ctx.user_data.get("cislo_from_street")
    ctx.user_data["cislo"] = c or None
    return await _resolve_and_save(update, ctx)


async def _resolve_and_save(update, ctx) -> int:
    svc = _svc(ctx)
    cast, ulica, cislo = (ctx.user_data["cast"], ctx.user_data["ulica"],
                          ctx.user_data["cislo"])
    res = svc.resolve_address(cast, ulica, cislo)

    if len(res.komunal) > 1:
        ctx.user_data["komunal_opts"] = [k["popis"] for k in res.komunal]
        buttons = [[InlineKeyboardButton(k["popis"], callback_data=f"kbin:{i}")]
                   for i, k in enumerate(res.komunal)]
        await update.message.reply_text(
            "⚫ Na tvojej adrese je viac nádob na komunál. Vyber tú svoju:",
            reply_markup=InlineKeyboardMarkup(buttons))
        return KOMUNAL_PICK

    if not res.triedeny_area and not res.komunal:
        warn = "\n".join("⚠️ " + w for w in res.warnings)
        await update.message.reply_text(
            "Nenašiel som túto adresu. Skús to znova cez /start.\n" + warn)
        return ConversationHandler.END

    return await _finalize(update, ctx, res,
                           res.komunal[0]["popis"] if res.komunal else None)


async def picked_bin(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    desc = ctx.user_data["komunal_opts"][int(q.data.split(":")[1])]
    res = _svc(ctx).resolve_address(ctx.user_data["cast"], ctx.user_data["ulica"],
                                    ctx.user_data["cislo"])
    return await _finalize(update, ctx, res, desc, query=q)


async def _finalize(update, ctx, res, komunal_desc, query=None) -> int:
    chat_id = query.message.chat_id if query else update.message.chat_id
    _db(ctx).upsert_subscription(WasteSubscription(
        user_id=chat_id, cast=res.cast, ulica=res.ulica, cislo=res.cislo,
        komunal_desc=komunal_desc))
    today = timeutil.today()
    lines = [f"✅ Hotovo! Sledujem *{res.ulica} {res.cislo or ''}, {res.cast}*.",
             "\nNajbližšie zvozy:"]
    for wt in ("plast", "papier", "bio"):
        d = res.triedeny.get(wt)
        ic = {"plast": "🟡", "papier": "🔵", "bio": "🟤"}[wt]
        if d:
            lines.append(f"{ic} {wt}: {fmt_date(d)} ({relative(d, today)})")
    for k in res.komunal:
        if komunal_desc and k["popis"] != komunal_desc:
            continue
        if k["next"]:
            lines.append(f"⚫ komunál: {fmt_date(k['next'])} "
                         f"({relative(k['next'], today)})")
    lines.append("\nDeň pred zvozom ti pošlem pripomienku. "
                 "Skús /dnes, /zajtra, /tyzden alebo sa pýtaj.")
    text = "\n".join(lines)
    if query:
        await query.edit_message_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")
    return ConversationHandler.END


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Zrušené. Kedykoľvek napíš /start.")
    return ConversationHandler.END


# ---------- dopyty ----------
async def _need_start(update):
    await update.message.reply_text("Najprv mi povedz adresu cez /start. 🙂")


async def _window(update, ctx, days, title):
    today = timeutil.today()
    sub = _db(ctx).get_subscription(update.message.chat_id)
    if not sub:
        return await _need_start(update)
    events = _svc(ctx).events_for_address(
        sub.cast, sub.ulica, sub.cislo, today,
        today + datetime.timedelta(days=days), sub.komunal_desc)
    if not events:
        return await update.message.reply_text(f"{title}: žiadny zvoz. 🎉")
    lines = [f"*{title}*"]
    for d, evs in group_by_date(events):
        kus = f"  ({pluralize_kontajner(len(evs))})" if len(evs) > 1 else ""
        lines.append(f"{fmt_date(d)} ({relative(d, today)}): {fmt_bins(evs)}{kus}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_dnes(update, ctx): await _window(update, ctx, 0, "Dnes")
async def cmd_tyzden(update, ctx): await _window(update, ctx, 7, "Najbližších 7 dní")


async def cmd_zajtra(update, ctx):
    today = timeutil.today()
    sub = _db(ctx).get_subscription(update.message.chat_id)
    if not sub:
        return await _need_start(update)
    t = today + datetime.timedelta(days=1)
    events = _svc(ctx).events_for_address(sub.cast, sub.ulica, sub.cislo, t, t,
                                          sub.komunal_desc)
    if not events:
        return await update.message.reply_text("Zajtra: žiadny zvoz. 🎉")
    n = len(events)
    kus = f"  ({pluralize_kontajner(n)})" if n > 1 else ""
    await update.message.reply_text(
        f"*Zajtra* ({fmt_date(t)}):\n{fmt_bins(events)}{kus}",
        parse_mode="Markdown")


async def cmd_help(update, ctx):
    await update.message.reply_text(
        "Príkazy:\n/dnes — dnešný zvoz\n/zajtra — zajtrajší zvoz\n"
        "/tyzden — 7 dní\n/zmen — zmeniť adresu\n/stop — prestať\n\n"
        "Alebo sa spýtaj: „kedy plast?“, „komunál“, „papier“ ...")


async def cmd_stop(update, ctx):
    _db(ctx).delete_waste_data(update.message.chat_id)
    await update.message.reply_text(
        "Odhlásené zo zvozu. Adresa aj história notifikácií zmazané. "
        "Profil Sentinela ostáva. Návrat cez /start.")


async def free_text(update, ctx):
    sub = _db(ctx).get_subscription(update.message.chat_id)
    if not sub:
        return await _need_start(update)
    answer = _router(ctx).handle(sub, update.message.text)
    await update.message.reply_text(answer)


# ---------- prístupová brána (#8; defaultne neaktívna) ----------
async def _gate(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Beží pred všetkými handlermi (group=-1). Pri prázdnom allowliste a vypnutom
    rate limite nerobí nič. Inak zablokuje spracovanie cez ApplicationHandlerStop."""
    guard: AccessGuard = ctx.application.bot_data["guard"]
    user = update.effective_user
    uid = user.id if user else None
    if uid is None:
        return
    if not guard.is_allowed(uid):
        log.warning("blokovaný používateľ mimo allowlistu: %s", uid)
        raise ApplicationHandlerStop
    if not guard.within_rate(uid, time.time()):
        log.warning("rate limit prekročený: %s", uid)
        raise ApplicationHandlerStop


# ---------- wiring ----------
def build_application(token: str, waste: WasteService, db: Database,
                      notify_hour: int, notify_minute: int,
                      guard: AccessGuard | None = None) -> Application:
    app = Application.builder().token(token).build()
    app.bot_data["waste"] = waste
    app.bot_data["db"] = db
    app.bot_data["router"] = Router(waste)
    # prázdny guard = allowlist aj rate limit vypnuté (žiadna zmena správania)
    app.bot_data["guard"] = guard or AccessGuard()

    # prístupová brána beží pred všetkým ostatným (skupina -1)
    app.add_handler(TypeHandler(Update, _gate), group=-1)

    conv = ConversationHandler(
        entry_points=[CommandHandler(["start", "zmen"], start)],
        states={
            CAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_cast)],
            ULICA: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_ulica)],
            CISLO: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_cislo)],
            KOMUNAL_PICK: [CallbackQueryHandler(picked_bin, pattern=r"^kbin:")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("dnes", cmd_dnes))
    app.add_handler(CommandHandler("zajtra", cmd_zajtra))
    app.add_handler(CommandHandler("tyzden", cmd_tyzden))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, free_text))

    async def _send(user_id: int, text: str):
        await app.bot.send_message(user_id, text, parse_mode="Markdown")

    dispatcher = NotificationDispatcher(db, _send)
    register_daily_notifications(app.job_queue, waste, dispatcher,
                                 notify_hour, notify_minute)
    return app
