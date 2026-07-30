from fastapi import FastAPI, Request, Response, BackgroundTasks
import requests
import base64
import os
from openai import OpenAI

app = FastAPI()

# Environment variables
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

HEADERS = {
    "Authorization": f"Bearer {WHATSAPP_TOKEN}",
    "Content-Type": "application/json"
}

# Strict Business & Language Rules
SYSTEM_PROMPT = """
You are an expert, highly professional AI assistant for Sleek Solar International (Pvt) Ltd.

STRICT LANGUAGE & SCRIPT RULES:
1. SINGLE LANGUAGE MATCHING (DO NOT MIX):
   - If the user writes in Roman Urdu, reply ONLY in pure Roman Urdu using English/Latin alphabets. NEVER use native Urdu/Arabic script (Urdu letters like اردو). NEVER mix English sentences into Roman Urdu replies.
   - If the user writes in English, reply ONLY in pure English. NEVER mix Roman Urdu words into English replies.
2. CONCISE & ENGAGING: Keep responses direct, polite, and short (2 to 4 sentences maximum).
3. NO SIGNATURE IN TEXT: Do NOT append any signature or name at the end of your generated text; the system handles the signature automatically.

BILL SCANNING & HISTORICAL UNITS ANALYSIS:
- Do NOT track total money, expenses, or bill amounts in PKR.
- Look specifically at the historical monthly consumption table on the electricity bill (kWh / units consumed in past months).
- Extract the consumed units for all available months shown in the bill table.
- Calculate the average monthly unit consumption = (Sum of visible monthly units / Number of months).
- Calculate recommended system size = (Average Monthly Units / 120).
- Sizing rules:
  * Size < 5 kW: State that our minimum installation capacity starts at 5 kW.
  * Size 5 kW to 49 kW: Recommend the exact kW system size and suggest calling 03138666256 for a quotation / site survey.
  * Size >= 50 kW: Identify as a commercial project and direct them to call 03138666255 (Voice Call Only).

BUSINESS DATA:
- Company: Sleek Solar International (Pvt) Ltd
- Address: 622-A Peoples Colony No-1, Faisalabad (9:30 AM - 6:00 PM)
- Quotations & Surveys: 03138666256
- Installments: Available through JS Bank.
"""

def format_signature(reply_text: str) -> str:
    """Appends 'Sleek Bot' after a line space (double newline)."""
    text = reply_text.strip()
    if text.endswith("Sleek Bot"):
        text = text.rsplit("Sleek Bot", 1)[0].strip()
    return f"{text}\n\nSleek Bot"

def send_whatsapp_message(to_number, text):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text}
    }
    requests.post(url, headers=HEADERS, json=payload)

def analyze_bill_image(media_id, sender_phone):
    """Background task to analyze bill image for average monthly units"""
    try:
        media_url_req = requests.get(f"https://graph.facebook.com/v18.0/{media_id}", headers=HEADERS)
        media_url = media_url_req.json().get('url')
        
        if not media_url:
            send_whatsapp_message(sender_phone, format_signature("Bill scan nahi ho saka. Baraye meherbani saaf tasweer dobara bhejein."))
            return

        image_req = requests.get(media_url, headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"})
        base64_image = base64.b64encode(image_req.content).decode('utf-8')
        
        prompt = f"""{SYSTEM_PROMPT}

TASK FOR BILL IMAGE:
1. Examine this electricity bill. Ignore rupees/costs entirely.
2. Search for the historical monthly units (kWh) table for past months.
3. Extract the monthly units and calculate the average monthly units consumption.
4. Calculate required solar system size in kW = (Average Monthly Units / 120).
5. State the calculated average monthly units, the recommended kW system size, and next steps clearly.
6. Match the language strictly: Roman Urdu (English alphabet only, NO Urdu script) or English."""

        response = client.chat.completions.create(
            model="openrouter/free",
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]}
            ]
        )
        raw_reply = response.choices[0].message.content.strip()
        send_whatsapp_message(sender_phone, format_signature(raw_reply))

    except Exception as e:
        print(f"Vision Processing Error: {e}")
        send_whatsapp_message(sender_phone, format_signature("Apka bill process karne mein masla aya hai. Baraye meherbani saaf tasweer dobara bhejein."))

def get_text_response(msg_text, sender_phone):
    """Background task for text messages"""
    try:
        prompt = f"""{SYSTEM_PROMPT}

USER MESSAGE: "{msg_text}"

TASK:
- Answer the user's question directly, concisely, and accurately.
- STRICT LANGUAGE RULE:
  * If the user wrote in Roman Urdu -> Reply ONLY in Roman Urdu (English alphabet). Do NOT use English sentences or native Urdu script.
  * If the user wrote in English -> Reply ONLY in English. Do NOT mix Roman Urdu."""

        response = client.chat.completions.create(
            model="openrouter/free",
            messages=[{"role": "user", "content": prompt}]
        )
        raw_reply = response.choices[0].message.content.strip()
        send_whatsapp_message(sender_phone, format_signature(raw_reply))

    except Exception as e:
        print(f"Text Processing Error: {e}")
        send_whatsapp_message(sender_phone, format_signature("Aap ke paigham ka jawab dene mein dushwari pesh aai hai. Baraye meherbani dobara koshish karein."))

def process_webhook_entry(body):
    """Handles webhook message processing asynchronously"""
    try:
        entry = body['entry'][0]['changes'][0]['value']
        if 'messages' in entry:
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
    except Exception as e:
        print(f"Webhook Execution Error: {e}")

@app.get("/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return Response(content=challenge, media_type="text/plain")
    return {"error": "Invalid token"}

@app.post("/webhook")
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    background_tasks.add_task(process_webhook_entry, body)
    return {"status": "ok"}
