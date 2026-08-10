from fastapi import FastAPI, Request, Response
import requests
import base64
import os
import json
from datetime import datetime, time, timedelta
from openai import OpenAI
import asyncio

app = FastAPI()

# Retrieve keys securely from environment variables
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
AUTHOR_NUMBER = os.environ.get("AUTHOR_NUMBER")  # Your WhatsApp number to receive daily report

# Set up the OpenAI client (using gpt-4o-mini)
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
)

HEADERS = {
    "Authorization": f"Bearer {WHATSAPP_TOKEN}",
    "Content-Type": "application/json"
}

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
    """Downloads image and asks OpenAI to read the electricity bill"""
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

def send_whatsapp_message(to_number, text):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text}
    }
    requests.post(url, headers=HEADERS, json=payload)

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
    return {"error": "Invalid token"}

@app.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()
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