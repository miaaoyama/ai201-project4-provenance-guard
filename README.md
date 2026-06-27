# Provenance Guard

**AI201 – Project 4**

## Overview

Provenance Guard is a backend attribution system designed for creative platforms that host original writing. Rather than making absolute claims about authorship, the system combines multiple detection signals to estimate whether submitted text appears more likely to be human-written or AI-generated. The goal is to increase transparency while acknowledging uncertainty and providing creators with a fair appeals process.

The system exposes a REST API built with Flask that accepts text submissions, evaluates them using two independent detection signals, produces a confidence score, generates a transparency label, records the decision in a structured audit log, and allows creators to submit appeals if they believe their work was misclassified.

---

# Features

* Multi-signal AI detection
* Confidence scoring
* Three transparency label variants
* Appeals workflow
* Structured audit log
* Rate limiting using Flask-Limiter
* REST API endpoints

---

# System Architecture

Submission flow:

```
POST /submit
        │
        ▼
Input Validation
        │
        ▼
Groq LLM Signal
        │
        ▼
Stylometric Signal
        │
        ▼
Confidence Scoring
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

Appeal flow:

```
POST /appeal
        │
        ▼
Locate Submission
        │
        ▼
Update Status
        │
        ▼
Log Appeal
        │
        ▼
Return Confirmation
```

---

# Detection Signals

## Signal 1 – Groq LLM Classification

The first signal uses a Groq-hosted language model to evaluate whether submitted text appears AI-generated or human-written.

The model evaluates:

* overall writing style
* coherence
* repetition
* generic wording
* consistency
* semantic patterns

The model returns:

* AI likelihood score (0–1)
* attribution prediction
* explanation

This signal captures writing quality and meaning rather than measurable statistics.

---

## Signal 2 – Stylometric Heuristics

The second signal is implemented entirely in Python.

It measures:

* sentence length variance
* vocabulary diversity (type-token ratio)
* punctuation density
* average sentence length

Unlike the LLM, this signal only evaluates structural characteristics.

---

# Confidence Scoring

The two signals are combined using a weighted average.

```
Combined Score =
(Groq Score × 0.60)
+
(Stylometric Score × 0.40)
```

Groq receives slightly more weight because it evaluates semantic information, while stylometric heuristics provide an independent structural perspective.

The final confidence score determines the attribution category.

| Score     | Classification |
| --------- | -------------- |
| 0.00–0.24 | Likely Human   |
| 0.25–0.79 | Uncertain      |
| 0.80–1.00 | Likely AI      |

These thresholds intentionally reduce false positives. On a creative platform, incorrectly labeling a human creator as AI-generated is considered more harmful than failing to detect some AI-generated content.

---

# Example Confidence Scores

## Example 1

Input:

Artificial intelligence represents a transformative paradigm shift...

Result:

```
Groq Score: 0.60
Stylometric Score: 0.364
Combined Confidence: 0.506
Classification:
Uncertain
```

---

## Example 2

Input:

The relationship between monetary policy and asset price inflation...

Result:

```
Groq Score: 0.20
Stylometric Score: 0.345
Combined Confidence: 0.258
Classification:
Uncertain
```

These examples demonstrate that different writing styles produce different signal values and confidence scores, even when both ultimately fall into the uncertain range.

---

# Transparency Labels

## High-confidence AI

> This work shows strong signs of AI generation. This label is provided for transparency and does not make a final judgment about the creator's intent.

---

## High-confidence Human

> This work shows strong signs of human authorship. No AI-generation concerns were detected at a high confidence level.

---

## Uncertain

> The system could not confidently determine whether this work was human-written or AI-generated. This content remains visible with no final attribution judgment.

---

# Appeals Workflow

Creators may submit an appeal if they believe their work has been misclassified.

The appeal includes:

* content ID
* creator reasoning

When an appeal is received the system:

* updates the submission status to `under_review`
* stores the creator's reasoning
* creates a new audit log entry
* preserves the original classification

Automatic reclassification is intentionally not performed.

---

# Rate Limiting

The submission endpoint is protected using Flask-Limiter.

Limit:

```
10 requests per minute
100 requests per day
```

These limits reflect realistic usage by individual creators while preventing automated abuse.

During testing, the rate limiter behaved as expected.

```
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

Every submission records:

* timestamp
* content ID
* creator ID
* attribution result
* confidence score
* Groq score
* stylometric score
* transparency label
* submission status

Appeals additionally record:

* appeal reasoning
* updated status
* appeal timestamp

---

# API Endpoints

## POST /submit

Accepts:

* creator_id
* text

Returns:

* content ID
* attribution
* confidence
* transparency label
* signal scores

---

## POST /appeal

Accepts:

* content ID
* creator reasoning

Returns:

* updated status
* confirmation message

---

## GET /log

Returns structured audit log entries in JSON format.

---

# Known Limitations

This project is intended as a transparency tool rather than a definitive authorship detector.

Several situations remain challenging:

* Poetry with intentional repetition may appear AI-generated because stylometric heuristics interpret repeated structures as unusually uniform.
* Very short submissions often do not provide enough data for reliable stylometric analysis.
* Highly edited human writing can resemble AI-generated prose.
* AI systems can intentionally imitate human imperfections, reducing detection accuracy.

Because of these limitations, the system includes an "Uncertain" classification and an appeals process instead of forcing binary decisions.

---

# Spec Reflection

Writing the specification before implementation helped clarify how confidence scoring, transparency labels, and appeals should interact before any code was written. Having the architecture planned first also made it much easier to implement each milestone incrementally.

One area where the implementation diverged from the original specification was the confidence calibration. During testing, the Groq model tended to assign more conservative scores than expected, resulting in many submissions falling into the "Uncertain" category. Rather than forcing stronger classifications, I kept the conservative thresholds because they better reflected the project's goal of avoiding false positives.

---

# AI Usage

AI was used as an implementation assistant throughout the project.

### Example 1

I used AI to generate the initial Flask application structure, including the `/submit` endpoint and Groq integration.

After generation, I revised the endpoint to match my planned API structure, renamed several fields, and modified the returned JSON to match my specification.

### Example 2

I used AI to help implement the stylometric heuristics and confidence scoring.

The generated implementation was adjusted to match the weighting and thresholds defined in my planning document. I also modified the scoring logic after testing to better reflect the conservative design philosophy of the project.

---

# Future Improvements

If this project were deployed in production, future improvements would include:

* additional detection signals
* machine learning calibration using labeled datasets
* authenticated appeals
* reviewer dashboard
* persistent SQL database
* provenance certificates
* analytics dashboard
* multimodal content support

---

# Technologies Used

* Python
* Flask
* Flask-Limiter
* Groq API
* python-dotenv
* JSON
