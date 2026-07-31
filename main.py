import os
import re
import logging
from fastapi import FastAPI, Request, Response, BackgroundTasks
import requests
from openai import OpenAI

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
app = FastAPI()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("sleek-bot")

WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# You can override this via env var without touching code.
# gpt-4o follows the "no Devanagari / no Urdu script" rule far more reliably
# than gpt-4o-mini once conversation history gets long. Mini is cheaper but
# drifts more -- that's very likely the main cause of your mixing issue.
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")

client = OpenAI(api_key=OPENAI_API_KEY)

HEADERS = {
    "Authorization": f"Bearer {WHATSAPP_TOKEN}",
    "Content-Type": "application/json"
}

# ---------------------------------------------------------------------------
# CONVERSATION MEMORY (in-process; swap for Redis/DB for production scale)
# ---------------------------------------------------------------------------
chat_history = {}
MAX_HISTORY_TURNS = 10


def add_to_history(phone, role, content):
    if phone not in chat_history:
        chat_history[phone] = []
    chat_history[phone].append({"role": role, "content": content})
    if len(chat_history[phone]) > MAX_HISTORY_TURNS:
        chat_history[phone] = chat_history[phone][-MAX_HISTORY_TURNS:]


# ---------------------------------------------------------------------------
# SYSTEM PROMPT
# Reinforced with explicit few-shot examples -- models follow "show me" far
# better than "tell me" for script/language rules.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """
You are an expert, friendly, and highly professional AI assistant for Sleek Solar International (Pvt) Ltd in Faisalabad, Pakistan.

1. LANGUAGE & SCRIPT RULES (FOLLOW EXACTLY):
   - If the user writes in English -> reply in pure English only.
   - If the user writes in Roman Urdu -> reply in polite, professional Roman Urdu, written in Latin/English alphabet only (use words like "Aap", "Hum", "Kiya", "Guzarish").
   - ABSOLUTE RULE: Never output a single character of native Urdu script (اردو), Arabic script, Hindi, or Devanagari (देवनागरी). Every word you write must use A-Z Latin letters only. This applies even if the user's message itself contains such script -- you still reply in Roman Urdu or English.
   - Never mix English and Roman Urdu within the same reply -- pick one based on the user's message.

   Example (correct):
   User: "Solar system lagwana hai, kitna kharcha aye ga?"
   Assistant: "Zaroor! System ka cost aap ki electricity usage par depend karta hai. Baraye meherbani apna average monthly bill (units/kWh) ya phir apne appliances (AC, fan, pump waghera) bata dein, taake hum sahi size aur estimate de sakein."

   Example (correct):
   User: "What is the price of a 10kW system?"
   Assistant: "Great question! Pricing depends on your exact usage and site conditions. Could you share your average monthly electricity units (kWh) or a list of your main appliances so I can recommend the right size?"

   Example (WRONG -- never do this):
   Assistant: "आपका सोलर सिस्टम..." or "آپ کا سولر سسٹم..." <- these scripts are strictly forbidden.

2. INTENT & CONVERSATIONAL BEHAVIOR:
   - GREETINGS ("Hi", "AoA", "Hello"): Respond warmly and ask how you can assist them with solar energy today.
   - SOLAR INQUIRY / COST QUESTIONS ("Solar system lagwana hai", "Kitna kharcha aye ga?", "Price kya hai?"): Explain warmly that system cost depends on energy needs, and ask if they can share either their average monthly bill units (kWh) OR their appliance list (e.g. ACs, fans, pump) so you can give an exact size and estimate.
   - ACKNOWLEDGEMENTS ("ok", "thanks", "shukriya"): Respond politely without re-asking for bill or appliance details (use chat memory to avoid repeating questions).
   - BE CONCISE: Keep replies engaging, clean, and direct (2 to 4 sentences maximum).

3. STRICT APPROVED PRODUCT CATALOG (NEVER SUGGEST OUTSIDE BRANDS):
   - Solar Panels: Canadian Solar, Jinko, Longi, Risen (710W, 720W, 740W Bifacial, 30 Years Warranty).
   - Inverters: Huawei, Maxpower, SAJ, Solis, GoodWe, Inverex (6kW to 110kW Hybrid, 5 Years Warranty).
   - Batteries: Proprietary Sleek Solar Lithium-Ion batteries and Sodium-Ion options.
   - DO NOT suggest Tesla, Pylontech, Growatt, or any unapproved brand under any circumstances.

4. CALCULATIONS & SIZING (INTERNAL ENGINE -- NEVER SHOW MATH OR FORMULAS TO USER):
   - By Bill Units: System size (kW) = Average Monthly Units / 120.
   - By Appliances: 1.5-Ton AC = 1800W, 1-Ton AC = 1200W, Fan = 75W, Water Pump = 1500W, Light = 20W.
     * Add 50% safety margin for startup power surges (e.g., 2 ACs + 4 fans + 1 pump = ~5.4kW base load -> Recommend 8 kW to 10 kW system). 
     Keep in mind a hard rule: 1 AC = 5kW, 2AC = 10kW and this goes on
   - Only apply routing thresholds below when a size calculation is actually made or specifically requested:
     * Size < 5 kW: Politely mention minimum installation capacity starts at 5 kW.
     * Size 5 kW to 49 kW: Recommend the kW size range and provide 03138666256 for site survey / quotation.
     * Size >= 50 kW: Identify as a commercial project and direct them to call senior engineers at 03138666255 (Voice Call Only).

5. BILL SCANNING:
   - Ignore total PKR cost/rupees. Look only at the historical monthly units (kWh) table.
   - Calculate average monthly units and recommend system size (Average Units / 120), following the same routing thresholds as above.

6. OUTPUT FORMATTING:
   - Output ONLY the conversational reply text. Do not include any signature, name, disclaimers, or metadata at the end (the backend appends the signature automatically).
"""

# Regex ranges: Arabic/Urdu script block + Devanagari block
FORBIDDEN_SCRIPT_PATTERN = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u0900-\u097F]')


def contains_forbidden_script(text: str) -> bool:
    return bool(FORBIDDEN_SCRIPT_PATTERN.search(text))


def strip_forbidden_script(text: str) -> str:
    """Last-resort fallback: remove any stray non-Latin characters."""
    return FORBIDDEN_SCRIPT_PATTERN.sub('', text)


def format_signature(reply_text: str) -> str:
    """Appends 'Sleek Bot' after a blank line (double newline)."""
    text = reply_text.strip()
    if text.endswith("Sleek Bot"):
        text = text.rsplit("Sleek Bot", 1)[0].strip()
    return f"{text}\n\nSleek Bot"


def call_openai(messages, max_retries=2):
    """
    Calls the OpenAI chat completion endpoint with:
      - low temperature for consistent tone/rule-following
      - a script-safety retry: if the model slips into Devanagari/Urdu script,
        we retry once with an explicit correction instruction before falling
        back to stripping the characters.
    """
    last_reply = None
    for attempt in range(max_retries):
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.4,
        )
        reply = response.choices[0].message.content.strip()
        last_reply = reply

        if not contains_forbidden_script(reply):
            return reply

        logger.warning("Forbidden script detected in model output (attempt %s). Retrying.", attempt + 1)
        messages = messages + [
            {"role": "assistant", "content": reply},
            {"role": "user", "content": (
                "SYSTEM CORRECTION: Your last reply contained native Urdu/Arabic or "
                "Devanagari script, which is strictly forbidden. Rewrite your entire "
                "previous reply using ONLY Latin/English alphabet letters (Roman Urdu "
                "or English), with the same meaning."
            )}
        ]

    # Fallback if the model still won't comply after retries
    logger.error("Model repeatedly returned forbidden script. Stripping characters as fallback.")
    return strip_forbidden_script(last_reply)


def send_whatsapp_message(to_number, text):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text}
    }
    try:
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=15)
        if resp.status_code >= 400:
            logger.error("WhatsApp send failed (%s): %s", resp.status_code, resp.text)
    except requests.RequestException as e:
        logger.error("WhatsApp send exception: %s", e)


def analyze_bill_image(media_id, sender_phone):
    """Background task to analyze a bill image using conversation context."""
    try:
        media_url_req = requests.get(f"https://graph.facebook.com/v18.0/{media_id}", headers=HEADERS, timeout=15)
        media_url = media_url_req.json().get('url')

        if not media_url:
            send_whatsapp_message(
                sender_phone,
                format_signature("Bill scan nahi ho saka. Baraye meherbani saaf tasweer dobara bhejein.")
            )
            return

        image_req = requests.get(media_url, headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}, timeout=15)

        import base64
        base64_image = base64.b64encode(image_req.content).decode('utf-8')

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if sender_phone in chat_history:
            messages.extend(chat_history[sender_phone])

        image_instruction = (
            "TASK: Examine this electricity bill image. Ignore PKR costs. Find the "
            "historical monthly units table, calculate the average monthly units, "
            "divide by 120 to recommend the kW system size, and apply the routing "
            "rules. Reply strictly in the user's language, following all script rules."
        )
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": image_instruction},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]
        })

        raw_reply = call_openai(messages)

        add_to_history(sender_phone, "user", "[User sent an electricity bill photo]")
        add_to_history(sender_phone, "assistant", raw_reply)

        send_whatsapp_message(sender_phone, format_signature(raw_reply))

    except Exception as e:
        logger.exception("Vision processing error: %s", e)
        send_whatsapp_message(
            sender_phone,
            format_signature("Apka bill process karne mein masla aya hai. Baraye meherbani saaf tasweer dobara bhejein.")
        )


def get_text_response(msg_text, sender_phone):
    """Background task for text messages using conversation context."""
    try:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if sender_phone in chat_history:
            messages.extend(chat_history[sender_phone])

        messages.append({"role": "user", "content": f'USER MESSAGE: "{msg_text}"'})

        raw_reply = call_openai(messages)

        add_to_history(sender_phone, "user", msg_text)
        add_to_history(sender_phone, "assistant", raw_reply)

        send_whatsapp_message(sender_phone, format_signature(raw_reply))

    except Exception as e:
        logger.exception("Text processing error: %s", e)
        send_whatsapp_message(
            sender_phone,
            format_signature("Aap ke paigham ka jawab dene mein dushwari pesh aai hai. Baraye meherbani dobara koshish karein.")
        )


def process_webhook_entry(body):
    """Handles webhook message processing asynchronously."""
    try:
        entry = body['entry'][0]['changes'][0]['value']
        if 'messages' not in entry:
            return

        message = entry['messages'][0]
        sender_phone = message['from']
        msg_type = message['type']

        if msg_type == 'image':
            media_id = message['image']['id']
            send_whatsapp_message(sender_phone, format_signature("📄 Apka bill analyze ho raha hai... Baraye meherbani intizar karein."))
            analyze_bill_image(media_id, sender_phone)

        elif msg_type == 'text':
            msg_text = message['text']['body']
            get_text_response(msg_text, sender_phone)

    except (KeyError, IndexError) as e:
        # Common for status/delivery-receipt webhooks that don't contain messages
        logger.info("Webhook entry skipped (no message payload): %s", e)
    except Exception as e:
        logger.exception("Webhook execution error: %s", e)


@app.get("/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return Response(content=challenge, media_type="text/plain")
    return Response(content="Invalid verify token", status_code=403)


@app.post("/webhook")
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    background_tasks.add_task(process_webhook_entry, body)
    return {"status": "ok"}


@app.get("/health")
async def health_check():
    """Simple health check endpoint for uptime monitoring."""
    missing = [name for name, val in [
        ("WHATSAPP_TOKEN", WHATSAPP_TOKEN),
        ("PHONE_NUMBER_ID", PHONE_NUMBER_ID),
        ("VERIFY_TOKEN", VERIFY_TOKEN),
        ("OPENAI_API_KEY", OPENAI_API_KEY),
    ] if not val]
    return {"status": "ok" if not missing else "missing_env_vars", "missing": missing}
