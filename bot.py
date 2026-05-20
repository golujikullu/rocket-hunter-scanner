import requests

BOT_TOKEN = "8913220765:AAHjkhBDmUylbcsfnGZhZFmtt_4rVKKt5mQ"
CHAT_ID = "6112546554"

message = "🚀 Rocket Hunter Scanner LIVE TEST"

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

payload = {
    "chat_id": CHAT_ID,
    "text": message
}

response = requests.post(url, data=payload)

print(response.text)
