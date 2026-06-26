import os
import json
import uuid
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

app = Flask(__name__)

LOG_FILE = "audit_log.jsonl"
client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def write_log(entry):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def get_log(limit=10):
    if not os.path.exists(LOG_FILE):
        return []

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    entries = [json.loads(line) for line in lines if line.strip()]
    return entries[-limit:]


def groq_detection_signal(text):
    prompt = f"""
You are part of an authorship transparency system.

Analyze this text and estimate how likely it is to be AI-generated.

Return ONLY valid JSON in this format:
{{
  "llm_score": 0.0,
  "attribution": "likely_human",
  "reason": "short reason"
}}

Rules:
- llm_score must be between 0 and 1
- 0 means very likely human-written
- 1 means very likely AI-generated
- attribution must be one of: likely_human, uncertain, likely_ai

Text:
{text}
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
    )

    content = response.choices[0].message.content.strip()

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        result = {
            "llm_score": 0.5,
            "attribution": "uncertain",
            "reason": "Groq response could not be parsed, so the system returned uncertain."
        }

    return result


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "Provenance Guard API is running"
    })


@app.route("/submit", methods=["POST"])
def submit():
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body must be JSON."}), 400

    text = data.get("text")
    creator_id = data.get("creator_id")

    if not text or not creator_id:
        return jsonify({
            "error": "Missing required fields: text and creator_id."
        }), 400

    content_id = str(uuid.uuid4())

    signal_result = groq_detection_signal(text)

    llm_score = float(signal_result.get("llm_score", 0.5))
    attribution = signal_result.get("attribution", "uncertain")

    response_body = {
        "content_id": content_id,
        "creator_id": creator_id,
        "attribution": attribution,
        "confidence": llm_score,
        "label": "Placeholder label. Full transparency labels will be added in a later milestone.",
        "signals": {
            "llm_score": llm_score,
            "llm_reason": signal_result.get("reason", "")
        },
        "status": "classified"
    }

    log_entry = {
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": now_utc(),
        "attribution": attribution,
        "confidence": llm_score,
        "llm_score": llm_score,
        "status": "classified"
    }

    write_log(log_entry)

    return jsonify(response_body), 200


@app.route("/log", methods=["GET"])
def log():
    return jsonify({
        "entries": get_log()
    })


if __name__ == "__main__":
    app.run(debug=True, port=5001)