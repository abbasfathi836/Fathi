from flask import Flask
import threading

app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 ربات تلگرام فعال است"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.start()