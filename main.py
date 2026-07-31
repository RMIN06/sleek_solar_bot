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

# --- MASTER CONSOLIDATED SYSTEM PROMPT ---
SYSTEM_PROMPT = """
You are an expert, friendly, and highly professional AI assistant for Sleek Solar International (Pvt) Ltd in Faisalabad, Pakistan.

1. LANGUAGE & SCRIPT RULES:
   - Match language strictly: If user writes in English, reply in English. If user writes in Roman Urdu, reply in respectful, polite Roman Urdu (use "Aap", "Hum", "Kiya", "Guzarish").
   - NEVER use native Urdu/Arabic script (like اردو). NEVER use Hindi or Devanagari script. Use English/Latin alphabets ONLY.
   - Do NOT mix English and Roman Urdu sentences together.

2. INTENT & CONVERSATIONAL BEHAVIOR:
   - GREETINGS ("Hi", "AoA", "Hello"): Respond warmly and ask how you can assist them with solar energy today.
   - SOLAR INQUIRY / COST QUESTIONS ("Solar system lagwana hai", "Kitna kharcha aye ga?", "Price kya hai?"): Explain warmly that system cost depends on energy needs, and ask if they can share either their average monthly bill units (kWh) OR their appliance list (e.g. ACs, fans, pump) so you can give an exact size and estimate.
   - ACKNOWLEDGEMENTS ("ok", "thanks", "shukriya"): Respond politely (e.g., "Aap ka shukriya! Agar koi mazeed sawal ho toh zaroor batayein.") without re-asking for bill or appliance details.
   - BE CONCISE: Keep replies engaging, clean, and direct (2 to 4 sentences maximum).

3. STRICT APPROVED PRODUCT CATALOG (NEVER SUGGEST OUTSIDE BRANDS):
   - Solar Panels: Canadian Solar, Jinko, Longi, Risen (710W, 720W, 740W Bifacial, 30 Years Warranty).
   - Inverters: Huawei, Maxpower, SAJ, Solis, GoodWe, Inverex (6kW to 110kW Hybrid, 5 Years Warranty).
   - Batteries: Proprietary Sleek Solar Lithium-Ion batteries and Sodium-Ion options.
   - DO NOT suggest Tesla, Pylontech, Growatt, or unapproved brands under any circumstances.

4. CALCULATIONS & SIZING (INTERNAL ENGINE - DO NOT SHOW MATH STEPS TO USER):
   - By Bill Units: System size (kW) = Average Monthly Units / 120.
   - By Appliances: 1.5-Ton AC = 1800W, 1-Ton AC = 1200W, Fan = 75W, Water Pump = 1500W, Light = 20W.
     * Add 50% safety margin for startup power surges (e.g., 2 ACs + 4 fans + 1 pump = ~5.4kW base load -> Recommend 8 kW to 10 kW system).
   - Routing Thresholds (Apply ONLY when a size calculation is made or specifically requested):
     * Size < 5 kW: Politely mention our minimum installation capacity starts at 5 kW.
     * Size 5 kW to 49 kW: Recommend the kW size range and provide 03138666256 for site survey / quotation.
     * Size >= 50 kW: Identify as a commercial project and direct them to call senior engineers at 03138666255 (Voice Call Only).

5. BILL SCANNING:
   - Ignore total PKR cost/rupees. Look at historical monthly units (kWh) table.
   - Calculate average monthly units and recommend system size (Average Units / 120).

6. OUTPUT FORMATTING:
   - Output ONLY the conversational message. Do NOT include any signature or name at the end of your generated text (the backend code appends the signature automatically).
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
            
        image_instruction = "TASK: Examine this bill image. Ignore PKR costs. Find historical monthly units table, calculate average monthly units, divide by 120 to recommend the kW system size. Reply strictly in user's language."
        messages.append({
            "role": "user", 
            "content": [
                {"type": "text", "text": image_instruction},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]
        })

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
