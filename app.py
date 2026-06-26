import os
import re
import json
import uuid
import string
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


def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


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
- polished but personal writing should not automatically be treated as AI
- generic, vague, overly balanced writing should score higher

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

    # Convert features into AI-likelihood sub-scores.
    # Lower variance = more uniform = more AI-like.
    variance_score = 1 - clamp(variance / 80)

    # Lower vocabulary diversity = more AI-like.
    diversity_score = 1 - clamp(type_token_ratio)

    # Very consistent polished prose often has moderate punctuation density.
    punctuation_score = clamp(punctuation_density / 0.08)

    # Very short texts are harder to judge, so pull score toward uncertainty.
    short_text_uncertainty = 0.5 if word_count < 40 else None

    raw_score = (
        variance_score * 0.45
        + diversity_score * 0.35
        + punctuation_score * 0.20
    )

    if short_text_uncertainty is not None:
        stylometric_score = (raw_score + short_text_uncertainty) / 2
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
    if score >= 0.80:
        return "likely_ai"
    elif score <= 0.24:
        return "likely_human"
    else:
        return "uncertain"


def placeholder_label(attribution):
    if attribution == "likely_ai":
        return "Placeholder label: high-confidence AI label will be finalized in Milestone 5."
    elif attribution == "likely_human":
        return "Placeholder label: high-confidence human label will be finalized in Milestone 5."
    return "Placeholder label: uncertain label will be finalized in Milestone 5."


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

    llm_result = groq_detection_signal(text)
    stylometric_result = stylometric_signal(text)

    llm_score = float(llm_result.get("llm_score", 0.5))
    stylometric_score = float(stylometric_result.get("stylometric_score", 0.5))

    confidence = combine_scores(llm_score, stylometric_score)
    attribution = classify_score(confidence)

    response_body = {
        "content_id": content_id,
        "creator_id": creator_id,
        "attribution": attribution,
        "confidence": confidence,
        "label": placeholder_label(attribution),
        "signals": {
            "llm_score": llm_score,
            "llm_reason": llm_result.get("reason", ""),
            "stylometric_score": stylometric_score,
            "stylometric_features": stylometric_result.get("features", {})
        },
        "status": "classified"
    }

    log_entry = {
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": now_utc(),
        "attribution": attribution,
        "confidence": confidence,
        "llm_score": llm_score,
        "stylometric_score": stylometric_score,
        "stylometric_features": stylometric_result.get("features", {}),
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