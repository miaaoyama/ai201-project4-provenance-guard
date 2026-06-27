import os
import re
import json
import uuid
import string
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from dotenv import load_dotenv
from groq import Groq
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

load_dotenv()

app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

LOG_FILE = "audit_log.jsonl"
CONTENT_FILE = "content_store.json"

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def load_content_store():
    if not os.path.exists(CONTENT_FILE):
        return {}

    with open(CONTENT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_content_store(store):
    with open(CONTENT_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)


def write_log(entry):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def get_log(limit=20):
    if not os.path.exists(LOG_FILE):
        return []

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    entries = [json.loads(line) for line in lines if line.strip()]
    return entries[-limit:]


def generate_transparency_label(attribution):
    labels = {
        "likely_ai": "This work shows strong signs of AI generation. This label is provided for transparency and does not make a final judgment about the creator’s intent.",
        "likely_human": "This work shows strong signs of human authorship. No AI-generation concerns were detected at a high confidence level.",
        "uncertain": "The system could not confidently determine whether this work was human-written or AI-generated. This content remains visible with no final attribution judgment."
    }

    return labels.get(attribution, labels["uncertain"])


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

Scoring guidance:
- Assign 0.10–0.30 when the text has clear personal experience, slang, humor, emotional reactions, unusual details, or uneven human rhythm.
- Assign 0.40–0.60 when the evidence is mixed, such as polished but specific writing or formal human writing.
- Assign 0.70–0.95 when the text is generic, formulaic, overly balanced, repetitive, vague, or sounds like common AI-generated prose.
- Do not mark writing as AI only because it is grammatical or organized.
- Do not mark writing as human only because it uses the word "I"; look for concrete personal details.

Text:
{text}
"""
def calculate_analytics():
    entries = get_log(limit=1000)

    classification_entries = [
        entry for entry in entries
        if entry.get("event_type") == "classification"
    ]

    appeal_entries = [
        entry for entry in entries
        if entry.get("event_type") == "appeal"
    ]

    total_submissions = len(classification_entries)
    likely_ai = sum(1 for e in classification_entries if e.get("attribution") == "likely_ai")
    likely_human = sum(1 for e in classification_entries if e.get("attribution") == "likely_human")
    uncertain = sum(1 for e in classification_entries if e.get("attribution") == "uncertain")
    total_appeals = len(appeal_entries)

    appeal_rate = 0
    if total_submissions > 0:
        appeal_rate = round((total_appeals / total_submissions) * 100, 2)

    return {
        "total_submissions": total_submissions,
        "detection_pattern": {
            "likely_ai": likely_ai,
            "likely_human": likely_human,
            "uncertain": uncertain
        },
        "total_appeals": total_appeals,
        "appeal_rate_percent": appeal_rate,
        "additional_metric": {
            "most_recent_event_count": len(entries)
        }
    }

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
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

    result["llm_score"] = clamp(float(result.get("llm_score", 0.5)))
    return result


def split_sentences(text):
    sentences = re.split(r"[.!?]+", text)
    return [s.strip() for s in sentences if s.strip()]


def tokenize_words(text):
    return re.findall(r"\b\w+\b", text.lower())


def stylometric_signal(text):
    sentences = split_sentences(text)
    words = tokenize_words(text)

    word_count = len(words)
    sentence_count = len(sentences)

    if word_count == 0 or sentence_count == 0:
        return {
            "stylometric_score": 0.5,
            "features": {
                "word_count": word_count,
                "sentence_count": sentence_count,
                "average_words_per_sentence": 0,
                "sentence_length_variance": 0,
                "type_token_ratio": 0,
                "punctuation_density": 0
            }
        }

    sentence_lengths = [len(tokenize_words(sentence)) for sentence in sentences]
    average_words_per_sentence = sum(sentence_lengths) / len(sentence_lengths)

    variance = sum(
        (length - average_words_per_sentence) ** 2
        for length in sentence_lengths
    ) / len(sentence_lengths)

    unique_words = set(words)
    type_token_ratio = len(unique_words) / word_count

    punctuation_count = sum(1 for char in text if char in string.punctuation)
    punctuation_density = punctuation_count / max(len(text), 1)

    variance_score = 1 - clamp(variance / 80)
    diversity_score = 1 - clamp(type_token_ratio)
    punctuation_score = clamp(punctuation_density / 0.08)

    raw_score = (
        variance_score * 0.45
        + diversity_score * 0.35
        + punctuation_score * 0.20
    )

    if word_count < 40:
        stylometric_score = (raw_score + 0.5) / 2
    else:
        stylometric_score = raw_score

    return {
        "stylometric_score": round(clamp(stylometric_score), 3),
        "features": {
            "word_count": word_count,
            "sentence_count": sentence_count,
            "average_words_per_sentence": round(average_words_per_sentence, 2),
            "sentence_length_variance": round(variance, 2),
            "type_token_ratio": round(type_token_ratio, 3),
            "punctuation_density": round(punctuation_density, 3)
        }
    }


def combine_scores(llm_score, stylometric_score):
    combined_score = (llm_score * 0.60) + (stylometric_score * 0.40)
    return round(clamp(combined_score), 3)


def classify_score(score):
    if score >= 0.60:
        return "likely_ai"
    elif score <= 0.24:
        return "likely_human"
    else:
        return "uncertain"


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "Provenance Guard API is running"
    })


@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def submit():
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body must be JSON."}), 400

    text = data.get("text")
    creator_id = data.get("creator_id")
    title = data.get("title", "Untitled")

    if not text or not creator_id:
        return jsonify({
            "error": "Missing required fields: text and creator_id."
        }), 400

    content_id = str(uuid.uuid4())

    llm_result = groq_detection_signal(text)
    stylometric_result = stylometric_signal(text)

    llm_score = float(llm_result.get("llm_score", 0.5))
    stylometric_score = float(stylometric_result.get("stylometric_score", 0.5))

    confidence = combine_scores(llm_score, stylometric_score)
    attribution = classify_score(confidence)
    label = generate_transparency_label(attribution)

    content_record = {
        "content_id": content_id,
        "creator_id": creator_id,
        "title": title,
        "text": text,
        "attribution": attribution,
        "confidence": confidence,
        "llm_score": llm_score,
        "stylometric_score": stylometric_score,
        "stylometric_features": stylometric_result.get("features", {}),
        "label": label,
        "status": "classified",
        "appeal_filed": False,
        "appeal_reasoning": None,
        "created_at": now_utc()
    }

    store = load_content_store()
    store[content_id] = content_record
    save_content_store(store)

    log_entry = {
        "event_type": "classification",
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": now_utc(),
        "attribution": attribution,
        "confidence": confidence,
        "llm_score": llm_score,
        "llm_reason": llm_result.get("reason", ""),
        "stylometric_score": stylometric_score,
        "stylometric_features": stylometric_result.get("features", {}),
        "label": label,
        "status": "classified",
        "appeal_filed": False
    }

    write_log(log_entry)

    response_body = {
        "content_id": content_id,
        "creator_id": creator_id,
        "attribution": attribution,
        "confidence": confidence,
        "label": label,
        "signals": {
            "llm_score": llm_score,
            "llm_reason": llm_result.get("reason", ""),
            "stylometric_score": stylometric_score,
            "stylometric_features": stylometric_result.get("features", {})
        },
        "status": "classified"
    }

    return jsonify(response_body), 200


@app.route("/appeal", methods=["POST"])
def appeal():
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body must be JSON."}), 400

    content_id = data.get("content_id")
    creator_reasoning = data.get("creator_reasoning")

    if not content_id or not creator_reasoning:
        return jsonify({
            "error": "Missing required fields: content_id and creator_reasoning."
        }), 400

    store = load_content_store()

    if content_id not in store:
        return jsonify({
            "error": "Content ID not found."
        }), 404

    original_record = store[content_id]
    previous_status = original_record.get("status", "classified")

    original_record["status"] = "under_review"
    original_record["appeal_filed"] = True
    original_record["appeal_reasoning"] = creator_reasoning
    original_record["appealed_at"] = now_utc()

    store[content_id] = original_record
    save_content_store(store)

    appeal_log_entry = {
        "event_type": "appeal",
        "content_id": content_id,
        "creator_id": original_record.get("creator_id"),
        "timestamp": now_utc(),
        "original_attribution": original_record.get("attribution"),
        "original_confidence": original_record.get("confidence"),
        "llm_score": original_record.get("llm_score"),
        "stylometric_score": original_record.get("stylometric_score"),
        "previous_status": previous_status,
        "status": "under_review",
        "appeal_filed": True,
        "appeal_reasoning": creator_reasoning
    }

    write_log(appeal_log_entry)

    return jsonify({
        "content_id": content_id,
        "status": "under_review",
        "appeal_filed": True,
        "message": "Appeal received and logged for review."
    }), 200


@app.route("/log", methods=["GET"])
def log():
    return jsonify({
        "entries": get_log()
    })

@app.route("/verify", methods=["POST"])
def verify_creator():
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body must be JSON."}), 400

    creator_id = data.get("creator_id")
    verification_statement = data.get("verification_statement")

    if not creator_id or not verification_statement:
        return jsonify({
            "error": "Missing required fields: creator_id and verification_statement."
        }), 400

    certificate = {
        "creator_id": creator_id,
        "verified_creator": True,
        "certificate": "Verified Human Creator ✓",
        "verification_method": "Creator submitted a verification statement describing their authorship process.",
        "display_label": "Verified Human Creator ✓ — this creator completed an additional authorship verification step.",
        "verified_at": now_utc()
    }

    write_log({
        "event_type": "provenance_certificate",
        "creator_id": creator_id,
        "timestamp": now_utc(),
        "verified_creator": True,
        "certificate": certificate["certificate"],
        "verification_statement": verification_statement
    })

    return jsonify(certificate), 200


@app.route("/analytics", methods=["GET"])
def analytics():
    return jsonify(calculate_analytics()), 200

if __name__ == "__main__":
    app.run(debug=True, port=5001)