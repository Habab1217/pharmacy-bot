import os
import google.generativeai as genai

from pharmacies import MEDICINES, format_medicine_categories, BAHIR_DAR_CENTER


def resolve_medicine_name(user_input: str) -> str:
    """Use Gemini to normalise the user's input to a standard generic medicine name."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    stock_list = ", ".join(MEDICINES)

    prompt = (
        f"The user is searching for a medicine. Their input is: \"{user_input}\"\n\n"
        f"Available medicines in our pharmacy network: {stock_list}\n\n"
        "Task: Identify which medicine from the available list best matches the user's input. "
        "The input may be in Amharic, English, a brand name, a misspelling, or an abbreviation. "
        "Reply with ONLY the single best-matching medicine name exactly as it appears in the list above. "
        "If nothing matches, reply with exactly: NO_MATCH"
    )

    response = model.generate_content(prompt)
    return response.text.strip().lower()


def smart_medicine_search(user_input: str, user_lat: float = None, user_lon: float = None) -> str:
    """Search for a medicine with Gemini name resolution, then show 3-category pharmacy results."""
    if user_lat is None:
        user_lat, user_lon = BAHIR_DAR_CENTER

    resolved = resolve_medicine_name(user_input)

    if resolved == "no_match" or not resolved:
        return (
            f"❌ *'{user_input}' አልተገኘም*\n"
            f"_'{user_input}' was not found in any pharmacy._\n\n"
            "እባክዎ ሌላ ስም ወይም አጠቃላይ ስም ይሞክሩ።\n"
            "_Please try a different or generic name._"
        )

    return format_medicine_categories(resolved, user_lat, user_lon)
