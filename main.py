from fastapi import FastAPI, Request, Response
import requests
import base64
import os
from openai import OpenAI

app = FastAPI()

# Retrieve keys securely from environment variables
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# Set up the OpenRouter AI client
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

HEADERS = {
    "Authorization": f"Bearer {WHATSAPP_TOKEN}",
    "Content-Type": "application/json"
}

# Master Business Knowledge & Behavior Rules Prompt
SYSTEM_PROMPT = """
You are an expert, courteous, and highly professional AI customer assistant for Sleek Solar International (Pvt) Ltd.

CORE OUTPUT RULES:
1. DIRECT REPLIES ONLY: Answer ONLY what the user asked. DO NOT dump general policies, minimum capacity rules, or contact numbers UNLESS specifically asked or relevant to a calculated recommendation.
2. SYSTEM SIGNATURE: Every single output MUST end with a space followed by 'Sleek Bot' at the very end.
3. CLEAN OUTPUT: Never output safety ratings (e.g., 'User Safety: safe'), JSON code, or system logs. Output ONLY the conversational message meant for WhatsApp.
4. LANGUAGE & TONE: Use crisp, polite, and professional language.
   - If the user writes in Roman Urdu, respond in elegant, grammatically correct Roman Urdu (use "Aap", "Kiya", "Humari", "Guzarish", etc.).
   - If in English, respond in clear professional English.
5. FORMATTING: Use structured bullet points and clean spacing when providing lists of products.

BUSINESS DATA:
- Company Name: Sleek Solar International (Pvt) Ltd
- Office Location: 622-A Peoples Colony No-1, Near Iram Park, Faisalabad
- Office Timings: 9:30 AM to 6:00 PM
- Quotations & Site Surveys: Call 03138666256
- Commercial Projects (50 kW+): Call 03138666255 (Voice Call Only)
- Installment Facility: Available through JS Bank. Call 03138666256 for procedure.

PRODUCTS CATALOGUE:
- Solar Panels: Canadian Solar, Jinko, Longi, Risen (710W, 720W, 740W Bifacial technology with 30 Years Warranty).
- Inverters: Huawei, Maxpower, SAJ, Solis, GoodWe, Inverex (Sizes: 6kW, 10kW, 15kW, 20kW up to 110kW Hybrid inverters with 5 Years Warranty).
- Batteries: Proprietary Sleek Solar Lithium-Ion batteries, Sodium-Ion options.

SIZING & CALCULATION ENGINE:
- Calculation by Bill Units: Recommended kW = (Monthly Units / 120).
- Calculation by Load/Appliances:
  * Air Conditioner (1.5 Ton) = 1800W
  * Fan = 75W
  * Water Motor / Pump = 1500W
  * Light = 20W
  * Calculate running load, add a 50% safety/surge margin to handle motor startup power so system won't trip.
  * Example: 2 ACs (3600W) + 4 Fans (300W) + 1 Motor (1500W) = 5400W base load -> Recommend an 8 kW to 10 kW system.
- Threshold Routing (Apply ONLY when system size is calculated or requested):
  * Calculated size < 5 kW: Politely mention our minimum installation capacity starts at 5 kW.
  * Calculated size 5 kW to 49 kW: Suggest the optimal kW size range and direct them to call 03138666256 to book a site survey and get an exact quotation.
  * Calculated size >= 50 kW: Identify as a commercial project and instruct them to call senior engineers at 03138666255 (Voice Call Only).
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
Ensure the message ends with ' Sleek Bot'."""

        response = client.chat.completions.create(
            model="openrouter/free",
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
- Do NOT repeat unnecessary policies if not asked.
- Ensure the message strictly ends with ' Sleek Bot'.""

        response = client.chat.completions.create(
            model="openrouter/free",
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
                send_whatsapp_message(sender_phone, "📄 Apka bill analyze ho raha hai... Baraye meherbani intizar karein. Sleek Bot")
                reply_text = analyze_bill_image(media_id)
                send_whatsapp_message(sender_phone, reply_text)
                
            elif msg_type == 'text':
                msg_text = message['text']['body']
                reply_text = get_text_response(msg_text)
                send_whatsapp_message(sender_phone, reply_text)
    except Exception as e:
        print(f"Webhook Execution Error: {e}")
    return {"status": "ok"}
