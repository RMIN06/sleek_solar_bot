import os
<<<<<<< HEAD
import json
from datetime import datetime, time, timedelta
=======
import re
import collections
import logging
from fastapi import FastAPI, Request, Response, BackgroundTasks
import requests
>>>>>>> 427234097c79ea1489b15fc20ff9097fa7654719
from openai import OpenAI
import asyncio

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
app = FastAPI()

<<<<<<< HEAD
# Retrieve keys securely from environment variables
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
AUTHOR_NUMBER = os.environ.get("AUTHOR_NUMBER")  # Your WhatsApp number to receive daily report

# Set up the OpenAI client (using gpt-4o-mini)
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
)
=======
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("sleek-bot")

WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# gpt-4o follows strict script/business rules more reliably than gpt-4o-mini
# once the conversation gets long. Override via env var without touching code.
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# Path to the Lithium-Ion battery price-list PDF that gets sent to customers
# who ask for battery pricing. NOTE: no PDF was actually provided in chat --
# only the company-details image came through. Put your real PDF file here
# (or point this env var at it) before deploying.
LITHIUM_PDF_PATH = os.environ.get("LITHIUM_PDF_PATH", "batteries_price.pdf")

client = OpenAI(api_key=OPENAI_API_KEY)
>>>>>>> 427234097c79ea1489b15fc20ff9097fa7654719

HEADERS = {
    "Authorization": f"Bearer {WHATSAPP_TOKEN}",
    "Content-Type": "application/json"
}

<<<<<<< HEAD
# Default Hybrid System Quotations (Rough Estimates)
HYBRID_QUOTATIONS = {
    "5kw": {
        "system": "5kW Hybrid Solar System",
        "components": [
            "5kW Hybrid Inverter (Huawei/Maxpower/Solis/GoodWe)",
            "8-10 x 580W+ Tier-1 Solar Panels (Canadian Solar/Jinko/Longi/Risen)",
            "Mounting Structure & Wiring",
            "Installation & Commissioning"
        ],
        "price_range": "PKR 650,000 - 750,000",
        "note": "Exact quotation after site visit. Battery storage sold separately."
    },
    "6kw": {
        "system": "6kW Hybrid Solar System",
        "components": [
            "6kW Hybrid Inverter (Huawei/Maxpower/Solis/GoodWe)",
            "10-12 x 580W+ Tier-1 Solar Panels (Canadian Solar/Jinko/Longi/Risen)",
            "Mounting Structure & Wiring",
            "Installation & Commissioning"
        ],
        "price_range": "PKR 750,000 - 850,000",
        "note": "Exact quotation after site visit. Battery storage sold separately."
    },
    "8kw": {
        "system": "8kW Hybrid Solar System",
        "components": [
            "8kW Hybrid Inverter (Huawei/Maxpower/Solis/GoodWe)",
            "14-16 x 580W+ Tier-1 Solar Panels (Canadian Solar/Jinko/Longi/Risen)",
            "Mounting Structure & Wiring",
            "Installation & Commissioning"
        ],
        "price_range": "PKR 950,000 - 1,100,000",
        "note": "Exact quotation after site visit. Battery storage sold separately."
    },
    "10kw": {
        "system": "10kW Hybrid Solar System",
        "components": [
            "10kW Hybrid Inverter (Huawei/Maxpower/Solis/GoodWe)",
            "18-20 x 580W+ Tier-1 Solar Panels (Canadian Solar/Jinko/Longi/Risen)",
            "Mounting Structure & Wiring",
            "Installation & Commissioning"
        ],
        "price_range": "PKR 1,200,000 - 1,400,000",
        "note": "Exact quotation after site visit. Battery storage sold separately."
    }
}

# Battery Price Reference (from batteries_price.pdf)
BATTERY_INFO = {
    "5kwh": "Sleek Solar 5kWh Lithium Battery: ~PKR 180,000 - 200,000",
    "6kwh": "Sleek Solar 6kWh Lithium Battery: ~PKR 210,000 - 230,000",
    "8kwh": "Sleek Solar 8kWh Lithium Battery: ~PKR 270,000 - 300,000",
    "10kwh": "Sleek Solar 10kWh Lithium Battery: ~PKR 330,000 - 360,000",
    "12kwh": "Sleek Solar 12kWh Lithium Battery: ~PKR 390,000 - 420,000",
    "15kwh": "Sleek Solar 15kWh Lithium Battery: ~PKR 480,000 - 520,000",
    "20kwh": "Sleek Solar 20kWh Lithium Battery: ~PKR 620,000 - 680,000",
}

# Track numbers messaged during bot hours (6 PM - 9 AM)
bot_hour_contacts = set()
contacts_file = "bot_hour_contacts.json"

def load_contacts():
    global bot_hour_contacts
    try:
        with open(contacts_file, 'r') as f:
            data = json.load(f)
            bot_hour_contacts = set(data.get('contacts', []))
    except:
        bot_hour_contacts = set()

def save_contacts():
    with open(contacts_file, 'w') as f:
        json.dump({'contacts': list(bot_hour_contacts)}, f)

def is_bot_active_hours():
    """Check if current time is between 6 PM and 9 AM"""
    now = datetime.now().time()
    return now >= time(18, 0) or now <= time(9, 0)

def format_quotation(kw_key):
    """Format a quotation response for a specific kW system"""
    if kw_key not in HYBRID_QUOTATIONS:
        return None
    q = HYBRID_QUOTATIONS[kw_key]
    lines = [f"📋 *{q['system']} (Rough Estimate)*"]
    lines.append(f"💰 *Price Range:* {q['price_range']}")
    lines.append("📦 *Includes:*")
    for comp in q['components']:
        lines.append(f"  • {comp}")
    lines.append(f"\n📝 *Note:* {q['note']}")
    lines.append("\n🏠 For exact quotation, we'll schedule a site visit.")
    return "\n".join(lines)

def format_battery_price(kwh_key):
    """Format battery price response"""
    key = kwh_key.lower().replace(" ", "")
    if key in BATTERY_INFO:
        return f"🔋 *Battery Price:*\n{BATTERY_INFO[key]}\n\n📝 Prices are indicative. Exact cost confirmed after site visit."
    return None

def detect_quotation_request(text):
    """Detect if user is asking for a system quotation vs battery price"""
    text_lower = text.lower()

    # Check for system quotation keywords
    system_keywords = ['system', 'quotation', 'quote', 'price', 'cost', 'kit', 'complete', 'setup', 'installation', 'hybrid system', 'solar system']
    battery_keywords = ['battery', 'batteries', 'storage', 'kwh', 'kwhr', 'backup', 'lithium', 'sodium']

    # Extract kW/kWh mentions
    import re
    kw_matches = re.findall(r'(\d+)\s*kw\b', text_lower)
    kwh_matches = re.findall(r'(\d+)\s*kwh\b', text_lower)

    # Determine intent
    is_system_query = any(kw in text_lower for kw in system_keywords)
    is_battery_query = any(kw in text_lower for kw in battery_keywords)

    # If explicitly mentions kWh, it's battery
    if kwh_matches:
        return 'battery', kwh_matches[0]

    # If mentions kW and system keywords, it's system
    if kw_matches and is_system_query:
        return 'system', kw_matches[0]

    # If just mentions kW without context, check for battery words
    if kw_matches and is_battery_query:
        return 'battery', kw_matches[0]

    if kw_matches:
        return 'system', kw_matches[0]

    return None, None

# Master Business Knowledge & Behavior Rules Prompt
SYSTEM_PROMPT = """
You are an expert, courteous, and highly professional AI customer assistant for Sleek Solar International (Pvt) Ltd.

CORE OUTPUT RULES:
1. DIRECT REPLIES ONLY: Answer ONLY what the user asked. DO NOT dump general policies, minimum capacity rules, or contact numbers UNLESS specifically asked.
2. SYSTEM SIGNATURE: Every single output MUST end with a space followed by 'Sleek Bot' at the very end.
3. CLEAN OUTPUT: Never output safety ratings, JSON code, or system logs. Output ONLY the conversational message meant for WhatsApp.
4. LANGUAGE & TONE: Use crisp, polite, and professional language.
   - If the user writes in Roman Urdu, respond in elegant, grammatically correct Roman Urdu (use "Aap", "Kiya", "Humari", "Guzarish", etc.).
   - If in English, respond in clear professional English.
5. FORMATTING: Use structured bullet points and clean spacing when providing lists of products.
6. KEEP REPLIES ENGAGING, SHORT AND SPECIFIC.

BUSINESS DATA:
- Company Name: Sleek Solar International (Pvt) Ltd
- Office Location: 622-A Peoples Colony No-1, Near Iram Park, Faisalabad
- Office Timings: 9:30 AM to 6:00 PM

PRODUCTS CATALOGUE:
- Solar Panels: Canadian Solar, Jinko, Longi, Risen (580W-740W Bifacial technology with 30 Years Warranty).
- Inverters: Huawei, Maxpower, SAJ, Solis, GoodWe, Inverex (Sizes: 5kW, 6kW, 8kW, 10kW, 15kW, 20kW up to 110kW Hybrid inverters with 5 Years Warranty).
- Batteries: Proprietary Sleek Solar Lithium-Ion batteries (5kWh to 20kWh), Sodium-Ion options.

SIZING & CALCULATION ENGINE:
- Calculation by Bill Units: Recommended kW = (Monthly Units / 120).
- Calculation by Load/Appliances:
  * Air Conditioner (1.5 Ton) = 1800W
  * Fan = 75W
  * Water Motor / Pump = 1500W
  * Light = 20W
  * Calculate running load, add a 50% safety/surge margin to handle motor startup power so system won't trip.
  * Example: 2 ACs (3600W) + 4 Fans (300W) + 1 Motor (1500W) = 5400W base load -> Recommend an 8 kW to 10 kW system.

QUOTATION HANDLING (Handled by system, not AI):
- Default hybrid quotations available for 5kW, 6kW, 8kW, 10kW systems
- Battery prices available for 5kWh to 20kWh
- Exact quotations only after site visit
- System handles 6kW system vs 6kWh battery differentiation automatically

DISTRIBUTOR INQUIRIES:
- If user asks about becoming a distributor, dealership, partnership, or wholesale
- Politely share distributors.pdf and ask about their business background
- Keep it professional and engaging

COMMERCIAL PROJECTS:
- Handle all sizes (no upper limit restriction)
- For large projects, provide guidance and offer site visit
"""

def analyze_bill_image(media_id):
    """Downloads image and asks OpenRouter to read the electricity bill"""
    try:
        # 1. Fetch Media URL from Meta
        media_url_req = requests.get(f"https://graph.facebook.com/v18.0/{media_id}", headers=HEADERS)
        media_url = media_url_req.json().get('url')

        if not media_url:
            return "Bill scan failed. Please re-send a clear photo of your electricity bill. Sleek Bot"

        # 2. Download Image Bytes
        image_req = requests.get(media_url, headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"})
        base64_image = base64.b64encode(image_req.content).decode('utf-8')

        prompt = f"""{SYSTEM_PROMPT}

TASK:
Examine this electricity bill image carefully.
1. Extract the monthly consumed units.
2. Calculate the required system size (Units / 120).
3. Provide the accurate recommendation based on Sizing Rules.
4. Reply in clear, professional Roman Urdu or English depending on context.
5. Keep response engaging, short and specific.
6. Suggest appropriate system size from 5kW, 6kW, 8kW, 10kW options.
Ensure the message ends with ' Sleek Bot'."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ]
        )
        reply = response.choices[0].message.content.strip()

        # Enforce suffix
        if not reply.endswith("Sleek Bot"):
            reply = reply + " Sleek Bot"
        return reply

    except Exception as e:
        print(f"Vision Processing Error: {e}")
        return "Apka bill process nahi ho saka. Baraye meherbani saaf tasweer dobara bhejein. Sleek Bot"

def get_text_response(msg_text):
    """Handles text messages and Roman Urdu using AI"""
    try:
        prompt = f"""{SYSTEM_PROMPT}

USER MESSAGE: "{msg_text}"

TASK:
Provide a clear, direct, polite, and well-formatted answer to the user's message.
- Calculate load/kW if appliances or units are mentioned.
- Suggest appropriate system (5kW, 6kW, 8kW, 10kW) based on calculation.
- Do NOT provide exact prices - system handles quotations separately.
- Do NOT repeat unnecessary policies if not asked.
- Keep replies engaging, short and specific.
- Ensure the message strictly ends with ' Sleek Bot'."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        reply = response.choices[0].message.content.strip()

        # Enforce suffix
        if not reply.endswith("Sleek Bot"):
            reply = reply + " Sleek Bot"
        return reply

    except Exception as e:
        print(f"Text Processing Error: {e}")
        return "Aap ke paigham ka jawab dene mein dushwari pesh aai hai. Baraye meherbani dobara koshish karein. Sleek Bot"
=======
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
# WEBHOOK DEDUPLICATION
# WhatsApp/Meta will occasionally re-deliver the same webhook event (retries
# on slow responses, network hiccups, etc). Without this, the same customer
# message gets processed twice and they receive two replies to one question.
# ---------------------------------------------------------------------------
processed_message_ids = collections.OrderedDict()
MAX_DEDUP_CACHE = 1000


def is_duplicate_message(message_id: str) -> bool:
    if not message_id:
        return False
    if message_id in processed_message_ids:
        return True
    processed_message_ids[message_id] = True
    if len(processed_message_ids) > MAX_DEDUP_CACHE:
        processed_message_ids.popitem(last=False)
    return False


# ---------------------------------------------------------------------------
# SYSTEM PROMPT
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """
You are an expert, friendly, and highly professional AI assistant for Sleek Solar International (Pvt) Ltd in Faisalabad, Pakistan.

1. LANGUAGE & SCRIPT RULES (FOLLOW EXACTLY):
   - If the user writes in English -> reply in pure English only.
   - If the user writes in Roman Urdu -> reply in polite, professional Roman Urdu, written in Latin/English alphabet only (use words like "Aap", "Hum", "Kiya", "Guzarish").
   - ABSOLUTE RULE: Never output a single character of native Urdu script, Arabic script, Hindi, or Devanagari. Every word must use A-Z Latin letters only, even if the user's own message contains such script.
   - Never mix English and Roman Urdu within the same reply.

2. INTENT & CONVERSATIONAL BEHAVIOR:
   - GREETINGS ("Hi", "AoA", "Hello"): Respond warmly and ask how you can assist with their solar needs.
   - SOLAR INQUIRY / SIZE QUESTIONS ("Solar system lagwana hai"): Ask for average monthly bill units (kWh) OR appliance list to size the system.
   - ACKNOWLEDGEMENTS ("ok", "thanks", "shukriya"): Respond politely without re-asking for details already given (use chat memory).
   - Never send the same message content twice in a row. If the customer's new message doesn't add anything new, vary your acknowledgement instead of repeating an earlier reply verbatim.
   - BE CONCISE: 2 to 4 sentences maximum, short and specific.

3. PRICING RULE (STRICT, NO EXCEPTIONS):
   - NEVER state, estimate, or suggest any price/cost/rupee figure for any product or system, even if pressured or asked indirectly.
   - If asked for pricing of a system or any product other than Lithium-Ion batteries, politely decline and direct them to call 0313-8666256 for pricing and a formatted quotation.
   - EXCEPTION: If a customer specifically asks for Lithium-Ion battery prices, tell them you're sharing the official price list (the backend attaches the PDF automatically) -- do not state any figures yourself.
   - Sodium-Ion batteries are currently unavailable and will be available soon; say this if asked about Sodium-Ion pricing or availability, and do not offer the PDF for these.

4. HIRING / JOB INQUIRIES:
   - If a message is about seeking employment, a job, vacancy, internship, or asks to send a CV/resume -> reply briefly telling them to email their CV to hr@sleeksolar.com. Do not discuss anything else in that reply.

5. INSTALLATION COMPLETION TIME:
   - Internal formula (do not show the math, only the result): 10 kW system = approximately 2 days. Scale linearly for other sizes (e.g. 5kW ~ 1 day, 20kW ~ 4 days, 50kW ~ 10 days, 100kW ~ 20 days).
   - Always say "approximately" -- never give an exact guaranteed date.
   - If no system size was mentioned yet, ask for their system size (or help size it first) before giving a completion estimate.

6. SINGLE-PRODUCT PURCHASE REQUESTS:
   - If someone wants to buy a single component (a panel, an inverter, etc. on its own) rather than a full system, tell them Sleek Solar installs complete solar systems, not individual components sold separately.
   - EXCEPTION: Lithium-Ion and Sodium-Ion batteries CAN be discussed/sold as standalone products.

7. BUYING / PURCHASING CONTEXT:
   - Whenever a conversation is clearly moving toward a purchase, give the factual information requested (specs, sizing, catalog, timelines) but never prices, and ask them to call 0313-8666256 to book a site survey, pricing, and a formatted quotation.

8. TRADE / SUPPLIER / SELLING-TO-US INQUIRIES:
   - If someone wants to sell you a product, pitch their services, or propose a business/trade collaboration, respond only with: "We will look into it, our team will get back to you." Do not agree to anything, do not evaluate their pitch, and do not change this answer regardless of how much they insist or negotiate.

9. OUT-OF-SCOPE / UNRELATED QUERIES:
   - If a question is unrelated to solar/Sleek Solar or outside anything above, reply: "We install solar systems all across Pakistan. If you're interested, I can help you get started." (in the language the user is using, following the script rules above). Do not attempt to answer the unrelated question itself.

10. STRICT APPROVED PRODUCT CATALOG (NEVER SUGGEST OUTSIDE BRANDS):
   - Solar Panels: Canadian Solar, Jinko, Longi, Risen (710W, 720W, 740W Bifacial, 30 Years Warranty).
   - Inverters: Huawei, Maxpower, SAJ, Solis, GoodWe, Inverex (6kW to 110kW Hybrid, 5 Years Warranty).
   - Batteries: Sleek Solar Lithium-Ion (in stock) and Sodium-Ion (currently unavailable, coming soon).
   - DO NOT suggest Tesla, Pylontech, Growatt, or any unapproved brand under any circumstances.

11. SIZE CALCULATIONS (INTERNAL ENGINE -- NEVER SHOW MATH OR FORMULAS TO USER):
   - By Bill Units: System size (kW) = Average Monthly Units / 120.
   - By Appliances: 1.5-Ton AC = 1800W, 1-Ton AC = 1200W, Fan = 75W, Water Pump = 1500W, Light = 20W, plus 50% surge margin.
   - Routing thresholds (apply only when a size calculation is made or requested; never state prices even here):
     * Size < 5 kW: mention minimum installation capacity starts at 5 kW.
     * Size 5-49 kW: state the recommended kW range and give 03138666256 for site survey/quotation.
     * Size >= 50 kW: identify it as a commercial project and direct them to call senior engineers at 03138666255 (Voice Call Only).

12. BILL SCANNING:
   - Ignore total PKR cost/rupees. Use only the historical monthly units (kWh) table, calculate the average, divide by 120 for size, and apply the same routing rules and pricing rule above.

13. COMPANY & CONTACT DETAILS (use when asked, or when clearly essential to answer the question -- don't volunteer them otherwise):
   - Company Name: Sleek Solar International (Pvt) Ltd
   - Headquarters: 622-A Peoples Colony No-1, Near Iram Park, Faisalabad
   - Business Hours: 9:30 AM - 6:00 PM
   - General & Quotations Line: 03138666256 (quotations, site surveys, installments)
   - Commercial Projects Line: 03138666255 (Voice Call Only, for systems >= 50 kW)
   - Financing Partner: JS Bank (installment facility available)
   - HR / Careers: hr@sleeksolar.com
   - Website: www.sleeksolar.com

14. WEBSITE-RELATED QUESTIONS (about us, certifications, services -- only answer if asked):
   - About Us: Sleek Solar (Pvt) Ltd is a certified solar energy provider in Pakistan, registered with SECP, licensed by PEC, and approved by AEDB for Net Metering. Restructured in 2013, rebranded in 2017 as Sleek Solar International (Pvt) Ltd, part of the Sleek Group.
   - Certifications: SECP, PEC, AEDB, NEPRA.
   - Services: Residential, Commercial, Industrial, and Agricultural solar systems (5 kW to multi-MW scale), plus solar panel cleaning. End-to-end: consultation, design, installation, Net Metering, and maintenance.
   - If asked something about the company/website you're not confident about, do not guess or invent details -- say you're not certain and point them to www.sleeksolar.com for that specific information.

15. OUTPUT FORMATTING:
   - Output ONLY the conversational reply text, no signature or metadata (the backend appends the signature automatically).
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
        retry once with an explicit correction instruction before falling
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

    logger.error("Model repeatedly returned forbidden script. Stripping characters as fallback.")
    return strip_forbidden_script(last_reply)

>>>>>>> 427234097c79ea1489b15fc20ff9097fa7654719

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


# ---------------------------------------------------------------------------
# LITHIUM-ION BATTERY PRICE-LIST PDF
# ---------------------------------------------------------------------------
_cached_battery_media_id = None

BATTERY_KEYWORDS = ("battery", "batteries")
PRICE_KEYWORDS = ("price", "prices", "cost", "costs", "rate", "rates", "kitna", "kithna", "qeemat", "qeymat")
SODIUM_KEYWORDS = ("sodium",)


def wants_battery_price_pdf(msg_text: str) -> bool:
    """Detects a Lithium-Ion battery pricing question (not Sodium-Ion)."""
    text = msg_text.lower()
    if any(s in text for s in SODIUM_KEYWORDS):
        return False
    return any(b in text for b in BATTERY_KEYWORDS) and any(p in text for p in PRICE_KEYWORDS)


def upload_media_to_whatsapp(file_path):
    """Uploads a local file to WhatsApp's Media API and returns its media_id."""
    if not os.path.exists(file_path):
        logger.error("Battery PDF not found at %s -- cannot send price list.", file_path)
        return None
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/media"
    try:
        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f, "application/pdf")}
            data = {"messaging_product": "whatsapp"}
            upload_headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
            resp = requests.post(url, headers=upload_headers, files=files, data=data, timeout=30)
        if resp.status_code >= 400:
            logger.error("Media upload failed (%s): %s", resp.status_code, resp.text)
            return None
        return resp.json().get("id")
    except requests.RequestException as e:
        logger.error("Media upload exception: %s", e)
        return None


def send_whatsapp_document(to_number, media_id, filename, caption=None):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    document_payload = {"id": media_id, "filename": filename}
    if caption:
        document_payload["caption"] = caption
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "document",
        "document": document_payload
    }
    try:
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=15)
        if resp.status_code >= 400:
            logger.error("WhatsApp document send failed (%s): %s", resp.status_code, resp.text)
    except requests.RequestException as e:
        logger.error("WhatsApp document send exception: %s", e)


def send_battery_price_pdf(to_number):
    """Uploads (if needed) and sends the Lithium-Ion battery price list PDF."""
    global _cached_battery_media_id
    media_id = _cached_battery_media_id or upload_media_to_whatsapp(LITHIUM_PDF_PATH)
    if not media_id:
        # Fallback if the PDF is missing/misconfigured -- don't leave the customer hanging.
        send_whatsapp_message(
            to_number,
            format_signature("Baraye meherbani hamare quotations line 03138666256 par call karein for Lithium-Ion battery pricing.")
        )
        return
    _cached_battery_media_id = media_id
    send_whatsapp_document(to_number, media_id, "Lithium-Ion-Battery-Pricelist.pdf", caption="Sleek Solar Lithium-Ion Battery Price List")


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
            "rules. Never state a price. Reply strictly in the user's language, "
            "following all script rules."
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

        # Lithium-Ion battery pricing gets the actual price-list PDF, not figures in text.
        if wants_battery_price_pdf(msg_text):
            send_battery_price_pdf(sender_phone)

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
        message_id = message.get('id')

        if is_duplicate_message(message_id):
            logger.info("Skipping duplicate webhook delivery for message %s", message_id)
            return

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


def send_document(to_number, document_path, caption=""):
    """Send a PDF/document via WhatsApp"""
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    # First upload the document
    with open(document_path, 'rb') as f:
        files = {'file': (os.path.basename(document_path), f, 'application/pdf')}
        data = {
            'messaging_product': 'whatsapp',
            'type': 'document'
        }
        upload_resp = requests.post(
            f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/media",
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
            files=files,
            data=data
        )

    if upload_resp.status_code == 200:
        media_id = upload_resp.json().get('id')
        # Now send the document
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "document",
            "document": {
                "id": media_id,
                "caption": caption,
                "filename": os.path.basename(document_path)
            }
        }
        requests.post(url, headers=HEADERS, json=payload)

async def send_daily_report():
    """Send daily report of contacts to author at 9 AM"""
    while True:
        now = datetime.now()
        # Calculate next 9 AM
        next_9am = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if now >= next_9am:
            next_9am += timedelta(days=1)

        wait_seconds = (next_9am - now).total_seconds()
        await asyncio.sleep(wait_seconds)

        # Send report
        if bot_hour_contacts and AUTHOR_NUMBER:
            contacts_list = "\n".join([f"• {num}" for num in sorted(bot_hour_contacts)])
            report = f"📊 *Daily Bot Report (6 PM - 9 AM)*\n\nTotal contacts: {len(bot_hour_contacts)}\n\n{contacts_list}\n\n—Sleek Bot"
            send_whatsapp_message(AUTHOR_NUMBER, report)
            # Clear for next day
            bot_hour_contacts.clear()
            save_contacts()

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
<<<<<<< HEAD
    try:
        entry = body['entry'][0]['changes'][0]['value']
        if 'messages' in entry:
            message = entry['messages'][0]
            sender_phone = message['from']
            msg_type = message['type']

            # Track contacts during bot hours
            if is_bot_active_hours():
                bot_hour_contacts.add(sender_phone)
                save_contacts()

            if msg_type == 'image':
                media_id = message['image']['id']
                send_whatsapp_message(sender_phone, "📄 Apka bill analyze ho raha hai... Baraye meherbani intizar karein. Sleek Bot")
                reply_text = analyze_bill_image(media_id)
                send_whatsapp_message(sender_phone, reply_text)

            elif msg_type == 'text':
                msg_text = message['text']['body']

                # Check for distributor inquiry
                distributor_keywords = ['distributor', 'dealership', 'dealer', 'partnership', 'wholesale', 'distributer', 'distributorship']
                if any(kw in msg_text.lower() for kw in distributor_keywords):
                    send_whatsapp_message(sender_phone,
                        "Shukriya! Aap ki dilchaspi ke liye. Humari distributor policy aur details is PDF mein hain. Baraye meherbani check karein aur humein batayen ke aap ka business kya hai aur kis area mein kaam karte hain? 🤝 Sleek Bot")
                    if os.path.exists("distributors.pdf"):
                        send_document(sender_phone, "distributors.pdf", "Sleek Solar Distributor Information")
                    else:
                        send_whatsapp_message(sender_phone, "PDF currently unavailable. Team se contact karein. Sleek Bot")

                # Check for quotation/battery requests
                else:
                    req_type, size = detect_quotation_request(msg_text)
                    if req_type == 'system' and size in ['5', '6', '8', '10']:
                        kw_key = f"{size}kw"
                        quotation = format_quotation(kw_key)
                        if quotation:
                            send_whatsapp_message(sender_phone, quotation + " Sleek Bot")
                    elif req_type == 'battery' and size in ['5', '6', '8', '10', '12', '15', '20']:
                        kwh_key = f"{size}kwh"
                        battery_price = format_battery_price(kwh_key)
                        if battery_price:
                            send_whatsapp_message(sender_phone, battery_price + " Sleek Bot")
                    else:
                        # Default AI response
                        reply_text = get_text_response(msg_text)
                        send_whatsapp_message(sender_phone, reply_text)
    except Exception as e:
        print(f"Webhook Execution Error: {e}")
    return {"status": "ok"}

# Load contacts on startup
load_contacts()

# Start daily report scheduler
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(send_daily_report())
=======
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
    battery_pdf_present = os.path.exists(LITHIUM_PDF_PATH)
    return {
        "status": "ok" if not missing else "missing_env_vars",
        "missing": missing,
        "battery_pdf_found": battery_pdf_present
    }
>>>>>>> 427234097c79ea1489b15fc20ff9097fa7654719
