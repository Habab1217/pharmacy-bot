import os
import google.generativeai as genai


def _fuzzy_match(extracted: list, known: list) -> list:
    """Match extracted names against registered MEDICINES list."""
    results = []
    for raw in extracted:
        raw_clean = raw.strip().lower()
        if not raw_clean:
            continue
        best_match = None
        best_score = 0
        for med in known:
            med_lower = med.lower()
            if raw_clean == med_lower:
                score = 100
            elif med_lower.startswith(raw_clean) or raw_clean.startswith(med_lower):
                score = 85
            elif raw_clean in med_lower or med_lower in raw_clean:
                score = 70
            else:
                raw_set = set(raw_clean[i:i+2] for i in range(len(raw_clean)-1))
                med_set = set(med_lower[i:i+2] for i in range(len(med_lower)-1))
                if raw_set and med_set:
                    score = int(len(raw_set & med_set) / max(len(raw_set), len(med_set)) * 60)
                else:
                    score = 0
            if score > best_score:
                best_score = score
                best_match = med
        if best_match and best_score >= 30:
            confidence = "✅" if best_score >= 70 else "⚠️"
            results.append({"extracted": raw.strip(), "matched": best_match,
                            "score": best_score, "confidence": confidence})
        else:
            results.append({"extracted": raw.strip(), "matched": None,
                            "score": 0, "confidence": "❌"})
    return results


def extract_medicines_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    # Import here to avoid circular import
    try:
        from pharmacies import MEDICINES
    except ImportError:
        MEDICINES = []

    medicines_list = ", ".join(MEDICINES) if MEDICINES else "paracetamol, amoxicillin, ibuprofen"

    image_part = {"mime_type": mime_type, "data": image_bytes}

    prompt = (
        "This is a medical prescription photo, possibly handwritten in Amharic or English.\n"
        "Task: Extract ONLY the medicine/drug names written on this prescription.\n"
        "Rules:\n"
        "- List each medicine name on a separate line\n"
        "- Do NOT include dosage, instructions, or doctor notes\n"
        "- If handwriting is unclear, make your best guess\n"
        "- Output format: one medicine name per line, nothing else\n"
        "- If this is not a prescription, reply with exactly: NOT_A_PRESCRIPTION\n\n"
        f"Known medicines for reference: {medicines_list}"
    )

    try:
        response = model.generate_content([image_part, prompt])
        raw_text = response.text.strip()
    except Exception as e:
        raise RuntimeError(f"Gemini API error: {e}")

    if "NOT_A_PRESCRIPTION" in raw_text.upper():
        return (
            "❌ *ይህ የሀኪም ማዘዣ አይደለም*\n"
            "_This does not appear to be a medical prescription._\n\n"
            "እባክዎ ትክክለኛ ማዘዣ ፎቶ ያስገቡ።"
        )

    extracted_names = [
        line.strip().lstrip("-•*123456789. ").rstrip(".,;:")
        for line in raw_text.splitlines()
        if line.strip() and len(line.strip()) > 1
    ]

    if not extracted_names:
        return (
            "⚠️ *ምንም መድሃኒት ስም ሊታወቅ አልቻለ*\n"
            "_No medicine names could be extracted._\n\n"
            "ፎቶው ግልፅ ካልሆነ እንደገና ይሞክሩ።"
        )

    matches = _fuzzy_match(extracted_names, MEDICINES) if MEDICINES else []

    lines = [
        "💊 *የሀኪም ማዘዣ ትንተና / Prescription Analysis*\n",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    if matches:
        found = [m for m in matches if m["matched"]]
        not_found = [m for m in matches if not m["matched"]]

        for m in found:
            lines.append(
                f"{m['confidence']} *{m['matched']}*\n"
                f"   _ከማዘዣ: \"{m['extracted']}\"_"
            )

        lines.append(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"📊 *{len(found)}/{len(matches)}* ምርቶች ተገኝተዋል / found in system")

        if not_found:
            nf_names = ", ".join(m["extracted"] for m in not_found)
            lines.append(f"\n⚠️ *ያልተገኙ:* _{nf_names}_")
    else:
        # No MEDICINES list — just show raw extracted names
        lines.append("📋 *የተዘረዘሩ ስሞች:*")
        for name in extracted_names:
            lines.append(f"• {name}")

    return "\n".join(lines)
