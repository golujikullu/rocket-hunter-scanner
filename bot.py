from flask import Flask
import requests
import threading

BOT_TOKEN = "8913220765:AAHjkhBDmUylbcsfnGZhZFmtt_4rVKKt5mQ"
CHAT_ID = "6112546554"

app = Flask(__name__)

def send_message():
    message = "🚀 Rocket Hunter Scanner LIVE TEST"

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    response = requests.post(url, data=payload)
    print(response.text)

@app.route('/')
def home():
    return "Bot is running!"

threading.Thread(target=send_message).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
