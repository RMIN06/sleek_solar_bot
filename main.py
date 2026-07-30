from fastapi import FastAPI, Request, Response
import requests
import base64
import os
from openai import OpenAI

app = FastAPI()

# Retrieve keys securely
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

def analyze_bill_image(media_id):
    """Downloads image and asks OpenRouter to read the electricity bill"""
    # Ask Meta for the image URL
    media_url_req = requests.get(f"https://graph.facebook.com/v18.0/{media_id}", headers=HEADERS)
    media_url = media_url_req.json().get('url')
    
    # Download the image
    image_req = requests.get(media_url, headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"})
    base64_image = base64.b64encode(image_req.content).decode('utf-8')
    
    # Instruct the AI
    prompt = """
    You are an expert solar engineer for Sleek Solar International in Pakistan. 
    Look at this electricity bill.
    1. Extract the 'Consumed Units' for the month.
    2. Calculate required solar system size in kW (Units / 120 = kW).
    3. Rules:
       - If kW < 5, say Sleek Solar's minimum is 5kW.
       - If kW >= 50, say this is commercial, ask them to call 03138666255.
       - If between 5kW and 50kW, suggest the kW size and tell them to call 03138666256 for a quotation.
    
    IMPORTANT: Reply naturally in a mix of professional English and Roman Urdu. Be polite and helpful. Do not output anything other than the exact message you want sent to the customer.
    """
    
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
    return response.choices[0].message.content

def get_text_response(msg_text):
    """Handles text messages and Roman Urdu using AI"""
    prompt = f"""
    You are a WhatsApp assistant for Sleek Solar International.
    User Message: "{msg_text}"
    
    Business Knowledge:
    - Products: Sleek Solar Lithium/Sodium-Ion batteries. Huawei, Maxpower, SAJ, Solis, GoodWe, Inverex inverters (6kW to 110kW). Canadian, Jinko, Longi, Risen panels (710W, 720W, 740W Bifacial).
    - Location: 622-A Peoples Colony No-1, Faisalabad. 9:30 AM - 6:00 PM.
    - Installments: Available via JS Bank. Call 03138666256.
    - Sizing rule: If they give appliances/units, suggest kW (1kW = 120 units). Min install is 5kW. >= 50kW must call 03138666255. Otherwise call 03138666256 for quote.
    
    Task: Answer the user's message accurately using the business knowledge above. Respond in the same language they used (English or Roman Urdu). Be concise.
    """
    
    response = client.chat.completions.create(
      model="openrouter/free",
      messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

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
                send_whatsapp_message(sender_phone, "📄 Apka bill analyze ho raha hai... please wait.")
                reply_text = analyze_bill_image(media_id)
                send_whatsapp_message(sender_phone, reply_text)
                
            elif msg_type == 'text':
                msg_text = message['text']['body']
                reply_text = get_text_response(msg_text)
                send_whatsapp_message(sender_phone, reply_text)
    except Exception as e:
        print(f"Error: {e}")
    return {"status": "ok"}