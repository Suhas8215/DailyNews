"""Flask web app: one-button news briefing."""
import os
from flask import Flask, render_template, jsonify, request

from dotenv import load_dotenv
load_dotenv()

# Import after dotenv so env is loaded
from news import run_briefing

app = Flask(__name__)
TRIGGER_TOKEN = os.environ.get("TRIGGER_TOKEN", "")


@app.route("/")
def index():
    return render_template("index.html", needs_token=bool(TRIGGER_TOKEN))


@app.route("/send", methods=["POST", "GET"])
def send():
    token = request.headers.get("X-Token") or request.args.get("token") or request.form.get("token")
    if TRIGGER_TOKEN and token != TRIGGER_TOKEN:
        return jsonify({"ok": False, "error": "Invalid or missing token"}), 401

    try:
        ok, msg = run_briefing()
        return jsonify({"ok": ok, "message": msg})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
