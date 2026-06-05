FOOTER = (
    "\n──────────────\n"
    "🛡️ *MedLink Ethiopia* — ምንም ክፍያ የለም!\n"
    "መድሃኒት ሲገዙ ዋጋ አስቀድመው ይወቁ።\n"
    "_Free price information. Always._"
)


def with_footer(text: str) -> str:
    return text + FOOTER


_BILINGUAL = {
    "welcome": (
        "🏥 *MedLink Ethiopia*\n"
        "_ዲጂታል የፋርማሲ ኔትወርክ — ባህር ዳር_\n\n"
        "እንኳን ደህና መጡ! ይህ ሲስተም የባህር ዳር ምዝገባ ፋርማሲዎች ዋጋ ንጽጽር፣ "
        "ቦታ ፍለጋ፣ እና ተደራሽ ዋጋ ያላቸው መድሃኒቶችን ፈጥኖ ለማግኘት ያግዝዎታል።\n\n"
        "_Welcome! MedLink Ethiopia helps citizens find medicines at fair "
        "prices across registered pharmacies in Bahir Dar._\n\n"
        "እባክዎ ከታች ካሉት አማራጮች ይምረጡ:\n"
        "_Please choose an option below:_\n"
    ),
    "prescription_prompt": (
        "📋 *የሀኪም ማዘዣውን ፎቶ ያስገቡ*\n"
        "_(Please send a photo of your prescription)_\n\n"
        "Gemini AI ሕክምናዎቹን ስሞች ያወጣልዎታል።\n"
        "_Gemini AI will extract the medicine names for you._"
    ),
    "search_prompt": (
        "🔍 *መድሃኒት ፈልግ / Search Medicine*\n\n"
        "የሚፈልጉትን መድሃኒት ስም ይጻፉ (በአማርኛ ወይም በእንግሊዝኛ):\n"
        "_Type the medicine name you are looking for (in Amharic or English):_\n\n"
        "📝 _Examples: Paracetamol, አሞክሲሲሊን, Omeprazole, Ciprofloxacin_"
    ),
    "location_prompt": (
        "📍 *ቦታዎን ያጋሩ / Share Your Location*\n\n"
        "ቅርብ ፋርማሲዎችን ለማሳየት ቦታዎን ያጋሩ፣ ወይም የባህር ዳር ማዕከልን ይጠቀሙ።\n"
        "_Share your location to find nearby pharmacies, or use Bahir Dar city center as default._"
    ),
    "help_text": (
        "ℹ️ *እገዛ / Help*\n\n"
        "🔹 *የሀኪም ማዘዣውን ፎቶ ያስገቡ* — AI ሕክምናዎቹን ስሞች ያወጣልዎታል።\n"
        "🔹 *መድሃኒት ፈልግ* — ዋጋ በ3 ምድቦች (ቅርብ/ቀበሌ/ከተማ) ያሳይዎታል።\n"
        "🔹 *ቅርብ ፋርማሲዎች* — ሁሉም ፋርማሲዎች በርቀት ቅደም ተከተል።\n"
        "🔹 *የዋጋ ማወዳደሪያ* — 10 አስፈላጊ መድሃኒቶች ዋጋ ማጠቃለያ።\n"
        "📍 /nearest · 📊 /summary · 🌐 /language\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🏢 *ስለ ሲስተሙ / About This System*\n\n"
        "*MedLink Ethiopia* — ዲጂታል የፋርማሲ ኔትወርክ ስርዓት\n"
        "_MedLink Ethiopia — Digital Pharmacy Network System_\n\n"
        "📋 *የዋጋ ውሂብ እንዴት ይሰበሰባል?*\n"
        "ዋጋዎቹ ከምዝገባ ፋርማሲዎች በቀጥታ ይሰበሰባሉ። "
        "እያንዳንዱ ፋርማሲ በወር አንድ ጊዜ ዋጋ ዝርዝሩን ያስገባል።\n"
        "_Prices are collected directly from registered pharmacies. "
        "Each pharmacy submits its price list monthly._\n\n"
        "🏷️ *3 የዋጋ ደረጃዎች ምን ማለት ናቸው?*\n"
        "🟢 *ዝቅተኛ ዋጋ* — ዝቅተኛ ዋጋ ያላቸው ፋርማሲዎች (ለምሳሌ: PFSA-affiliated)\n"
        "🟡 *መካከለኛ ዋጋ* — መካከለኛ የዋጋ ደረጃ ያላቸው\n"
        "🔴 *ከፍተኛ ዋጋ* — ከፍተኛ ዋጋ ያላቸው የግል ፋርማሲዎች\n"
        "_🟢 Budget: lowest prices (e.g. PFSA-affiliated)_\n"
        "_🟡 Standard: mid-range pricing_\n"
        "_🔴 Premium: higher-priced private pharmacies_\n\n"
        "🏛️ *ለመንግሥት ምን ጥቅም አለው?*\n"
        "ይህ ሲስተም መንግሥት የፋርማሲ ዋጋዎችን እንዲቆጣጠር፣ "
        "ከፍተኛ ዋጋ ጭማሪን እንዲለይ፣ እና የቀረጥ ተገዥነትን "
        "እንዲያረጋግጥ ያግዛል።\n"
        "_This system helps government monitor pharmacy pricing, "
        "identify excessive markups, and verify tax compliance._\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📬 *አግኙን / Contact Us*\n"
        "*MedLink Ethiopia PLC*\n"
        "📍 ባህር ዳር, ኢትዮጵያ · _Bahir Dar, Ethiopia_\n"
        "✉️ info@medlinkethiopia.com"
    ),
    "analyzing": (
        "⏳ *ፎቶዎን እየተመለከትን ነው...*\n"
        "_(Analyzing your prescription photo with AI, please wait...)_"
    ),
    "prescription_result_suffix": (
        "---\n"
        "💊 ለእነዚህ መድሃኒቶች ቅርብ ፋርማሲ ይፈልጉ?\n"
        "_Would you like to find a nearby pharmacy for these medicines?_"
    ),
    "prescription_analyzed": "✅ *ቀለምዎ ተተነተነ / Prescription Analyzed*",
    "photo_error": (
        "❌ *ስህተት ተፈጠረ / An error occurred*\n\n"
        "ፎቶዎን ማንበብ አልተቻለም። እባክዎ ደግመው ይሞክሩ።\n"
        "_Could not read your photo. Please try again with a clearer image._"
    ),
    "photo_not_expected": (
        "📋 የሀኪም ማዘዣ ፎቶ ለመላክ ከዚህ ይጫኑ:\n"
        "_To send a prescription photo, use the menu below:_"
    ),
    "searching": "🔍 *\"{q}\" እየፈለግን ነው...*\n_(Searching for '{q}' in Bahir Dar pharmacies...)_",
    "search_error": (
        "❌ *ስህተት ተፈጠረ / Search failed*\n\n"
        "እባክዎ ደግመው ይሞክሩ።\n_Please try again._"
    ),
    "fallback": "ምናሌ ለማየት /start ይጫኑ\n_Press /start to see the menu_",
    "language_choose": (
        "🌐 *ቋንቋ ይምረጡ / Choose Language*\n\n"
        "እባክዎ የሚፈልጉትን ቋንቋ ይምረጡ:\n"
        "_Please select your preferred language:_"
    ),
    "language_set_am": "✅ ቋንቋ ወደ አማርኛ ተቀይሯል!\n_Language set to Amharic!_",
    "language_set_en": "✅ ቋንቋ ወደ እንግሊዝኛ ተቀይሯል!\n_Language set to English!_",
    "location_updated": "📍 *ቦታዎ ተቀብሏል!*\n_Location received!_",
    "nearest_prompt": (
        "📍 *ቦታዎን ያጋሩ*\n"
        "3 ቅርብ ፋርማሲዎችን ለማሳየት ቦታዎን ያጋሩ ወይም ነባሪ ቦታ ይጠቀሙ።\n"
        "_Share your location to find the 3 nearest pharmacies._"
    ),
    "summary_generating": "⏳ *ማጠቃለያ እየተዘጋጀ ነው...*\n_Generating price summary..._",
    "report_step1": (
        "🚨 *ዋጋ ሪፖርት / Price Report*\n\n"
        "ደረጃ 1/3 — ጥርጣሬ ካለበት ፋርማሲ ምን ነበር?\n"
        "_Step 1/3 — Which pharmacy charged you the suspicious price?_"
    ),
    "report_step2": (
        "🚨 *ዋጋ ሪፖርት / Price Report*\n\n"
        "ደረጃ 2/3 — የትኛው መድሃኒት ነው?\n"
        "_Step 2/3 — Which medicine was it?_\n\n"
        "📝 _Examples: Paracetamol, Amoxicillin, Ibuprofen, Ciprofloxacin_"
    ),
    "report_step3": (
        "🚨 *ዋጋ ሪፖርት / Price Report*\n\n"
        "ደረጃ 3/3 — ምን ያህል ዋጋ ከፈሉ? (በብር ይጻፉ)\n"
        "_Step 3/3 — What price were you charged? (type in Birr)_\n\n"
        "📝 _Example: 45  or  120.50_"
    ),
    "report_confirm": (
        "✅ *ሪፖርትዎ ደርሷል! / Report Received!*\n\n"
        "🏥 ፋርማሲ: *{pharmacy}*\n"
        "💊 መድሃኒት: *{medicine}*\n"
        "💰 የተከፈለ ዋጋ: *{price} ብር*\n\n"
        "ሪፖርትዎ ወደ MedLink Ethiopia ቀጥሎ ይላካል። "
        "ዋጋ ፍትሃዊ እንዲሆን ላደረጉት ትብብር እናመሰግናለን!\n\n"
        "_Your report has been submitted to MedLink Ethiopia. "
        "Thank you for helping keep medicine prices fair!_"
    ),
    "report_cancelled": (
        "❌ *ሪፖርት ተሰርዟል / Report Cancelled*\n\n"
        "ወደ ዋና ምናሌ ይመለሳሉ።\n"
        "_Returning to the main menu._"
    ),
    "loyalty_intro": (
        "🎁 *Loyalty Points — የሽልማት ነጥቦች*\n\n"
        "📊 አጠቃላይ Points: *{points} pts*\n"
        "🏆 ደረጃ: *{level}*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🌟 *Points እንዴት ይሰበሰባሉ?*\n"
        "• ⭐ ፋርማሲ ሲደለድሉ → +10 pts\n"
        "• 🚨 ዋጋ ሪፖርት ሲያደርጉ → +20 pts\n"
        "• 🧾 QR ሲ scan ያደርጉ → +5 pts\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎯 *ሽልማቶች / Rewards:*\n"
        "• 🥉 50 pts  → Bronze Member\n"
        "• 🥈 150 pts → Silver Member + 5% ቅናሽ\n"
        "• 🥇 300 pts → Gold Member + 10% ቅናሽ\n"
        "• 💎 500 pts → Platinum + ነፃ ጤና ምርመራ\n\n"
        "_Earn points every time you help make medicine prices fair!_"
    ),
    "loyalty_earned": (
        "🎉 *+{pts} Points ተጨምሮልዎታል!*\n"
        "📊 አጠቃላይ: *{total} pts* — ደረጃ: *{level}*\n"
        "_Points added! Total: {total} pts — Level: {level}_"
    ),
    "qr_scan_prompt": (
        "📷 *QR Code Scan*\n\n"
        "ከፋርማሲ ያገኙትን QR Code ፎቶ ያስገቡ።\n"
        "_Send a photo of the QR code you received from the pharmacy._\n\n"
        "✅ ዋጋ ይረጋገጣል + 5 Points ታገኛለህ!\n"
        "_Price will be verified + you earn 5 points!_"
    ),
    "qr_scan_done": (
        "✅ *QR ተሰርቷል! / QR Verified!*\n\n"
        "🏥 ፋርማሲ: *{pharmacy}*\n"
        "💊 መድሃኒት: *{medicine}*\n"
        "💰 ዋጋ: *{price} ብር*\n\n"
        "🎁 *+5 Points ተጨምሮልዎታል!*\n"
        "_Receipt verified! 5 loyalty points added._"
    ),
}

STRINGS = {
    "am": {
        **_BILINGUAL,
        "btn_prescription": "📋 የሀኪም ማዘዣውን ፎቶ ያስገቡ (Send Prescription Photo)",
        "btn_search": "🔍 መድሃኒት ፈልግ (Search Medicine)",
        "btn_pharmacies": "🏥 ቅርብ ፋርማሲዎች (Nearby Pharmacies)",
        "btn_pharmacies_nearby": "📍 በዙሪያህ ያሉ ፋርማሲዎች (Nearby)",
        "btn_pharmacies_kebele": "🏘️ በቀበሌው ያሉ ፋርማሲዎች (Kebele)",
        "btn_pharmacies_city": "🏙️ በከተማው ያሉ ፋርማሲዎች (City)",
        "btn_summary": "📊 የዋጋ ማወዳደሪያ (Price Summary)",
        "btn_help": "ℹ️ እገዛ (Help)",
        "btn_back": "🔙 ተመለስ (Back)",
        "btn_search_again": "🔍 ሌላ ፈልግ (Search Again)",
        "btn_main_menu": "↩️ ዋና ማውጫ ይመለሱ (Main Menu)",
        "btn_language": "🌐 ቋንቋ ቀይር (Change Language)",
        "btn_share_location": "📍 አሁን ያለሁበት ቦታ ላክ (Share My Location)",
        "btn_use_default": "📍 የባህር ዳር ማዕከልን ተጠቀም (Use Bahir Dar Center)",
        "btn_report": "🚨 ዋጋ ሪፖርት አድርግ (Report Price)",
        "btn_rating": "⭐ ፋርማሲ ደረጃ ስጥ (Rate Pharmacy)",
        "btn_loyalty": "🎁 Loyalty Points",
        "btn_tax_report": "🧾 የቀረጥ ሪፖርት (Tax Report)",
        "btn_lang_am": "🇪🇹 አማርኛ (Amharic)",
        "btn_lang_en": "🇬🇧 English",
    },
    "en": {
        **_BILINGUAL,
        "btn_prescription": "📋 Send Prescription Photo",
        "btn_search": "🔍 Search Medicine",
        "btn_pharmacies": "🏥 Nearby Pharmacies",
        "btn_pharmacies_nearby": "📍 Nearby (በዙሪያህ) — 1km",
        "btn_pharmacies_kebele": "🏘️ Kebele (በቀበሌው) — 5km",
        "btn_pharmacies_city": "🏙️ City Wide (በከተማው)",
        "btn_summary": "📊 Price Summary",
        "btn_help": "ℹ️ Help",
        "btn_back": "🔙 Back",
        "btn_search_again": "🔍 Search Again",
        "btn_main_menu": "↩️ Main Menu",
        "btn_language": "🌐 Change Language",
        "btn_share_location": "📍 Share My Location",
        "btn_use_default": "📍 Use Bahir Dar Center",
        "btn_report": "🚨 Report Price",
        "btn_rating": "⭐ Rate a Pharmacy",
        "btn_loyalty": "🎁 Loyalty Points",
        "btn_tax_report": "🧾 Tax Report",
        "btn_lang_am": "🇪🇹 አማርኛ (Amharic)",
        "btn_lang_en": "🇬🇧 English",
    },
}


def t(key: str, lang: str = "am", **kwargs) -> str:
    text = STRINGS.get(lang, STRINGS["am"]).get(key, STRINGS["am"].get(key, key))
    return text.format(**kwargs) if kwargs else text
