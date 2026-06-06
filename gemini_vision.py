import os
import google.generativeai as genai
from pharmacies import MEDICINES


def _fuzzy_match(extracted: list[str], known: list[str]) -> list[dict]:
    """
    Match extracted medicine names (possibly handwritten/misspelled)
    against our registered MEDICINES list using simple scoring.
    Returns list of {extracted, matched, score} sorted best-first.
    """
    results = []
    for raw in extracted:
        raw_clean = raw.strip().lower()
        if not raw_clean:
            continue

        best_match = None
        best_score = 0

        for med in known:
            med_lower = med.lower()

            # Exact match
            if raw_clean == med_lower:
                score = 100
            # Starts-with
            elif med_lower.startswith(raw_clean) or raw_clean.startswith(med_lower):
                score = 85
            # Substring
            elif raw_clean in med_lower or med_lower in raw_clean:
                score = 70
            # Character overlap ratio (simple bigram)
            else:
                raw_set = set(raw_clean[i:i+2] for i in range(len(raw_clean)-1))
                med_set = set(med_lower[i:i+2] for i in range(len(med_lower)-1))
                if raw_set and med_set:
                    overlap = len(raw_set & med_set) / max(len(raw_set), len(med_set))
                    score = int(overlap * 60)
                else:
                    score = 0

            if score > best_score:
                best_score = score
                best_match = med

        if best_match and best_score >= 30:
            results.append({
                "extracted": raw.strip(),
                "matched": best_match,
                "score": best_score,
                "confidence": "✅ ተገኝቷል" if best_score >= 70 else "⚠️ ሊሆን ይችላል",
            })
        else:
            results.append({
                "extracted": raw.strip(),
                "matched": None,
                "score": 0,
                "confidence": "❌ አልተገኘም",
            })

    return results


def extract_medicines_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    medicines_list = ", ".join(MEDICINES)

    image_part = {
        "mime_type": mime_type,
        "data": image_bytes,
    }

    prompt = (
        "This is a medical prescription photo, possibly handwritten in Amharic or English.\n"
        "Your task:\n"
        "1. Extract ONLY the medicine/drug names written on this prescription.\n"
        "2. List each medicine name on a separate line.\n"
        "3. Do NOT include dosage, instructions, or doctor notes — names only.\n"
        "4. If handwriting is unclear, make your best guess at the medicine name.\n"
        "5. Output format: one medicine name per line, nothing else.\n"
        "6. If this is not a prescription, reply with exactly: NOT_A_PRESCRIPTION\n\n"
        f"Known medicines in our system for reference: {medicines_list}"
    )

    response = model.generate_content([image_part, prompt])
    raw_text = response.text.strip()

    # Not a prescription
    if "NOT_A_PRESCRIPTION" in raw_text.upper():
        return (
            "❌ *ይህ የሀኪም ማዘዣ አይደለም*\n"
            "_This does not appear to be a medical prescription._\n\n"
            "እባክዎ ትክክለኛ ማዘዣ ፎቶ ያስገቡ።\n"
            "_Please send a clear photo of a medical prescription._"
        )

    # Parse extracted medicine names
    extracted_names = [
        line.strip().lstrip("-•*123456789. ")
        for line in raw_text.splitlines()
        if line.strip()
    ]

    if not extracted_names:
        return (
            "⚠️ *ምንም መድሃኒት ስም ሊታወቅ አልቻለ*\n"
            "_No medicine names could be extracted._\n\n"
            "ፎቶው ግልፅ ካልሆነ እንደገና ይሞክሩ።\n"
            "_If the photo is unclear, please try again with better lighting._"
        )

    # Fuzzy match against our MEDICINES list
    matches = _fuzzy_match(extracted_names, MEDICINES)

    lines = [
        "💊 *የሀኪም ማዘዣ ትንተና / Prescription Analysis*\n",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    found_count = 0
    not_found = []

    for m in matches:
        if m["matched"]:
            found_count += 1
            lines.append(
                f"{m['confidence']} *{m['matched']}*\n"
                f"   _ከማዘዣ: \"{m['extracted']}\"_"
            )
        else:
            not_found.append(m["extracted"])

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"📊 {found_count}/{len(matches)} ምርቶች በስርዓቱ ውስጥ ተገኝተዋል")
    lines.append(f"_{found_count}/{len(matches)} medicines found in our system_")

    if not_found:
        lines.append(
            f"\n⚠️ *ያልተገኙ:* {', '.join(not_found)}\n"
            "_Not registered in our pharmacy network_"
        )

    return "\n".join(lines)
