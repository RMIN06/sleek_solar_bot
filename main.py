from fastapi import FastAPI, Request, Response, BackgroundTasks
import requests
import base64
import os
from openai import OpenAI

app = FastAPI()

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

# Stricter, shorter prompt
SYSTEM_PROMPT = """
You are an expert, highly professional AI assistant for Sleek Solar International (Pvt) Ltd.

STRICT CONVERSATION RULES:
1. EXTREMELY CONCISE: Keep responses short (1-3 sentences maximum). Do NOT write paragraphs. 
2. ENGAGE THE CUSTOMER: If they ask for a price, do not explain the math or give examples. Simply ask them politely for their monthly units or appliances.
3. DIRECT ANSWERS: Answer only what is asked. Do not list policies, locations, or numbers unless explicitly relevant.
4. NO INTERNAL LOGIC: NEVER show the user the calculation formula (e.g., do not show 1800W + 75W math). 
5. LANGUAGE: Use natural, conversational Roman Urdu (or English if they use it). 
6. SIGNATURE: Every single message MUST end with a space followed exactly by 'Sleek Bot'.

BUSINESS & CALCULATION LOGIC (For your internal calculations only, do not show to customer):
- Min install: 5 kW. Commercial: 50 kW+. 
- Formula: (Units / 120) or Appliances (AC=1800W, Fan=75W, Motor=1500W + 50% margin). 
- Contact for quote: 03138666256. 
"""

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
    """Background task to analyze image"""
    try:
        media_url_req = requests.get(f"https://graph.facebook.com/v18.0/{media_id}", headers=HEADERS)
        media_url = media_url_req.json().get('url')
        
        if not media_url:
            send_whatsapp_message(sender_phone, "Bill scan failed. Please re-send a clear photo. Sleek Bot")
            return

        image_req = requests.get(media_url, headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"})
        base64_image = base64.b64encode(image_req.content).decode('utf-8')
        
        prompt = f"""{SYSTEM_PROMPT}\nTASK: Read this electricity bill. Extract consumed units, calculate the kW system needed (Units / 120), and give a short recommendation. End with ' Sleek Bot'."""

        response = client.chat.completions.create(
            model="openrouter/free",
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]}
            ]
        )
        reply = response.choices[0].message.content.strip()
        if not reply.endswith("Sleek Bot"): reply += " Sleek Bot"
        send_whatsapp_message(sender_phone, reply)

    except Exception as e:
        print(f"Vision Error: {e}")
        send_whatsapp_message(sender_phone, "Apka bill process nahi ho saka. Baraye meherbani saaf tasweer dobara bhejein. Sleek Bot")

def get_text_response(msg_text, sender_phone):
    """Background task for text"""
    try:
        prompt = f"""{SYSTEM_PROMPT}\nUSER: "{msg_text}"\nTASK: Reply shortly and conversationally. End with ' Sleek Bot'."""

        response = client.chat.completions.create(
            model="openrouter/free",
            messages=[{"role": "user", "content": prompt}]
        )
        reply = response.choices[0].message.content.strip()
        if not reply.endswith("Sleek Bot"): reply += " Sleek Bot"
        send_whatsapp_message(sender_phone, reply)

    except Exception as e:
        print(f"Text Error: {e}")
        send_whatsapp_message(sender_phone, "Technical issue, please try again. Sleek Bot")

def process_webhook_entry(body):
    """Handles the actual message processing in the background"""
    try:
        entry = body['entry'][0]['changes'][0]['value']
        if 'messages' in entry:
            message = entry['messages'][0]
            sender_phone = message['from']
            msg_type = message['type']
            
            if msg_type == 'image':
                media_id = message['image']['id']
                send_whatsapp_message(sender_phone, "📄 Apka bill analyze ho raha hai... intizar karein. Sleek Bot")
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
    # Pass the heavy lifting to the background to instantly return 200 OK to Meta
    background_tasks.add_task(process_webhook_entry, body)
    return {"status": "ok"}
