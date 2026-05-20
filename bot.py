import requests

BOT_TOKEN = "PASTE_BOT_TOKEN_HERE"
CHAT_ID = "PASTE_CHANNEL_ID_HERE"

message = "🚀 Rocket Hunter Scanner LIVE TEST"

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

payload = {
    "chat_id": CHAT_ID,
    "text": message
}

response = requests.post(url, data=payload)

print(response.text)
