from flask import Flask, request
import requests
import os

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")


@app.route("/")
def home():
    return "Rocket Hunter Running 🚀"


@app.route("/webhook", methods=["POST"])
def webhook():

    data = request.get_json(force=True)

    print(data)

    try:
        chat_id = data["message"]["chat"]["id"]

        text = data["message"].get("text", "")

        if text == "/start":

            send_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

            payload = {
                "chat_id": chat_id,
                "text": "🚀 Rocket Hunter Activated"
            }

            r = requests.post(send_url, json=payload)

            print(r.text)

    except Exception as e:
        print("ERROR:", e)

    return "ok", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
