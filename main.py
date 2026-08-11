from fastapi import FastAPI, Request, Response
import requests
import base64
import os
import re
from openai import OpenAI
from datetime import datetime, time
import json

app = FastAPI()

# Retrieve keys securely from environment variables
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")

# Set up the OpenAI client (using gpt-4o-mini)
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
)

HEADERS = {
    "Authorization": f"Bearer {WHATSAPP_TOKEN}",
    "Content-Type": "application/json"
}

# Time restrictions: only respond between 6pm (18:00) and 9am (09:00)
ALLOWED_START_HOUR = 18  # 6pm
ALLOWED_END_HOUR = 9     # 9am (next day)

# Storage for tracking (in production, use a database)
# Format: {"phone_number": {"name": str, "location": str, "timestamp": str}}
site_visit_requests = {}
# Track site visit conversation state: {"phone_number": "step" where step is "awaiting_name", "awaiting_location", or "completed"}
site_visit_state = {}
# Numbers that messaged outside allowed hours (to be summarized at 9am)
overnight_messages = set()
# Flag to track if we've already sent the 9am summary for today
summary_sent_today = False

# PDF file mapping for quotations
QUOTATION_PDFS = {
    "5kw": "5kW Hybrid Quotation.pdf",
    "6kw": "6kW Hybrid Quotation.pdf",
    "8kw": "8kW Hybrid Quotation.pdf",
    "10kw": "10kW Hybrid Quotation.pdf",
}

BATTERY_PDF = "batteries_price.pdf"
DISTRIBUTOR_PDF = "distributors.pdf"

# Battery sizes we offer
BATTERY_SIZES = ['6', '8', '10', '16']

def detect_quotation_request(text):
    """Detect if user is asking for a system quotation vs battery price"""
    text_lower = text.lower()

    # Check for system quotation keywords
    system_keywords = ['system', 'quotation', 'quote', 'price', 'cost', 'kit', 'complete', 'setup', 'installation', 'hybrid system', 'solar system']
    battery_keywords = ['battery', 'batteries', 'storage', 'kwh', 'kwhr', 'backup', 'lithium']

    # Extract kW/kWh mentions
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

def detect_distributor_inquiry(text):
    """Detect if user is asking about distributorship"""
    distributor_keywords = ['distributor', 'dealership', 'dealer', 'partnership', 'wholesale', 'distributer', 'distributorship']
    return any(kw in text.lower() for kw in distributor_keywords)

def detect_loan_inquiry(text):
    """Detect if user is asking about loan/financing"""
    loan_keywords = ['loan', 'financing', 'finance', 'installment', 'installments', 'emi', 'js bank', 'bank', 'loan facility']
    return any(kw in text.lower() for kw in loan_keywords)

# Master Business Knowledge & Behavior Rules Prompt
SYSTEM_PROMPT = """
You are an expert, courteous, and highly professional AI customer assistant for Sleek Solar International (Pvt) Ltd.

CORE OUTPUT RULES:
1. DIRECT REPLIES ONLY: Answer ONLY what the user asked. DO NOT dump general policies, minimum capacity rules, or contact numbers UNLESS specifically asked.
2. SYSTEM SIGNATURE: Every single output MUST end with a blank line followed by 'Sleek Bot' at the very end.
3. CLEAN OUTPUT: Never output safety ratings, JSON code, or system logs. Output ONLY the conversational message meant for WhatsApp.
4. LANGUAGE & TONE:
   - If the user writes in English, respond in clear professional English ONLY.
   - If the user writes in Roman Urdu (Urdu written in English letters), respond in elegant, grammatically correct Roman Urdu ONLY (use "Aap", "Kiya", "Humari", "Guzarish", etc.).
   - NEVER use native Urdu script, Arabic script, or any other language.
   - Match the user's language exactly even if they mix English and Roman Urdu. Do NOT switch languages. Only switch languagewhen user switches.
5. RESPONSE STYLE: Be extremely concise, specific to client's need only. Do not add extra information the user didn't ask for. Do not cite products/brands not mentioned by user.
6. BRANDS/PRODUCTS: Only mention these approved brands when relevant:
   - Solar Panels: Canadian Solar, Jinko, Longi, Risen (580W-740W Bifacial, 30 Years Warranty)
   - Inverters: Huawei, Maxpower, SAJ, Solis, GoodWe, Inverex (5kW-110kW Hybrid, 5 Years Warranty)
   - Batteries: Sleek Solar Lithium-Ion (6kWh, 8kWh, 10kWh, 16kWh)
7. PRICING: NEVER state any price/cost/rupee figure in text. PDFs handle pricing.
8. LOAN: If asked about loan/financing/installment, say: "Loaning can be done through JS Bank."
9. SYSTEM SIZING:
   - When user asks for solar/system for their house, FIRST ask for their monthly average electricity units (kWh).
   - Calculate recommended kW using: Monthly Average Units / 120 = Recommended System kW.
   - When user provides appliances information, calculate using 1 ac = 5kW system rule. Also keep other appliances in count while calculating the total system size required.
   - Reference rule for validation: 1.5 Ton AC ≈ 5kW system. Use this to cross-check if user mentions ACs.
   - Do NOT assume AC count or calculate solely on ACs unless user provides that info.
   - Suggest appropriate system from 5kW, 6kW, 8kW, 10kW options based on calculation.
   - Write response with proper spacing, do not dump everything in one paragraph. Use line breaks for clarity.

10. UNKNOWN INFO: If you don't know something, do not guess. Do not provide the information.
11. EXACT QUOTATION: Only after site visit.
"""

def is_within_allowed_hours():
    """Check if current time is within allowed response hours (6pm-9am)"""
    now = datetime.now().time()
    start_time = time(ALLOWED_START_HOUR, 0)  # 6:00 PM
    end_time = time(ALLOWED_END_HOUR, 0)      # 9:00 AM

    # Handle overnight period (6pm to 9am next day)
    if ALLOWED_START_HOUR > ALLOWED_END_HOUR:
        return now >= start_time or now <= end_time
    else:
        return start_time <= now <= end_time

def should_store_and_defer_response():
    """Check if we should store the message and defer response (outside allowed hours)"""
    if not is_within_allowed_hours():
        # Reset daily summary flag if it's a new day (after 9am)
        now = datetime.now()
        if now.hour >= ALLOWED_END_HOUR and summary_sent_today:
            global summary_sent_today
            summary_sent_today = False
        return True
    return False

def store_overnight_message(sender_phone):
    """Store a sender's number for the overnight summary"""
    overnight_messages.add(sender_phone)

def send_overnight_summary(author_number):
    """Send a summary of overnight messages to the author"""
    global summary_sent_today
    if not overnight_messages or summary_sent_today:
        return

    if len(overnight_messages) == 0:
        return

    message = f"Overnight message summary ({len(overnight_messages)} messages):\n"
    for i, num in enumerate(overnight_messages, 1):
        message += f"{i}. {num}\n"

    send_whatsapp_message(author_number, message)
    summary_sent_today = True
    # Clear the set after sending summary
    overnight_messages.clear()

def detect_site_visit_request(text):
    """Detect if user is asking about or wants to book a site visit"""
    site_visit_keywords = ['site visit', 'site survey', 'visit', 'survey', 'come to', 'come over',
                          'site inspection', 'property visit', 'home visit']
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in site_visit_keywords)

def detect_job_hiring_inquiry(text):
    """Detect if user is asking about job/hiring/career opportunities"""
    job_keywords = ['job', 'hire', 'hiring', 'career', 'vacancy', 'position', 'employment',
                   'work', 'recruitment', 'recruit', 'staff', 'employee', 'opportunity']
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in job_keywords)

def extract_name_and_location(text):
    """Extract name and Google Maps location from text (simplified)"""
    # This is a simplified extraction - in reality, you'd want more sophisticated NLP
    # For now, we'll ask the user to provide these separately
    return None, None

def analyze_bill_image(media_id):
    """Downloads image and asks OpenAI to read the electricity bill"""
    try:
        # 1. Fetch Media URL from Meta
        media_url_req = requests.get(f"https://graph.facebook.com/v18.0/{media_id}", headers=HEADERS)
        media_url = media_url_req.json().get('url')

        if not media_url:
            return "Bill scan failed. Please re-send a clear photo of your electricity bill.\n\nSleek Bot"

        # 2. Download Image Bytes
        image_req = requests.get(media_url, headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"})
        base64_image = base64.b64encode(image_req.content).decode('utf-8')

        prompt = f"""{SYSTEM_PROMPT}

TASK:
Examine this electricity bill image carefully.
1. Extract the monthly consumed units from the bill.
2. Calculate the required system size using: Monthly Average Units / 120 = Recommended System kW.
3. Reference rule for validation: 1.5 Ton AC ≈ 5kW system.
4. Recommend appropriate system size from 5kW, 6kW, 8kW, 10kW options based on calculation.
5. Reply in user's language (English or Roman Urdu only).
6. Be extremely concise and specific.
7. Do NOT mention any prices.
8. Ensure the message ends with a blank line then 'Sleek Bot'."""

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

        # Enforce suffix with blank line
        if not reply.endswith("Sleek Bot"):
            reply = reply + "\n\nSleek Bot"
        return reply

    except Exception as e:
        print(f"Vision Processing Error: {e}")
        return "Apka bill process nahi ho saka. Baraye meherbani saaf tasweer dobara bhejein.\n\nSleek Bot"

def get_text_response(msg_text):
    """Handles text messages and Roman Urdu using AI"""
    try:
        prompt = f"""{SYSTEM_PROMPT}

USER MESSAGE: "{msg_text}"

TASK:
Provide a clear, direct, polite, and extremely concise answer.
- If user asks for solar/system for house: ask for monthly average units (kWh) first, then calculate using Monthly Units / 120 = Recommended kW.
- If user provides units or appliances: calculate using Monthly Units / 120, cross-check with AC rule (1.5 Ton AC ≈ 5kW).
- Suggest appropriate system (5kW, 6kW, 8kW, 10kW) based on calculation.
- Do NOT provide any prices.
- Do NOT mention brands/products user didn't ask about.
- Match user's language (English or Roman Urdu only).
- If you don't know something, don't guess - don't provide it.
- Ensure the message ends with a blank line then 'Sleek Bot'."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        reply = response.choices[0].message.content.strip()

        # Enforce suffix with blank line
        if not reply.endswith("Sleek Bot"):
            reply = reply + "\n\nSleek Bot"
        return reply

    except Exception as e:
        print(f"Text Processing Error: {e}")
        return "Aap ke paigham ka jawab dene mein dushwari pesh aai hai. Baraye meherbani dobara koshish karein.\n\nSleek Bot"

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
    if not os.path.exists(document_path):
        print(f"PDF not found: {document_path}")
        return

    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
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

            if msg_type == 'image':
                media_id = message['image']['id']
                send_whatsapp_message(sender_phone, "📄 Apka bill analyze ho raha hai... Baraye meherbani intizar karein.\n\nSleek Bot")
                reply_text = analyze_bill_image(media_id)
                send_whatsapp_message(sender_phone, reply_text)

            elif msg_type == 'text':
                msg_text = message['text']['body']

                # Check for job/hiring inquiry - handle anytime
                if detect_job_hiring_inquiry(msg_text):
                    send_whatsapp_message(sender_phone, "Please mail your CV at hr@sleeksolar.com. Our team will look into it.\n\nSleek Bot")
                    return {"status": "ok"}

                # Check if we're within allowed hours for responses (6pm-9am)
                if not is_within_allowed_hours():
                    # Outside allowed hours - store for overnight summary but don't respond
                    store_overnight_message(sender_phone)
                    return {"status": "ok"}

                # Check for loan/financing inquiry
                if detect_loan_inquiry(msg_text):
                    send_whatsapp_message(sender_phone, "Loaning can be done through JS Bank.\n\nSleek Bot")

                # Check for distributor inquiry
                elif detect_distributor_inquiry(msg_text):
                    send_whatsapp_message(sender_phone,
                        "Shukriya! Aap ki dilchaspi ke liye. Humari distributor policy aur details is PDF mein hain. Baraye meherbani check karein aur humein batayen ke aap ka business kya hai aur kis area mein kaam karte hain? 🤝\n\nSleek Bot")
                    if os.path.exists(DISTRIBUTOR_PDF):
                        send_document(sender_phone, DISTRIBUTOR_PDF, "Sleek Solar Distributor Information")
                    else:
                        send_whatsapp_message(sender_phone, "PDF currently unavailable. Team se contact karein.\n\nSleek Bot")

                # Check for quotation/battery requests
                else:
                    req_type, size = detect_quotation_request(msg_text)
                    if req_type == 'system' and size in ['5', '6', '8', '10']:
                        kw_key = f"{size}kw"
                        pdf_file = QUOTATION_PDFS.get(kw_key)
                        if pdf_file and os.path.exists(pdf_file):
                            send_whatsapp_message(sender_phone,
                                f"Yahan {size}kW hybrid system ki standard quotation share kar raha hoon. Exact quotation site visit ke baad provide ki jayegi.\n\nSleek Bot")
                            send_document(sender_phone, pdf_file, f"Sleek Solar {size}kW Hybrid System Quotation")
                        else:
                            send_whatsapp_message(sender_phone,
                                f"{size}kW hybrid system ki quotation ke liye humari team se 0313-8666256 par contact karein.\n\nSleek Bot")

                    elif req_type == 'battery' and size in BATTERY_SIZES:
                        if os.path.exists(BATTERY_PDF):
                            send_whatsapp_message(sender_phone,
                                f"Yahan {size}kWh lithium battery ki price list share kar raha hoon.\n\nSleek Bot")
                            send_document(sender_phone, BATTERY_PDF, f"Sleek Solar {size}kWh Battery Price List")
                        else:
                            send_whatsapp_message(sender_phone,
                                "Battery pricing ke liye humari team se 0313-8666256 par contact karein.\n\nSleek Bot")

                    else:
                        # Default AI response
                        reply_text = get_text_response(msg_text)
                        send_whatsapp_message(sender_phone, reply_text)
    except Exception as e:
        print(f"Webhook Execution Error: {e}")
    return {"status": "ok"}