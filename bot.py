import logging
import os
import datetime
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from pharmacies import (
    BAHIR_DAR_CENTER,
    PHARMACIES,
    format_all_pharmacies_by_category,
    format_nearest_three,
    format_price_summary,
)
from gemini_vision import extract_medicines_from_image
from medicine_search import smart_medicine_search
from strings import t, with_footer

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

USE_DEFAULT_TEXT_AM = "📍 የባህር ዳር ማዕከልን ተጠቀም (Use Bahir Dar Center)"
USE_DEFAULT_TEXT_EN = "📍 Use Bahir Dar Center"


# ── helpers ──────────────────────────────────────────────────────

def get_lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("lang", "am")


def get_user_location(context: ContextTypes.DEFAULT_TYPE) -> tuple[float, float]:
    return (
        context.user_data.get("user_lat", BAHIR_DAR_CENTER[0]),
        context.user_data.get("user_lon", BAHIR_DAR_CENTER[1]),
    )


def main_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_prescription", lang), callback_data="send_prescription")],
        [InlineKeyboardButton(t("btn_search", lang), callback_data="search_medicine")],
        [InlineKeyboardButton(t("btn_pharmacies", lang), callback_data="nearby_pharmacies")],
        [InlineKeyboardButton(t("btn_summary", lang), callback_data="price_summary")],
        [InlineKeyboardButton(t("btn_report", lang), callback_data="report_price")],
        [InlineKeyboardButton(t("btn_rating", lang), callback_data="rate_pharmacy")],
        [InlineKeyboardButton(t("btn_loyalty", lang), callback_data="loyalty_points")],
        [InlineKeyboardButton(t("btn_tax_report", lang), callback_data="tax_report")],
        [InlineKeyboardButton(t("btn_help", lang), callback_data="help")],
        [InlineKeyboardButton(t("btn_language", lang), callback_data="change_language")],
    ])


def report_pharmacy_keyboard(lang: str) -> InlineKeyboardMarkup:
    rows = []
    pair = []
    for i, ph in enumerate(PHARMACIES):
        pair.append(InlineKeyboardButton(ph["name"], callback_data=f"report_pharm_{i}"))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton(t("btn_back", lang), callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)


def back_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_back", lang), callback_data="back_to_menu")],
    ])


def rate_pharmacy_select_keyboard(lang: str) -> InlineKeyboardMarkup:
    rows = []
    pair = []
    for i, ph in enumerate(PHARMACIES):
        pair.append(InlineKeyboardButton(ph["name"], callback_data=f"rate_pharm_{i}"))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton(t("btn_back", lang), callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)


def format_ratings_summary() -> str:
    """Read ratings.log and compute average stars per pharmacy."""
    import os, collections
    log_path = os.path.join(os.path.dirname(__file__), "ratings.log")
    if not os.path.exists(log_path):
        return (
            "⭐ *የፋርማሲ ደረጃዎች / Pharmacy Ratings*\n\n"
            "_ገና ምንም ደረጃ አልተሰጠም — No ratings yet._"
        )

    totals = collections.defaultdict(list)
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            # format: [timestamp] user=X | pharmacy=Y | stars=N | comment=Z
            try:
                parts = {p.split("=", 1)[0].strip(): p.split("=", 1)[1].strip()
                         for p in line.split("|")}
                ph = parts.get("pharmacy", "").strip()
                stars = int(parts.get("stars", "0").strip())
                if ph and stars:
                    totals[ph].append(stars)
            except Exception:
                continue

    if not totals:
        return (
            "⭐ *የፋርማሲ ደረጃዎች / Pharmacy Ratings*\n\n"
            "_ገና ምንም ደረጃ አልተሰጠም — No ratings yet._"
        )

    lines = [
        "⭐ *የፋርማሲ ደረጃዎች / Pharmacy Ratings*",
        "_Aggregated from user reviews_\n",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    sorted_ph = sorted(totals.items(), key=lambda x: -sum(x[1]) / len(x[1]))
    for ph, stars_list in sorted_ph:
        avg = sum(stars_list) / len(stars_list)
        filled = round(avg)
        star_bar = "⭐" * filled + "☆" * (5 - filled)
        lines.append(f"{star_bar} *{ph}*")
        lines.append(f"   📊 _(avg {avg:.1f}/5 · {len(stars_list)} ግምገማዎች)_\n")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


async def _save_rating(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    comment: str,
) -> None:
    lang = get_lang(context)
    data = context.user_data.get("rating_data", {})
    pharmacy = data.get("pharmacy", "—")
    stars = data.get("stars", 0)
    star_display = "⭐" * stars

    log_path = os.path.join(os.path.dirname(__file__), "ratings.log")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user = update.effective_user
    user_info = f"@{user.username}" if user.username else str(user.id)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(
            f"[{timestamp}] user={user_info} | pharmacy={pharmacy} "
            f"| stars={stars} | comment={comment}\n"
        )

    context.user_data["mode"] = None
    context.user_data.pop("rating_step", None)
    context.user_data.pop("rating_data", None)

    # +10 points for rating
    total = add_points(context, 10)
    level = get_level(total)

    await update.effective_message.reply_text(
        with_footer(
            f"✅ *ደረጃዎ ደርሷል! / Rating Submitted!*\n\n"
            f"🏥 *{pharmacy}*\n"
            f"⭐ {star_display} ({stars}/5)\n"
            f"💬 _{comment}_\n\n"
            f"🎁 *+10 Points ተጨምሮልዎታል!*\n"
            f"📊 አጠቃላይ: *{total} pts* — {level}\n"
            f"_Thank you for your feedback! +10 loyalty points added._"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 ሁሉም ደረጃዎች (View All Ratings)", callback_data="view_ratings")],
            [InlineKeyboardButton("🎁 የእኔ Points", callback_data="loyalty_points")],
            [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
        ]),
    )


# ── loyalty points helpers ───────────────────────────────────────

def get_points(context: ContextTypes.DEFAULT_TYPE) -> int:
    return context.user_data.get("loyalty_points", 0)


def add_points(context: ContextTypes.DEFAULT_TYPE, pts: int) -> int:
    total = context.user_data.get("loyalty_points", 0) + pts
    context.user_data["loyalty_points"] = total
    return total


def get_level(points: int) -> str:
    if points >= 500:
        return "💎 Platinum"
    elif points >= 300:
        return "🥇 Gold"
    elif points >= 150:
        return "🥈 Silver"
    elif points >= 50:
        return "🥉 Bronze"
    else:
        return "🌱 Starter"


def location_request_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(t("btn_share_location", lang), request_location=True)],
            [KeyboardButton(t("btn_use_default", lang))],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


async def _ask_for_location(message, context, pending_action: str) -> None:
    lang = get_lang(context)
    context.user_data["pending_action"] = pending_action
    prompt_key = "nearest_prompt" if pending_action == "nearest" else "location_prompt"
    await message.reply_text(
        with_footer(t(prompt_key, lang)),
        parse_mode="Markdown",
        reply_markup=location_request_keyboard(lang),
    )


async def _show_nearby_pharmacies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = get_lang(context)
    lat, lon = get_user_location(context)
    await update.effective_message.reply_text(
        with_footer(format_all_pharmacies_by_category(lat, lon)),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
        ]),
    )


async def _show_nearest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = get_lang(context)
    lat, lon = get_user_location(context)
    await update.effective_message.reply_text(
        with_footer(format_nearest_three(lat, lon)),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("btn_search", lang), callback_data="search_medicine")],
            [InlineKeyboardButton(t("btn_pharmacies", lang), callback_data="nearby_pharmacies")],
            [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
        ]),
    )


async def _show_filtered_pharmacies(update: Update, context: ContextTypes.DEFAULT_TYPE, filter_key: str) -> None:
    from pharmacies import PHARMACIES, haversine_km, TIER_LABELS
    lang = get_lang(context)
    lat, lon = get_user_location(context)

    TIER_ORDER = {"budget": 1, "standard": 2, "premium": 3}

    all_entries = []
    for p in PHARMACIES:
        dist = haversine_km(lat, lon, p["lat"], p["lon"])
        all_entries.append({**p, "distance_km": round(dist, 2)})

    if filter_key == "pharmacies_nearby":
        group = [e for e in all_entries if e["distance_km"] <= 1.0]
        title = "📍 *በዙሪያህ ያሉ ፋርማሲዎች* — 1 ኪ.ሜ ውስጥ\n_Pharmacies within 1km_"
    elif filter_key == "pharmacies_kebele":
        group = [e for e in all_entries if 1.0 < e["distance_km"] <= 5.0]
        title = "🏘️ *በቀበሌው ያሉ ፋርማሲዎች* — 5 ኪ.ሜ ውስጥ\n_Pharmacies within 5km_"
    else:
        group = [e for e in all_entries if e["distance_km"] > 5.0]
        title = "🏙️ *በከተማው ያሉ ፋርማሲዎች*\n_All other city pharmacies_"

    # Sort: ዝቅተኛ (budget) → መካከለኛ (standard) → ከፍተኛ (premium), then by distance
    group.sort(key=lambda x: (TIER_ORDER.get(x.get("tier", ""), 9), x["distance_km"]))

    if not group:
        text = f"{title}\n\n_— ምንም ፋርማሲ አልተገኘም / No pharmacies found in this range._"
    else:
        TIER_EMOJI = {"budget": "🟢", "standard": "🟡", "premium": "🔴"}
        lines = [title, ""]
        for i, e in enumerate(group):
            tier_key = e.get("tier", "")
            tier_icon = TIER_EMOJI.get(tier_key, "")
            tier_label = TIER_LABELS.get(tier_key, "")
            lines.append(
                f"{i+1}. {tier_icon} *{e['name']}* _{tier_label}_\n"
                f"   📍 {e['address']}\n"
                f"   📏 {e['distance_km']} ኪ.ሜ · 📞 {e['phone']}\n"
                f"   🕐 {e['hours']}\n"
            )
        text = "\n".join(lines)

    await update.effective_message.reply_text(
        with_footer(text),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("btn_pharmacies", lang), callback_data="nearby_pharmacies")],
            [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
        ]),
    )


async def _resolve_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Execute the action that was waiting for a location."""
    pending = context.user_data.pop("pending_action", None)
    if pending == "pharmacy_filter":
        filter_key = context.user_data.pop("pending_pharmacy_filter", "pharmacies_city")
        await _show_filtered_pharmacies(update, context, filter_key)
    elif pending == "nearby_pharmacies":
        await _show_nearby_pharmacies(update, context)
    elif pending == "nearest":
        await _show_nearest(update, context)
    elif pending == "search_medicine":
        lang = get_lang(context)
        context.user_data["mode"] = "search"
        await update.effective_message.reply_text(
            with_footer(t("search_prompt", lang)),
            parse_mode="Markdown",
            reply_markup=back_keyboard(lang),
        )


# ── command handlers ──────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["mode"] = None
    lang = get_lang(context)
    await update.message.reply_text(
        with_footer(t("welcome", lang)),
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(lang),
    )


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = get_lang(context)
    context.user_data["mode"] = "report"
    context.user_data["report_step"] = "pharmacy"
    context.user_data["report_data"] = {}
    await update.message.reply_text(
        with_footer(t("report_step1", lang)),
        parse_mode="Markdown",
        reply_markup=report_pharmacy_keyboard(lang),
    )


async def nearest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if "user_lat" not in context.user_data:
        await _ask_for_location(update.message, context, "nearest")
    else:
        await _show_nearest(update, context)


async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = get_lang(context)
    msg = await update.message.reply_text(
        t("summary_generating", lang), parse_mode="Markdown"
    )
    summary_text = format_price_summary()
    await msg.delete()
    await update.message.reply_text(
        with_footer(summary_text),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("btn_search", lang), callback_data="search_medicine")],
            [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
        ]),
    )


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = get_lang(context)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_lang_am", lang), callback_data="set_lang_am")],
        [InlineKeyboardButton(t("btn_lang_en", lang), callback_data="set_lang_en")],
    ])
    await update.message.reply_text(
        with_footer(t("language_choose", lang)),
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


# ── callback button handler ───────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)

    if query.data == "set_lang_am":
        context.user_data["lang"] = "am"
        await query.edit_message_text(
            with_footer(t("language_set_am", "am")), parse_mode="Markdown",
            reply_markup=main_menu_keyboard("am"),
        )

    elif query.data == "set_lang_en":
        context.user_data["lang"] = "en"
        await query.edit_message_text(
            with_footer(t("language_set_en", "en")), parse_mode="Markdown",
            reply_markup=main_menu_keyboard("en"),
        )

    elif query.data == "change_language":
        await query.edit_message_text(
            with_footer(t("language_choose", lang)), parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("btn_lang_am", lang), callback_data="set_lang_am")],
                [InlineKeyboardButton(t("btn_lang_en", lang), callback_data="set_lang_en")],
            ]),
        )

    elif query.data == "send_prescription":
        context.user_data["mode"] = "prescription"
        # Send a NEW message with ReplyKeyboard so camera button appears at bottom
        await query.edit_message_text(
            with_footer(t("prescription_prompt", lang)),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("btn_back", lang), callback_data="back_to_menu")],
            ]),
        )
        # ReplyKeyboard with request_photo — opens camera/gallery on tap
        await query.message.reply_text(
            "👇 ከታች ያለውን ቁልፍ ተጫን:\n_Tap the button below to open your camera:_",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("📸 ፎቶ አንሳ / Take Photo", request_photo=True)]],
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )

    elif query.data == "search_medicine":
        context.user_data["mode"] = "search"
        await query.edit_message_text(
            with_footer(t("search_prompt", lang)), parse_mode="Markdown",
            reply_markup=back_keyboard(lang),
        )

    elif query.data == "nearby_pharmacies":
        context.user_data["mode"] = None
        await query.edit_message_text(
            with_footer(
                "🏥 *ቅርብ ፋርማሲዎች / Nearby Pharmacies*\n\n"
                "እባክዎ ከታች ካሉት አማራጮች ይምረጡ:\n"
                "_Please choose a filter:_"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("btn_pharmacies_nearby", lang), callback_data="pharmacies_nearby")],
                [InlineKeyboardButton(t("btn_pharmacies_kebele", lang), callback_data="pharmacies_kebele")],
                [InlineKeyboardButton(t("btn_pharmacies_city", lang), callback_data="pharmacies_city")],
                [InlineKeyboardButton(t("btn_back", lang), callback_data="back_to_menu")],
            ]),
        )

    elif query.data in ("pharmacies_nearby", "pharmacies_kebele", "pharmacies_city"):
        context.user_data["mode"] = None
        if "user_lat" not in context.user_data:
            context.user_data["pending_action"] = "pharmacy_filter"
            context.user_data["pending_pharmacy_filter"] = query.data
            await query.edit_message_text(
                with_footer(t("location_prompt", lang)), parse_mode="Markdown",
            )
            await query.message.reply_text(
                "👇", reply_markup=location_request_keyboard(lang),
            )
        else:
            await _show_filtered_pharmacies(update, context, query.data)

    elif query.data == "price_summary":
        context.user_data["mode"] = None
        generating_msg = await query.message.reply_text(
            t("summary_generating", lang), parse_mode="Markdown"
        )
        summary_text = format_price_summary()
        await generating_msg.delete()
        await query.message.reply_text(
            with_footer(summary_text),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("btn_search", lang), callback_data="search_medicine")],
                [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
            ]),
        )

    elif query.data == "help":
        context.user_data["mode"] = None
        await query.edit_message_text(
            with_footer(t("help_text", lang)), parse_mode="Markdown",
            reply_markup=back_keyboard(lang),
        )

    elif query.data == "report_price":
        context.user_data["mode"] = "report"
        context.user_data["report_step"] = "pharmacy"
        context.user_data["report_data"] = {}
        await query.edit_message_text(
            with_footer(t("report_step1", lang)), parse_mode="Markdown",
            reply_markup=report_pharmacy_keyboard(lang),
        )

    elif query.data.startswith("report_pharm_"):
        idx = int(query.data.split("_")[-1])
        pharmacy_name = PHARMACIES[idx]["name"]
        context.user_data["report_data"]["pharmacy"] = pharmacy_name
        context.user_data["report_step"] = "medicine"
        await query.edit_message_text(
            with_footer(t("report_step2", lang)) + f"\n\n🏥 _{pharmacy_name}_",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("btn_back", lang), callback_data="report_price")],
            ]),
        )

    elif query.data == "back_to_menu":
        context.user_data["mode"] = None
        context.user_data.pop("report_step", None)
        context.user_data.pop("report_data", None)
        context.user_data.pop("rating_step", None)
        context.user_data.pop("rating_data", None)
        # Remove any ReplyKeyboard (e.g. camera button from prescription)
        await query.message.reply_text("↩️", reply_markup=ReplyKeyboardRemove())
        await query.edit_message_text(
            with_footer(t("welcome", lang)), parse_mode="Markdown",
            reply_markup=main_menu_keyboard(lang),
        )

    elif query.data == "rate_pharmacy":
        context.user_data["mode"] = "rating"
        context.user_data["rating_step"] = "pharmacy"
        context.user_data["rating_data"] = {}
        await query.edit_message_text(
            with_footer(
                "⭐ *ፋርማሲ ደረጃ ስጥ / Rate a Pharmacy*\n\n"
                "ደረጃ 1/3 — የትኛውን ፋርማሲ ደረጃ መስጠት ትፈልጋለህ?\n"
                "_Step 1/3 — Which pharmacy would you like to rate?_"
            ),
            parse_mode="Markdown",
            reply_markup=rate_pharmacy_select_keyboard(lang),
        )

    elif query.data.startswith("rate_pharm_"):
        idx = int(query.data.split("_")[-1])
        pharmacy_name = PHARMACIES[idx]["name"]
        context.user_data["rating_data"]["pharmacy"] = pharmacy_name
        context.user_data["rating_data"]["pharmacy_idx"] = idx
        context.user_data["rating_step"] = "stars"
        await query.edit_message_text(
            with_footer(
                f"⭐ *ፋርማሲ ደረጃ ስጥ / Rate a Pharmacy*\n\n"
                f"🏥 _{pharmacy_name}_\n\n"
                f"ደረጃ 2/3 — ምን ያህል ኮከብ ትሰጣለህ?\n"
                f"_Step 2/3 — How many stars do you give?_"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⭐", callback_data="rate_stars_1"),
                    InlineKeyboardButton("⭐⭐", callback_data="rate_stars_2"),
                    InlineKeyboardButton("⭐⭐⭐", callback_data="rate_stars_3"),
                ],
                [
                    InlineKeyboardButton("⭐⭐⭐⭐", callback_data="rate_stars_4"),
                    InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data="rate_stars_5"),
                ],
                [InlineKeyboardButton(t("btn_back", lang), callback_data="rate_pharmacy")],
            ]),
        )

    elif query.data.startswith("rate_stars_"):
        stars = int(query.data.split("_")[-1])
        context.user_data["rating_data"]["stars"] = stars
        context.user_data["rating_step"] = "comment"
        star_display = "⭐" * stars
        pharmacy_name = context.user_data["rating_data"].get("pharmacy", "")
        await query.edit_message_text(
            with_footer(
                f"⭐ *ፋርማሲ ደረጃ ስጥ / Rate a Pharmacy*\n\n"
                f"🏥 _{pharmacy_name}_  {star_display}\n\n"
                f"ደረጃ 3/3 — አስተያየትዎን ይጻፉ (አማርኛ ወይም እንግሊዝኛ)\n"
                f"_Step 3/3 — Write a short comment (optional)_\n\n"
                f"ለመዝለል «/skip» ይጻፉ\n"
                f"_Type /skip to skip_"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⏭️ ዝለል (Skip)", callback_data="rate_skip_comment")],
                [InlineKeyboardButton(t("btn_back", lang), callback_data="rate_pharmacy")],
            ]),
        )

    elif query.data == "rate_skip_comment":
        await _save_rating(update, context, comment="—")

    elif query.data == "view_ratings":
        text = format_ratings_summary()
        await query.edit_message_text(
            with_footer(text),
            parse_mode="Markdown",
            reply_markup=back_keyboard(lang),
        )

    elif query.data == "loyalty_points":
        context.user_data["mode"] = None
        points = get_points(context)
        level = get_level(points)
        await query.edit_message_text(
            with_footer(t("loyalty_intro", lang, points=points, level=level)),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📷 QR Scan (+5 pts)", callback_data="qr_scan")],
                [InlineKeyboardButton(t("btn_back", lang), callback_data="back_to_menu")],
            ]),
        )

    elif query.data == "qr_scan":
        context.user_data["mode"] = "qr_scan"
        await query.edit_message_text(
            with_footer(t("qr_scan_prompt", lang)),
            parse_mode="Markdown",
            reply_markup=back_keyboard(lang),
        )

    elif query.data == "tax_report":
        context.user_data["mode"] = None
        await query.edit_message_text(
            with_footer(
                "🧾 *የቀረጥ ሪፖርት / Tax Report*\n\n"
                "🚧 _ይህ ባህሪ በቅርቡ ይመጣል — Monthly tax report coming soon!_\n\n"
                "ፋርማሲዎች ወርሃዊ ሪፖርት ያቀርባሉ።\n"
                "_Pharmacies will submit monthly tax compliance reports._"
            ),
            parse_mode="Markdown",
            reply_markup=back_keyboard(lang),
        )


# ── location handler ──────────────────────────────────────────────

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = get_lang(context)
    loc = update.message.location
    context.user_data["user_lat"] = loc.latitude
    context.user_data["user_lon"] = loc.longitude
    await update.message.reply_text(
        with_footer(t("location_updated", lang)), parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    await _resolve_pending(update, context)


# ── photo handler ─────────────────────────────────────────────────

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = get_lang(context)

    if context.user_data.get("mode") == "qr_scan":
        context.user_data["mode"] = None
        processing_msg = await update.message.reply_text(
            "⏳ *QR እየተነበበ ነው...*\n_Reading QR code..._", parse_mode="Markdown"
        )
        # +5 points for QR scan
        total = add_points(context, 5)
        level = get_level(total)
        await processing_msg.delete()
        await update.message.reply_text(
            with_footer(
                "✅ *QR ተሰርቷል! / QR Scanned!*\n\n"
                "🧾 ደረሰኝዎ ተረጋግጧል!\n"
                "_Your receipt has been verified!_\n\n"
                f"🎁 *+5 Points ተጨምሮልዎታል!*\n"
                f"📊 አጠቃላይ: *{total} pts* — {level}"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎁 የእኔ Points", callback_data="loyalty_points")],
                [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
            ]),
        )
        return

    if context.user_data.get("mode") != "prescription":
        await update.message.reply_text(
            with_footer(t("photo_not_expected", lang)), parse_mode="Markdown",
            reply_markup=main_menu_keyboard(lang),
        )
        return

    context.user_data["mode"] = None
    # Remove the camera ReplyKeyboard immediately
    await update.message.reply_text(
        "⏳ *ማዘዣው እየተነተነ ነው...*\n_Analyzing your prescription..._",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    processing_msg = await update.message.reply_text(
        t("analyzing", lang), parse_mode="Markdown",
    )

    try:
        photo = update.message.photo[-1]
        photo_file = await photo.get_file()
        image_bytes = await photo_file.download_as_bytearray()
        result = extract_medicines_from_image(bytes(image_bytes), "image/jpeg")
        await processing_msg.delete()

        response_text = (
            f"{t('prescription_analyzed', lang)}\n\n"
            f"{result}\n\n"
            f"{t('prescription_result_suffix', lang)}"
        )
        await update.message.reply_text(
            with_footer(response_text), parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("btn_search", lang), callback_data="search_medicine")],
                [InlineKeyboardButton(t("btn_pharmacies", lang), callback_data="nearby_pharmacies")],
                [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
            ]),
        )

    except Exception as e:
        logger.error(f"Error processing prescription photo: {e}")
        await processing_msg.delete()
        await update.message.reply_text(
            with_footer(t("photo_error", lang)), parse_mode="Markdown",
            reply_markup=main_menu_keyboard(lang),
        )


# ── text handler ──────────────────────────────────────────────────

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = get_lang(context)
    text = update.message.text.strip()

    # Default-location keyboard button
    if text in (USE_DEFAULT_TEXT_AM, USE_DEFAULT_TEXT_EN):
        context.user_data["user_lat"] = BAHIR_DAR_CENTER[0]
        context.user_data["user_lon"] = BAHIR_DAR_CENTER[1]
        await update.message.reply_text(
            with_footer(t("location_updated", lang)), parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        await _resolve_pending(update, context)
        return

    if context.user_data.get("mode") == "rating":
        step = context.user_data.get("rating_step")

        if step == "comment":
            # User typed a comment (or /skip)
            comment = "—" if text.lower() in ("/skip", "skip") else text
            await _save_rating(update, context, comment=comment)
            return

    if context.user_data.get("mode") == "report":
        step = context.user_data.get("report_step")
        data = context.user_data.setdefault("report_data", {})

        if step == "medicine":
            data["medicine"] = text
            context.user_data["report_step"] = "price"
            await update.message.reply_text(
                with_footer(t("report_step3", lang)) + f"\n\n💊 _{text}_",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t("btn_back", lang), callback_data="report_price")],
                ]),
            )
            return

        if step == "price":
            data["price"] = text
            pharmacy = data.get("pharmacy", "—")
            medicine = data.get("medicine", "—")
            price = data.get("price", "—")

            # Log the report
            log_path = os.path.join(os.path.dirname(__file__), "reports.log")
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            user = update.effective_user
            user_info = f"@{user.username}" if user.username else str(user.id)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(
                    f"[{timestamp}] user={user_info} | pharmacy={pharmacy} "
                    f"| medicine={medicine} | price={price} ብር\n"
                )

            context.user_data["mode"] = None
            context.user_data.pop("report_step", None)
            context.user_data.pop("report_data", None)

            # +20 points for price report
            total = add_points(context, 20)
            level = get_level(total)

            await update.message.reply_text(
                with_footer(
                    t("report_confirm", lang, pharmacy=pharmacy, medicine=medicine, price=price) +
                    f"\n\n🎁 *+20 Points ተጨምሮልዎታል!*\n"
                    f"📊 አጠቃላይ: *{total} pts* — {level}"
                ),
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(lang),
            )
            return

    if context.user_data.get("mode") == "search":
        context.user_data["mode"] = None
        searching_msg = await update.message.reply_text(
            t("searching", lang, q=text), parse_mode="Markdown",
        )
        try:
            lat, lon = get_user_location(context)
            result_text = smart_medicine_search(text, lat, lon)
            await searching_msg.delete()
            await update.message.reply_text(
                with_footer(result_text), parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t("btn_search_again", lang), callback_data="search_medicine")],
                    [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
                ]),
            )
        except Exception as e:
            logger.error(f"Medicine search error: {e}")
            await searching_msg.delete()
            await update.message.reply_text(
                with_footer(t("search_error", lang)), parse_mode="Markdown",
                reply_markup=main_menu_keyboard(lang),
            )
    else:
        await update.message.reply_text(
            with_footer(t("fallback", lang)), parse_mode="Markdown",
            reply_markup=main_menu_keyboard(lang),
        )


# ── entry point ───────────────────────────────────────────────────

async def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("nearest", nearest_command))
    app.add_handler(CommandHandler("summary", summary_command))
    app.add_handler(CommandHandler("language", language_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.LOCATION, location_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("Bot is starting...")
    async with app:
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        threading.Thread(target=run_health_server, daemon=True).start()
        # Run forever
        await asyncio.Event().wait()
        await app.updater.stop()
        await app.stop()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
