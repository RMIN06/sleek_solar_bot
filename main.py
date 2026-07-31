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
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Initialize official OpenAI client
client = OpenAI(
    api_key=OPENAI_API_KEY,
)

HEADERS = {
    "Authorization": f"Bearer {WHATSAPP_TOKEN}",
    "Content-Type": "application/json"
}

# --- CONVERSATION MEMORY ---
chat_history = {}

def add_to_history(phone, role, content):
    if phone not in chat_history:
        chat_history[phone] = []
    chat_history[phone].append({"role": role, "content": content})
    if len(chat_history[phone]) > 10:
        chat_history[phone] = chat_history[phone][-10:]

# --- STRICT BUSINESS RULES ---
SYSTEM_PROMPT = """
You are an AI assistant for Sleek Solar. 

CRITICAL RULES:
1. STRICT LANGUAGE MATCH: 
   - If user asks in English -> Reply ONLY in pure English. 
   - If user asks in Roman Urdu -> Reply ONLY in pure Roman Urdu.
   - NO HINDI. NO DEVANAGARI SCRIPT. NO NATIVE URDU/ARABIC SCRIPT. Use English alphabets only.
2. BE EXTREMELY SHORT & SPECIFIC: Answer ONLY the exact question asked. Maximum 2 sentences. 
3. DO NOT ASK FOR MORE INFO: Do NOT ask for their bill, load, or appliances unless they explicitly ask for a system size or price estimate. If they just say "Hi", just say "Hello, how can I help?".
4. NO UNREQUESTED DATA: Do NOT give phone numbers or minimum kW limits unless directly asked.

STRICT PRODUCT CATALOG (NEVER SUGGEST OTHER BRANDS):
- Solar Panels: Canadian Solar, Jinko, Longi, Risen (710W, 720W, 740W Bifacial).
- Inverters: Huawei, Maxpower, SAJ, Solis, GoodWe, Inverex (6kW to 110kW).
- Batteries: Sleek Solar Lithium-Ion and Sodium-Ion batteries. (NEVER suggest Tesla, Pylontech, or other external brands).

SIZING KNOWLEDGE:
- System Size (kW) = Average Monthly Units / 120.
- Min install: 5 kW. Commercial: 50 kW+.
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
        
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if sender_phone in chat_history:
            messages.extend(chat_history[sender_phone])
            
        image_instruction = "TASK: Examine this bill image. Ignore PKR costs. Find the historical monthly units table, calculate the average monthly units, and divide by 120 to recommend the kW system size. Reply strictly in the user's language."
        messages.append({
            "role": "user", 
            "content": [
                {"type": "text", "text": image_instruction},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]
        })

        # Upgraded to gpt-4o-mini
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )
        raw_reply = response.choices[0].message.content.strip()
        
        add_to_history(sender_phone, "user", "[User sent an electricity bill photo]")
        add_to_history(sender_phone, "assistant", raw_reply)
        
        send_whatsapp_message(sender_phone, format_signature(raw_reply))

    except Exception as e:
        print(f"Vision Processing Error: {e}")
        send_whatsapp_message(sender_phone, format_signature("Apka bill process karne mein masla aya hai. Baraye meherbani saaf tasweer dobara bhejein."))

def get_text_response(msg_text, sender_phone):
    """Background task for text messages using context history"""
    try:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if sender_phone in chat_history:
            messages.extend(chat_history[sender_phone])
            
        messages.append({"role": "user", "content": f'USER MESSAGE: "{msg_text}"'})

        # Upgraded to gpt-4o-mini
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )
        raw_reply = response.choices[0].message.content.strip()
        
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
