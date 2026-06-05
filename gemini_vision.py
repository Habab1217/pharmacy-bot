import os
import google.generativeai as genai


def extract_medicines_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set")

    genai.configure(api_key=api_key)

    model = genai.GenerativeModel("gemini-2.5-flash")

    image_part = {
        "mime_type": mime_type,
        "data": image_bytes,
    }

    prompt = (
        "This is a medical prescription photo. "
        "Please extract all medicine names from this prescription. "
        "List each medicine on a new line with its dosage if visible. "
        "If you cannot identify it as a prescription, say so clearly. "
        "Respond in both Amharic and English."
    )

    response = model.generate_content([image_part, prompt])
    return response.text
