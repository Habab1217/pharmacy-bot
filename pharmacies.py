import math

BAHIR_DAR_CENTER = (11.5931, 37.3906)

MEDICINES = [
    "paracetamol", "amoxicillin", "ibuprofen", "metformin", "omeprazole",
    "ciprofloxacin", "azithromycin", "atorvastatin", "amlodipine", "metronidazole",
    "cotrimoxazole", "doxycycline", "prednisolone", "cetirizine", "salbutamol inhaler",
    "folic acid", "iron sulfate", "vitamin c", "zinc", "ors sachet",
    "albendazole", "artemether lumefantrine", "quinine", "fluconazole", "nystatin drops",
    "diclofenac", "tramadol", "lisinopril", "glibenclamide", "vitamin b complex",
]

# ─────────────────────────────────────────────────────────────────
# Price tiers (3 tiers × 10 pharmacies across Kebele 01-10)
#
#   🟢 BUDGET   — baseline prices   (×1.0)
#   🟡 STANDARD — mid-range         (×1.45–1.55)
#   🔴 PREMIUM  — private/imported  (×2.5–2.9)
#
# Maximum spread across all pharmacies: ~150–194%
# e.g. Artemether: budget 75 ብር → premium 210 ብር (+180%)
# ─────────────────────────────────────────────────────────────────
PHARMACIES = [
    # ── BUDGET tier ──────────────────────────────────────────────
    {
        "name": "ዝናብ ፋርማሲ",
        "name_en": "Zinab Pharmacy",
        "tier": "budget",
        "address": "ቀበሌ 02, ፋሲለደስ ሰፈር",
        "kebele": "ቀበሌ 02",
        "phone": "+251-58-220-0200",
        "hours": "ሰኞ-ቅዳሜ: 7:30-20:00",
        "lat": 11.5960,
        "lon": 37.3720,
        "stock": {
            "paracetamol": 5,  "amoxicillin": 28, "ibuprofen": 8,   "metformin": 20,
            "omeprazole": 25,  "ciprofloxacin": 40, "metronidazole": 12,
            "cotrimoxazole": 10, "doxycycline": 18, "prednisolone": 8,
            "cetirizine": 10,  "folic acid": 5,   "iron sulfate": 8,
            "vitamin c": 10,   "zinc": 8,          "ors sachet": 4,
            "albendazole": 6,  "quinine": 15,      "diclofenac": 10,
            "glibenclamide": 15, "vitamin b complex": 15,
        },
    },
    {
        "name": "ተስፋ ፋርማሲ",
        "name_en": "Tesfa Pharmacy",
        "tier": "budget",
        "address": "ቀበሌ 06, ወሃኒ ሰፈር",
        "kebele": "ቀበሌ 06",
        "phone": "+251-58-220-0600",
        "hours": "ሰኞ-ቅዳሜ: 8:00-19:30",
        "lat": 11.5850,
        "lon": 37.4020,
        "stock": {
            "paracetamol": 5,  "amoxicillin": 30, "ibuprofen": 8,   "metformin": 21,
            "omeprazole": 26,  "ciprofloxacin": 42, "metronidazole": 12,
            "cotrimoxazole": 10, "doxycycline": 19, "prednisolone": 8,
            "cetirizine": 10,  "folic acid": 5,   "iron sulfate": 8,
            "vitamin c": 10,   "zinc": 8,          "ors sachet": 4,
            "albendazole": 6,  "artemether lumefantrine": 75, "quinine": 16,
            "diclofenac": 10,  "tramadol": 22,    "glibenclamide": 16,
            "vitamin b complex": 16,
        },
    },
    {
        "name": "ብርሃን ፋርማሲ",
        "name_en": "Birhan Pharmacy",
        "tier": "budget",
        "address": "ቀበሌ 08, ዩኒቨርሲቲ ሰፈር",
        "kebele": "ቀበሌ 08",
        "phone": "+251-58-220-0800",
        "hours": "ሰኞ-ቅዳሜ: 7:30-21:00",
        "lat": 11.5750,
        "lon": 37.3810,
        "stock": {
            "paracetamol": 5,  "amoxicillin": 30, "ibuprofen": 8,   "metformin": 21,
            "omeprazole": 26,  "ciprofloxacin": 42, "azithromycin": 62,
            "amlodipine": 30,  "metronidazole": 12, "cotrimoxazole": 10,
            "doxycycline": 18, "prednisolone": 8,  "cetirizine": 10,
            "salbutamol inhaler": 70, "folic acid": 5, "iron sulfate": 8,
            "vitamin c": 10,   "zinc": 8,           "ors sachet": 4,
            "albendazole": 6,  "artemether lumefantrine": 76,
            "quinine": 15,     "fluconazole": 20,   "diclofenac": 10,
            "nystatin drops": 37, "atorvastatin": 50, "lisinopril": 28,
            "glibenclamide": 15, "vitamin b complex": 15,
        },
    },
    # ── STANDARD tier ────────────────────────────────────────────
    {
        "name": "ጤና ፍቅር ፋርማሲ",
        "name_en": "Tena Fiqir Pharmacy",
        "tier": "standard",
        "address": "ቀበሌ 03, ከተማ ማዕከል",
        "kebele": "ቀበሌ 03",
        "phone": "+251-58-220-0300",
        "hours": "ሰኞ-እሁድ: 7:00-22:00",
        "lat": 11.5935,
        "lon": 37.3915,
        "stock": {
            "paracetamol": 8,  "amoxicillin": 42, "ibuprofen": 12,  "metformin": 30,
            "omeprazole": 38,  "ciprofloxacin": 60, "azithromycin": 90,
            "atorvastatin": 76, "amlodipine": 45, "metronidazole": 18,
            "cotrimoxazole": 15, "doxycycline": 27, "prednisolone": 12,
            "cetirizine": 15,  "salbutamol inhaler": 106, "folic acid": 8,
            "iron sulfate": 12, "vitamin c": 15,   "zinc": 12,  "ors sachet": 6,
            "albendazole": 9,  "artemether lumefantrine": 114, "quinine": 23,
            "fluconazole": 30, "nystatin drops": 52, "diclofenac": 15,
            "tramadol": 33,    "lisinopril": 42,   "glibenclamide": 23,
            "vitamin b complex": 23,
        },
    },
    {
        "name": "ሰላም ፋርማሲ",
        "name_en": "Selam Pharmacy",
        "tier": "standard",
        "address": "ቀበሌ 05, ሴፍነ ሰላም",
        "kebele": "ቀበሌ 05",
        "phone": "+251-58-220-0500",
        "hours": "ሰኞ-ቅዳሜ: 8:00-20:00",
        "lat": 11.5890,
        "lon": 37.3960,
        "stock": {
            "paracetamol": 7,  "amoxicillin": 40, "ibuprofen": 12,  "metformin": 29,
            "omeprazole": 36,  "ciprofloxacin": 58, "metronidazole": 17,
            "cotrimoxazole": 14, "doxycycline": 26, "prednisolone": 12,
            "cetirizine": 15,  "folic acid": 7,    "iron sulfate": 12,
            "vitamin c": 14,   "zinc": 12,          "ors sachet": 6,
            "albendazole": 9,  "quinine": 22,       "diclofenac": 15,
            "glibenclamide": 22, "vitamin b complex": 22,
        },
    },
    {
        "name": "ሕይወት ፋርማሲ",
        "name_en": "Hiyiwet Pharmacy",
        "tier": "standard",
        "address": "ቀበሌ 07, ባህር ዳር ዋና ገበያ",
        "kebele": "ቀበሌ 07",
        "phone": "+251-58-220-0700",
        "hours": "ሰኞ-እሁድ: 7:00-21:30",
        "lat": 11.6020,
        "lon": 37.3870,
        "stock": {
            "paracetamol": 8,  "amoxicillin": 44, "ibuprofen": 12,  "metformin": 31,
            "omeprazole": 39,  "ciprofloxacin": 62, "azithromycin": 93,
            "atorvastatin": 78, "amlodipine": 47, "metronidazole": 19,
            "cotrimoxazole": 16, "doxycycline": 28, "prednisolone": 12,
            "cetirizine": 16,  "salbutamol inhaler": 110, "folic acid": 8,
            "iron sulfate": 12, "vitamin c": 16,   "zinc": 13,  "ors sachet": 6,
            "albendazole": 9,  "artemether lumefantrine": 118, "quinine": 23,
            "fluconazole": 31, "nystatin drops": 54, "diclofenac": 16,
            "tramadol": 34,    "lisinopril": 43,   "glibenclamide": 23,
            "vitamin b complex": 23,
        },
    },
    {
        "name": "አባይ ፋርማሲ",
        "name_en": "Abay Pharmacy",
        "tier": "standard",
        "address": "ቀበሌ 09, ፌሌጌ ሕይወት አካባቢ",
        "kebele": "ቀበሌ 09",
        "phone": "+251-58-220-0900",
        "hours": "ሰኞ-ቅዳሜ: 8:00-21:00",
        "lat": 11.6060,
        "lon": 37.3880,
        "stock": {
            "paracetamol": 8,  "amoxicillin": 42, "ibuprofen": 12,  "metformin": 30,
            "omeprazole": 38,  "ciprofloxacin": 60, "azithromycin": 90,
            "atorvastatin": 75, "amlodipine": 45, "metronidazole": 18,
            "cotrimoxazole": 15, "doxycycline": 27, "prednisolone": 12,
            "cetirizine": 15,  "salbutamol inhaler": 106, "folic acid": 8,
            "iron sulfate": 12, "vitamin c": 15,   "zinc": 12,  "ors sachet": 6,
            "albendazole": 9,  "artemether lumefantrine": 114, "quinine": 23,
            "fluconazole": 30, "diclofenac": 15,  "tramadol": 33,
            "lisinopril": 42,  "glibenclamide": 23, "vitamin b complex": 23,
        },
    },
    # ── PREMIUM tier ─────────────────────────────────────────────
    {
        "name": "ታና ፋርማሲ",
        "name_en": "Tana Pharmacy",
        "tier": "premium",
        "address": "ቀበሌ 01, ታና ሀይቅ አቅራቢያ",
        "kebele": "ቀበሌ 01",
        "phone": "+251-58-220-0100",
        "hours": "ሰኞ-ቅዳሜ: 8:00-21:00",
        "lat": 11.6048,
        "lon": 37.3845,
        "stock": {
            "paracetamol": 14, "amoxicillin": 76, "ibuprofen": 22,  "metformin": 54,
            "omeprazole": 68,  "ciprofloxacin": 108, "azithromycin": 158,
            "atorvastatin": 134, "amlodipine": 82, "metronidazole": 32,
            "cotrimoxazole": 27, "doxycycline": 48, "prednisolone": 21,
            "cetirizine": 27,  "salbutamol inhaler": 190, "folic acid": 14,
            "iron sulfate": 21, "vitamin c": 27,   "zinc": 20,  "ors sachet": 11,
            "albendazole": 16, "artemether lumefantrine": 203, "quinine": 40,
            "fluconazole": 54, "nystatin drops": 93, "diclofenac": 27,
            "tramadol": 58,    "lisinopril": 74,   "glibenclamide": 40,
            "vitamin b complex": 40,
        },
    },
    {
        "name": "ሰማይ ፋርማሲ",
        "name_en": "Semay Pharmacy",
        "tier": "premium",
        "address": "ቀበሌ 04, አውሮፕላን ማረፊያ አካባቢ",
        "kebele": "ቀበሌ 04",
        "phone": "+251-58-220-0400",
        "hours": "ሰኞ-ቅዳሜ: 8:30-20:30",
        "lat": 11.6080,
        "lon": 37.4010,
        "stock": {
            "paracetamol": 14, "amoxicillin": 78, "ibuprofen": 22,  "metformin": 56,
            "omeprazole": 70,  "ciprofloxacin": 112, "azithromycin": 164,
            "atorvastatin": 140, "amlodipine": 84, "metronidazole": 33,
            "prednisolone": 22, "cetirizine": 28,  "salbutamol inhaler": 196,
            "folic acid": 14,  "iron sulfate": 22, "vitamin c": 28,  "zinc": 21,
            "ors sachet": 11,  "albendazole": 16, "artemether lumefantrine": 210,
            "fluconazole": 56, "nystatin drops": 96, "diclofenac": 28,
            "tramadol": 60,    "lisinopril": 77,   "glibenclamide": 42,
            "vitamin b complex": 42,
        },
    },
    {
        "name": "ፍቅር ፋርማሲ",
        "name_en": "Fiqir Pharmacy",
        "tier": "premium",
        "address": "ቀበሌ 10, ሰሜናዊ ባህር ዳር",
        "kebele": "ቀበሌ 10",
        "phone": "+251-58-220-1000",
        "hours": "ሰኞ-እሁድ: 24 ሰዓት",
        "lat": 11.6120,
        "lon": 37.3950,
        "stock": {
            "paracetamol": 13, "amoxicillin": 73, "ibuprofen": 21,  "metformin": 52,
            "omeprazole": 65,  "ciprofloxacin": 104, "azithromycin": 152,
            "atorvastatin": 128, "amlodipine": 78, "metronidazole": 31,
            "cotrimoxazole": 26, "doxycycline": 47, "prednisolone": 20,
            "cetirizine": 26,  "salbutamol inhaler": 182, "folic acid": 13,
            "iron sulfate": 20, "vitamin c": 26,   "zinc": 19,  "ors sachet": 10,
            "albendazole": 15, "artemether lumefantrine": 195, "quinine": 38,
            "fluconazole": 52, "nystatin drops": 89, "diclofenac": 26,
            "tramadol": 56,    "lisinopril": 71,   "glibenclamide": 38,
            "vitamin b complex": 38,
        },
    },
]

TIER_LABELS = {
    "budget":   "🟢 ዝቅተኛ ዋጋ",
    "standard": "🟡 መካከለኛ ዋጋ",
    "premium":  "🔴 ከፍተኛ ዋጋ",
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _with_distance(pharmacy: dict, user_lat: float, user_lon: float) -> dict:
    dist = haversine_km(user_lat, user_lon, pharmacy["lat"], pharmacy["lon"])
    return {**pharmacy, "distance_km": round(dist, 2)}


def _split_categories(entries: list[dict]) -> dict:
    return {
        "nearby": [e for e in entries if e["distance_km"] <= 1.0],
        "kebele": [e for e in entries if 1.0 < e["distance_km"] <= 5.0],
        "city":   [e for e in entries if e["distance_km"] > 5.0],
    }


def _fmt_medicine_row(rank: int, entry: dict, cheapest: bool) -> str:
    mark = "✅ " if cheapest else f"{rank}. "
    tier = TIER_LABELS.get(entry.get("tier", ""), "")
    return (
        f"{mark}*{entry['name']}* {tier}\n"
        f"   💊 *{entry['price']} ብር*\n"
        f"   📏 {entry['distance_km']} ኪ.ሜ · 📞 {entry['phone']}\n"
    )


def _fmt_pharmacy_row(rank: int, entry: dict, closest: bool) -> str:
    mark = "✅ " if closest else f"{rank}. "
    tier = TIER_LABELS.get(entry.get("tier", ""), "")
    return (
        f"{mark}*{entry['name']}* {tier}\n"
        f"   📍 {entry['address']}\n"
        f"   📏 {entry['distance_km']} ኪ.ሜ · 📞 {entry['phone']}\n"
        f"   🕐 {entry['hours']}\n"
    )


_CAT_LABELS = [
    ("nearby", "📍 *በዙሪያህ (Nearby)* — 1 ኪ.ሜ ውስጥ"),
    ("kebele", "🏘️ *በቀበሌህ (Your Kebele)* — 5 ኪ.ሜ ውስጥ"),
    ("city",   "🏙️ *በከተማ (City-wide)* — ሁሉም ባህር ዳር"),
]


def format_medicine_categories(medicine_name: str, user_lat: float, user_lon: float) -> str:
    query = medicine_name.strip().lower()

    hits = []
    for p in PHARMACIES:
        price = next((v for k, v in p["stock"].items() if query in k or k in query), None)
        if price is not None:
            e = _with_distance(p, user_lat, user_lon)
            e["price"] = price
            hits.append(e)

    if not hits:
        return (
            f"❌ *'{medicine_name.title()}' አልተገኘም*\n"
            f"_Not found in any Bahir Dar pharmacy._\n\n"
            "እባክዎ ሌላ ስም ወይም አጠቃላይ ስም ይሞክሩ።\n"
            "_Try a different or generic name._"
        )

    cats = _split_categories(hits)
    sections = []
    for cat_key, cat_label in _CAT_LABELS:
        group = sorted(cats[cat_key], key=lambda x: (x["price"], x["distance_km"]))
        if not group:
            sections.append(f"{cat_label}\n_— ምንም አልተገኘም_\n")
            continue
        lines = [cat_label]
        for i, e in enumerate(group):
            lines.append(_fmt_medicine_row(i + 1, e, i == 0))
        if len(group) > 1:
            lo, hi = group[0]["price"], group[-1]["price"]
            pct = round((hi - lo) / lo * 100)
            lines.append(f"   _💡 ዋጋ ልዩነት: {lo}–{hi} ብር ({pct}% ልዩነት)_\n")
        sections.append("\n".join(lines))

    header = (
        f"🔍 *{medicine_name.title()}* — የፋርማሲ ዋጋ ንጽጽር\n"
        f"_Price comparison across Bahir Dar pharmacies_\n"
    )
    return header + "\n" + "\n".join(sections)


def format_all_pharmacies_by_category(user_lat: float, user_lon: float) -> str:
    all_entries = sorted(
        [_with_distance(p, user_lat, user_lon) for p in PHARMACIES],
        key=lambda x: x["distance_km"],
    )
    cats = _split_categories(all_entries)
    sections = []
    for cat_key, cat_label in _CAT_LABELS:
        group = cats[cat_key]
        if not group:
            sections.append(f"{cat_label}\n_— ምንም አልተገኘም_\n")
            continue
        lines = [cat_label]
        for i, e in enumerate(group):
            lines.append(_fmt_pharmacy_row(i + 1, e, i == 0))
        sections.append("\n".join(lines))
    return "🏥 *ቅርብ ፋርማሲዎች — ባህር ዳር*\n_Nearby Pharmacies — Bahir Dar_\n\n" + "\n".join(sections)


_SUMMARY_MEDICINES = [
    ("artemether lumefantrine", "Artemether/Lumefantrine", "🦟 ወባ (Malaria)"),
    ("amoxicillin",             "Amoxicillin 500mg",       "💊 ፀረ-ባክቴሪያ (Antibiotic)"),
    ("ciprofloxacin",           "Ciprofloxacin 500mg",     "💊 ፀረ-ባክቴሪያ (Antibiotic)"),
    ("salbutamol inhaler",      "Salbutamol Inhaler",      "🫁 አስም (Asthma)"),
    ("metformin",               "Metformin 500mg",         "🩸 ስኳር (Diabetes)"),
    ("omeprazole",              "Omeprazole 20mg",         "🫃 የሆድ (Gastric)"),
    ("atorvastatin",            "Atorvastatin 20mg",       "❤️ ልብ (Cardiovascular)"),
    ("paracetamol",             "Paracetamol 500mg",       "🌡️ ትኩሳት (Fever/Pain)"),
    ("doxycycline",             "Doxycycline 100mg",       "💊 ፀረ-ባክቴሪያ (Antibiotic)"),
    ("tramadol",                "Tramadol 50mg",           "🩹 ሕመም (Pain Relief)"),
]


def format_price_summary() -> str:
    from datetime import date
    today = date.today().strftime("%d %B %Y")

    lines = [
        "📊 *የዋጋ ማጠቃለያ — ባህር ዳር ፋርማሲዎች*",
        "_Bahir Dar Pharmacy Price Summary_",
        f"📅 {today}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    max_spread = 0
    for i, (key, display, category) in enumerate(_SUMMARY_MEDICINES, 1):
        entries = [(p["name"], p["stock"][key]) for p in PHARMACIES if key in p["stock"]]
        if not entries:
            continue
        entries.sort(key=lambda x: x[1])
        cheap_name, cheap_price = entries[0]
        pricey_name, pricey_price = entries[-1]
        spread = round((pricey_price - cheap_price) / cheap_price * 100)
        max_spread = max(max_spread, spread)

        lines += [
            f"{i}. 💊 *{display}*",
            f"   _{category}_",
            f"   🟢 ዝቅተኛ: *{cheap_price} ብር* — {cheap_name}",
            f"   🔴 ከፍተኛ: *{pricey_price} ብር* — {pricey_name}",
            f"   📈 ልዩነት / Spread: *+{spread}%*",
            "",
        ]

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "⚠️ *ዋና ግኝት / Key Finding*",
        "",
        f"ተመሳሳይ አስፈላጊ መድሃኒቶች በባህር ዳር ፋርማሲዎች ዋጋቸው እስከ *{max_spread}%* ይለያያል።",
        f"_The same essential medicine can cost up to {max_spread}% more_",
        "_at one Bahir Dar pharmacy vs another._",
        "",
        "📌 ምንጭ: ባህር ዳር ፋርማሲ ኔትወርክ ቦት",
        "_Source: Bahir Dar Pharmacy Network Bot_",
    ]

    return "\n".join(lines)


def format_nearest_three(user_lat: float, user_lon: float) -> str:
    top3 = sorted(
        [_with_distance(p, user_lat, user_lon) for p in PHARMACIES],
        key=lambda x: x["distance_km"],
    )[:3]
    lines = ["🏥 *3 ቅርብ ፋርማሲዎች / 3 Nearest Pharmacies*\n"]
    for i, e in enumerate(top3):
        lines.append(_fmt_pharmacy_row(i + 1, e, i == 0))
    return "\n".join(lines)
