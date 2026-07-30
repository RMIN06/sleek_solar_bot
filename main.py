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

# --- CONVERSATION MEMORY ---
# This dictionary stores the recent chat history per phone number
chat_history = {}

def add_to_history(phone, role, content):
    if phone not in chat_history:
        chat_history[phone] = []
    chat_history[phone].append({"role": role, "content": content})
    # Keep only the last 10 messages to avoid overloading the memory/prompt
    if len(chat_history[phone]) > 10:
        chat_history[phone] = chat_history[phone][-10:]

# --- STRICT BUSINESS RULES ---
SYSTEM_PROMPT = """
You are an expert, highly professional AI assistant for Sleek Solar International (Pvt) Ltd.

STRICT BEHAVIOR RULES:
1. NO UNNECESSARY CONTACT INFO: Do NOT add the contact number (03138666256) at the end of every message. ONLY provide it if the user specifically asks how to contact, requests an exact quote, or needs a site survey.
2. CONTEXT AWARENESS: You have access to the recent chat history. If a user says "ok", "thanks", or acknowledges a previous calculation, simply reply politely (e.g., "Aap ka shukriya. Agar mazeed kuch poochna ho to batayein."). Do NOT ask for their details or bill again if you already have them.
3. SINGLE LANGUAGE MATCHING (DO NOT MIX):
   - If the user writes in Roman Urdu, reply ONLY in pure Roman Urdu using English/Latin alphabets. NEVER use native Urdu/Arabic script (Urdu letters like اردو). NEVER mix English sentences into Roman Urdu replies.
   - If the user writes in English, reply ONLY in pure English.
4. NO SIGNATURE IN TEXT: Do NOT append any signature or name at the end of your generated text; the system handles the signature automatically.

STRICT ANTI-HALLUCINATION PRODUCT CATALOG:
You must ONLY suggest or mention the exact products listed below. NEVER mention outside brands like Tesla, Pylontech, Growatt, etc. If a customer asks about an unlisted brand, state that we do not carry it and offer our listed alternatives.
- Solar Panels: Canadian Solar, Jinko, Longi, Risen (710W, 720W, 740W Bifacial technology with 30 Years Warranty).
- Inverters: Huawei, Maxpower, SAJ, Solis, GoodWe, Inverex (Sizes: 6kW to 110kW Hybrid inverters with 5 Years Warranty).
- Batteries: Sleek Solar Lithium-Ion batteries.

BILL SCANNING & HISTORICAL UNITS ANALYSIS:
- Do NOT track total money, expenses, or bill amounts in PKR.
- Look specifically at the historical monthly consumption table on the electricity bill (kWh / units consumed in past months).
- Extract the consumed units for all available months shown in the bill table.
- Calculate the average monthly unit consumption = (Sum of visible monthly units / Number of months).
- Calculate recommended system size = (Average Monthly Units / 120).
- If Size < 5 kW: State that our minimum installation capacity starts at 5 kW.
- If Size >= 50 kW: Identify as a commercial project and direct them to call 03138666255 (Voice Call Only).
"""

def format_signature(reply_text: str) -> str:
    """Appends 'Sleek Bot' after a line space."""
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
    """Background task to analyze bill image using context history"""
    try:
        media_url_req = requests.get(f"https://graph.facebook.com/v18.0/{media_id}", headers=HEADERS)
        media_url = media_url_req.json().get('url')
        
        if not media_url:
            send_whatsapp_message(sender_phone, format_signature("Bill scan nahi ho saka. Baraye meherbani saaf tasweer dobara bhejein."))
            return

        image_req = requests.get(media_url, headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"})
        base64_image = base64.b64encode(image_req.content).decode('utf-8')
        
        # Build the message array with history
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if sender_phone in chat_history:
            messages.extend(chat_history[sender_phone])
            
        # Add the image instruction
        image_instruction = "TASK: Examine this bill image. Ignore PKR costs. Find the historical monthly units table, calculate the average monthly units, and divide by 120 to recommend the kW system size. Reply in the user's language."
        messages.append({
            "role": "user", 
            "content": [
                {"type": "text", "text": image_instruction},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]
        })

        response = client.chat.completions.create(
            model="openrouter/free",
            messages=messages
        )
        raw_reply = response.choices[0].message.content.strip()
        
        # Save to history
        add_to_history(sender_phone, "user", "[User sent an electricity bill photo]")
        add_to_history(sender_phone, "assistant", raw_reply)
        
        send_whatsapp_message(sender_phone, format_signature(raw_reply))

    except Exception as e:
        print(f"Vision Processing Error: {e}")
        send_whatsapp_message(sender_phone, format_signature("Apka bill process karne mein masla aya hai. Baraye meherbani saaf tasweer dobara bhejein."))

def get_text_response(msg_text, sender_phone):
    """Background task for text messages using context history"""
    try:
        # Build the message array with history
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if sender_phone in chat_history:
            messages.extend(chat_history[sender_phone])
            
        # Add the new user message
        messages.append({"role": "user", "content": f'USER MESSAGE: "{msg_text}"'})

        response = client.chat.completions.create(
            model="openrouter/free",
            messages=messages
        )
        raw_reply = response.choices[0].message.content.strip()
        
        # Save to history
        add_to_history(sender_phone, "user", msg_text)
        add_to_history(sender_phone, "assistant", raw_reply)
        
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
