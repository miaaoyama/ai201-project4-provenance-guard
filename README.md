# Provenance Guard

**AI201 – Project 4**

## Overview

Provenance Guard is a backend attribution system designed for creative writing platforms where users publish poems, stories, essays, blog posts, and other original work. Rather than attempting to make a definitive judgment about authorship, the system estimates whether submitted content appears more likely to be human-written or AI-generated while communicating its level of confidence.

The primary goal of the project is transparency, not enforcement. AI-generated content is becoming increasingly difficult to distinguish from human writing, and even state-of-the-art detectors are imperfect. Because of this uncertainty, Provenance Guard combines multiple independent detection signals instead of relying on a single classifier. It also provides creators with an appeals process whenever they believe their work has been misclassified.

The application is implemented as a Flask REST API that accepts text submissions, evaluates them using two independent detection signals, combines those signals into a confidence score, generates a reader-friendly transparency label, stores every decision in a structured audit log, and supports creator appeals.

---

# Features

* REST API built with Flask
* Multi-signal attribution pipeline
* Confidence scoring with uncertainty
* Three transparency label variants
* Appeals workflow
* Structured JSON audit log
* Rate limiting with Flask-Limiter
* Persistent content tracking for appeals

---

# System Architecture

## Submission Flow

```text
POST /submit
        │
        ▼
Validate Request
        │
        ▼
Groq LLM Detection
        │
        ▼
Stylometric Analysis
        │
        ▼
Confidence Scoring
        │
        ▼
Classification
        │
        ▼
Transparency Label
        │
        ▼
Audit Log
        │
        ▼
JSON Response
```

## Appeal Flow

```text
POST /appeal
        │
        ▼
Locate Submission
        │
        ▼
Update Status
        │
        ▼
Store Creator Reasoning
        │
        ▼
Audit Log
        │
        ▼
Confirmation Response
```

---

# Detection Pipeline

The attribution pipeline combines two independent detection signals.

Using two different approaches makes the system more reliable than relying on a single signal because each captures different characteristics of the writing.

---

## Signal 1 — Groq LLM Classification

The first signal uses a Groq-hosted large language model to evaluate the overall writing style.

Rather than measuring statistics, the model looks for semantic characteristics such as:

* overall coherence
* repetitive phrasing
* generic language
* formulaic structure
* specificity
* personal experience
* emotional tone
* contextual nuance

The model returns:

* AI likelihood score (0–1)
* attribution assessment
* explanation describing why it reached that conclusion

### What this signal captures

The LLM captures higher-level characteristics that are difficult to measure numerically, such as whether the writing feels generic or contains concrete lived experience.

### Blind spots

Because it reasons holistically, the model may occasionally mistake highly polished human writing for AI-generated text or underestimate AI-generated writing that intentionally imitates human imperfections.

---

## Signal 2 — Stylometric Heuristics

The second signal is implemented entirely in Python without using another AI model.

Instead of evaluating meaning, it analyzes measurable structural characteristics including:

* sentence length variance
* average sentence length
* vocabulary diversity (type-token ratio)
* punctuation density

These characteristics are combined into a stylometric AI-likelihood score.

### What this signal captures

Stylometric analysis measures structural consistency. AI-generated writing often produces more uniform sentence patterns and vocabulary usage than naturally occurring human writing.

### Blind spots

Stylometric analysis cannot understand meaning or intent.

Formal academic writing, technical reports, or intentionally repetitive creative writing may resemble AI-generated text even when written entirely by a person.

---

# Confidence Scoring

Both signals produce independent scores between **0** and **1**.

The final confidence score is calculated using a weighted average:

```text
Combined Confidence =
(Groq Score × 0.60)
+
(Stylometric Score × 0.40)
```

The Groq signal receives a slightly higher weight because it evaluates semantic characteristics while the stylometric signal provides an independent structural perspective.

The final confidence determines the attribution category.

| Confidence Score | Classification |
| ---------------- | -------------- |
| 0.00 – 0.24      | Likely Human   |
| 0.25 – 0.59      | Uncertain      |
| 0.60 – 1.00      | Likely AI      |

These thresholds intentionally prioritize reducing false positives.

Incorrectly labeling a human creator as AI-generated can damage trust and attribution. Because of this, the system favors uncertainty whenever the two signals disagree rather than making an overly confident decision.

---

# Confidence Score Validation

To evaluate whether the confidence scores behaved reasonably, several different writing styles were submitted to the system.

## Example 1 — Generic AI-style Writing

Input:

> Artificial intelligence represents a transformative paradigm shift in modern society...

Result

```text
Groq Score: 0.80
Stylometric Score: 0.386
Combined Confidence: 0.634

Classification:
Likely AI
```

---

## Example 2 — Casual Personal Writing

Input:

> ok so i finally tried that new ramen place downtown...

Result

```text
Groq Score: 0.20
Stylometric Score: 0.283
Combined Confidence: 0.233

Classification:
Likely Human
```

---

## Example 3 — Borderline Example

Input:

> I have been thinking a lot about remote work lately...

Result

```text
Groq Score: 0.40
Stylometric Score: 0.415
Combined Confidence: 0.406

Classification:
Uncertain
```

These examples demonstrate that different writing styles produce meaningfully different confidence scores instead of every submission receiving the same classification.

---

# Transparency Labels

The transparency label is intended for non-technical readers. Instead of exposing raw confidence scores, it communicates the system's assessment in plain language.

## High-Confidence AI

> "This work shows strong signs of AI generation. This label is provided for transparency and does not make a final judgment about the creator's intent."

---

## High-Confidence Human

> "This work shows strong signs of human authorship. No AI-generation concerns were detected at a high confidence level."

---

## Uncertain

> "The system could not confidently determine whether this work was human-written or AI-generated. This content remains visible with no final attribution judgment."

These labels intentionally avoid technical language such as "classifier output" or "model probability" so that readers can easily understand the result.

---

# Appeals Workflow

Creators who believe their work has been misclassified may submit an appeal.

The appeal requires:

* `content_id`
* `creator_reasoning`

When an appeal is received, the system:

1. Locates the original submission.
2. Updates its status to `under_review`.
3. Stores the creator's explanation.
4. Records a new audit log entry linked to the original submission.
5. Returns a confirmation message.

The system does **not** automatically reclassify content. Instead, it preserves the original decision while recording that the creator has requested a manual review.

---

# Rate Limiting

To reduce abuse, the submission endpoint is protected using **Flask-Limiter**.

Configured limits:

```text
10 requests per minute
100 requests per day
```

These limits were chosen because they reflect realistic usage on a creative writing platform.

A typical creator is unlikely to submit more than a few pieces of writing in a short period of time, while an automated script attempting to probe or overwhelm the detector would quickly exceed these limits.

Testing confirmed the limiter behaved as expected.

```text
200
200
200
200
200
200
200
200
200
429
429
429
```

---

# Audit Log

Every classification decision is written to a structured JSON audit log.

Each entry records:

* timestamp
* content ID
* creator ID
* attribution result
* confidence score
* Groq score
* stylometric score
* transparency label
* submission status

When an appeal is submitted, the log additionally records:

* appeal event
* creator reasoning
* updated status (`under_review`)
* appeal timestamp

Maintaining a structured audit log makes every attribution decision traceable while preserving the history of appeals.

---

# API Endpoints

## POST /submit

Submits writing for attribution analysis.

### Request

```json
{
  "creator_id": "user123",
  "text": "Example submission..."
}
```

### Response

```json
{
  "content_id": "...",
  "attribution": "...",
  "confidence": 0.634,
  "label": "...",
  "signals": {
    "llm_score": 0.80,
    "stylometric_score": 0.386
  },
  "status": "classified"
}
```

---

## POST /appeal

Submits an appeal for an existing classification.

### Request

```json
{
  "content_id": "...",
  "creator_reasoning": "I wrote this myself."
}
```

The response confirms that the submission has been placed **under review**.

---

## GET /log

Returns the structured audit log containing both classification events and appeal events.

---

# Known Limitations

Provenance Guard is designed as a transparency tool rather than a definitive AI detector.

Some content types remain difficult to classify accurately.

Examples include:

* **Poetry**, where repetition and simple vocabulary may resemble AI-generated patterns even when written by a human.
* **Highly technical or academic writing**, which often uses formal language and consistent sentence structure that may resemble AI-generated prose.
* **Very short submissions**, where there is insufficient text for meaningful stylometric analysis.
* **AI-generated writing intentionally edited by humans**, which may contain enough personal detail to reduce the AI likelihood score.

Because these limitations are unavoidable, the system includes an **Uncertain** category and an appeals process instead of forcing every submission into a binary decision.

---

# Spec Reflection

Writing the specification before implementation significantly improved the overall design process.

Planning the system architecture first made it easier to build each milestone incrementally instead of trying to implement every feature simultaneously. Defining the confidence ranges and transparency labels early also ensured that the API, audit log, and appeals workflow all shared the same assumptions.

One place where the implementation diverged from the original plan was confidence calibration. During testing, the Groq model produced more conservative scores than expected, so the confidence thresholds were adjusted after evaluating multiple examples. This resulted in classifications that better matched the project's goal of minimizing false positives while still producing meaningful differences across writing styles.

---

# AI Usage

AI was used as a development assistant throughout the project rather than as an automatic code generator.

## Example 1

AI was used to generate the initial Flask application structure, including the API routes and Groq integration.

After reviewing the generated code, I modified the endpoint structure, updated the returned JSON format, added structured logging, and reorganized the application to match the architecture defined in my planning document.

---

## Example 2

AI assisted with implementing the stylometric heuristics and confidence-scoring logic.

The initial implementation was revised after testing multiple examples. I adjusted the weighting between the Groq signal and the stylometric signal, modified the classification thresholds, improved the Groq prompt, and calibrated the system so that it produced meaningful differences between human, uncertain, and AI classifications.

---

# Future Improvements

If this project were extended further, possible improvements include:

* adding additional detection signals for an ensemble approach
* training a calibrated classifier using labeled evaluation data
* authenticated creator accounts
* reviewer dashboard for appeals
* SQLite or PostgreSQL database instead of JSON storage
* provenance certificates for verified creators
* analytics dashboard showing detection trends and appeal rates
* support for additional content types such as image metadata or multimodal submissions

---

# Technologies Used

* Python
* Flask
* Flask-Limiter
* Groq API
* python-dotenv
* JSON
* REST API design

---

# Conclusion

Provenance Guard demonstrates that AI attribution systems should emphasize transparency rather than certainty. By combining multiple independent signals, communicating confidence clearly, maintaining a complete audit trail, and allowing creators to appeal decisions, the system encourages trust while acknowledging the limitations of current AI detection technology.

# Stretch Features

## Provenance Certificate

I implemented a provenance certificate feature through the `POST /verify` endpoint.

A creator can submit a verification statement explaining their authorship process, such as having drafts, notes, or revision history. If accepted, the system returns a verified creator certificate.

Example output:

```json
{
  "certificate": "Verified Human Creator ✓",
  "creator_id": "test-human",
  "display_label": "Verified Human Creator ✓ — this creator completed an additional authorship verification step.",
  "verification_method": "Creator submitted a verification statement describing their authorship process.",
  "verified_creator": true
}
## Analytics Dashboard (Stretch Feature)

To better understand how the attribution system performs over time, I implemented an analytics endpoint (`GET /analytics`) that summarizes information from the structured audit log.

Rather than requiring someone to manually inspect individual log entries, the endpoint provides an overall view of system activity and classification patterns.

The analytics endpoint currently reports:

* **Detection pattern** – the number of submissions classified as `likely_ai`, `likely_human`, and `uncertain`.
* **Appeal rate** – the percentage of submitted content that has been appealed by creators.
* **Additional metric** – the total number of recorded events (classifications, appeals, and verification events) currently stored in the audit log.

Example output:

```json
{
  "total_submissions": 26,
  "detection_pattern": {
    "likely_ai": 2,
    "likely_human": 7,
    "uncertain": 17
  },
  "total_appeals": 1,
  "appeal_rate_percent": 3.85,
  "additional_metric": {
    "most_recent_event_count": 35
  }
}
```

This endpoint could easily be connected to a future web dashboard displaying charts and trends for moderators, platform administrators, or researchers monitoring attribution decisions over time.
