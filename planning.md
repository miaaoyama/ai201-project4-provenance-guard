# Provenance Guard Planning

## Project Overview

Provenance Guard is a backend attribution system for creative writing platforms. The system accepts submitted text, analyzes it using multiple detection signals, calculates a confidence score, returns a transparency label, records the decision in an audit log, and allows creators to appeal classifications they believe are incorrect.

The purpose of this project is not to perfectly detect AI-generated writing. Perfect AI detection is not realistic. Instead, Provenance Guard is designed to communicate uncertainty honestly, avoid overclaiming authorship decisions, and provide creators with a path to contest results.

---

# Architecture

## Architecture Narrative

When a creator submits text, the request goes to the `POST /submit` endpoint. The endpoint validates that the request includes the required fields, then sends the text through two detection signals: a Groq LLM classification signal and a stylometric heuristic signal.

Each signal returns an AI-likelihood score. The system combines those two scores into a single confidence score using a weighted average. That score is mapped to one of three attribution categories: `likely_human`, `uncertain`, or `likely_ai`. The classification is then converted into a plain-language transparency label. The full decision, including individual signal scores, the combined confidence score, and the label, is saved in the audit log and returned as JSON.

If a creator disagrees with the result, they can submit an appeal through `POST /appeal`. The system looks up the original content record, stores the creator's reasoning, changes the status to `under_review`, and adds an appeal event to the audit log.

## Architecture Diagram

```text
Submission Flow

Creator / Platform
      |
      | raw text + creator_id
      v
POST /submit
      |
      | validated request
      v
Input Validation
      |
      | text
      v
Detection Pipeline
      |
      |------------------------------|
      |                              |
      v                              v
Groq LLM Signal              Stylometric Heuristic Signal
      |                              |
      | llm_score                    | stylometric_score
      |                              |
      |--------------|---------------|
                     v
            Confidence Scoring
                     |
                     | combined confidence score
                     v
              Classification
                     |
                     | likely_human / uncertain / likely_ai
                     v
          Transparency Label Generator
                     |
                     | reader-friendly label text
                     v
              Structured Audit Log
                     |
                     | saved decision record
                     v
              JSON API Response


Appeal Flow

Creator
   |
   | content_id + creator_reasoning
   v
POST /appeal
   |
   | appeal request
   v
Appeal Handler
   |
   | update content status
   v
Content Store
   |
   | status = under_review
   v
Structured Audit Log
   |
   | appeal event linked to original decision
   v
JSON API Response
```

---

# Detection Signals

## Signal 1: Groq LLM Classification

The first detection signal uses a Groq-hosted language model to analyze the submitted text.

### What it measures

This signal evaluates higher-level writing qualities such as:

* whether the text sounds generic
* whether the structure feels formulaic
* whether the writing contains personal detail
* whether the writing includes emotional tone or lived experience
* whether the writing sounds like common AI-generated prose
* whether the writing is overly balanced or vague

### Output

The signal returns a score between `0.0` and `1.0`.

```json
{
  "llm_score": 0.8,
  "attribution": "likely_ai",
  "reason": "The text is generic, formulaic, and lacks personal detail."
}
```

A score closer to `1.0` means the LLM signal thinks the text is more likely AI-generated. A score closer to `0.0` means the LLM signal thinks the text is more likely human-written.

### Why I chose it

This signal can evaluate meaning and tone in a way that simple statistics cannot. It can notice if the text lacks concrete detail or sounds like a broad generated response.

### Blind spot

The LLM can still be wrong. It may assign high AI scores to formal human writing or lower AI scores to AI-generated writing that has been edited to sound personal.

---

## Signal 2: Stylometric Heuristics

The second signal uses pure Python to measure structural patterns in the submitted text.

### What it measures

This signal measures:

* sentence length variance
* average words per sentence
* type-token ratio
* punctuation density

### Output

The signal returns a score between `0.0` and `1.0`, plus the measured features.

```json
{
  "stylometric_score": 0.386,
  "features": {
    "word_count": 48,
    "sentence_count": 3,
    "average_words_per_sentence": 16.0,
    "sentence_length_variance": 24.0,
    "type_token_ratio": 0.896,
    "punctuation_density": 0.014
  }
}
```

A higher score means the structure looks more AI-like. A lower score means the structure looks more human-like.

### Why I chose it

This signal is independent from the LLM signal because it does not interpret meaning. It only measures structure. This makes the overall pipeline stronger because the two signals capture different properties of the text.

### Blind spot

Stylometric heuristics cannot understand content, intention, creativity, or context. Poetry, technical writing, and very short submissions may be difficult for this signal to evaluate accurately.

---

# Combining Signals

The two signal scores are combined using a weighted average.

```text
combined_confidence =
(llm_score * 0.60) + (stylometric_score * 0.40)
```

The LLM signal receives slightly more weight because it can evaluate semantic and stylistic meaning. The stylometric signal still receives significant weight because it gives an independent structural measurement.

---

# Uncertainty Representation

The confidence score represents the system's estimate that a piece of text is AI-generated.

The final implementation uses these thresholds:

```text
0.00 – 0.24 = likely_human
0.25 – 0.59 = uncertain
0.60 – 1.00 = likely_ai
```

A confidence score near the middle does not produce a forced binary answer. It produces the `uncertain` label.

For example:

```text
0.233 = likely_human
0.406 = uncertain
0.634 = likely_ai
```

This approach gives the system room to express uncertainty instead of pretending that every classification is equally reliable.

---

# Transparency Label Design

The transparency label is written for readers, not developers. It avoids technical language and explains the result plainly.

| Result                | Exact Label Text                                                                                                                                                   |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| High-confidence AI    | “This work shows strong signs of AI generation. This label is provided for transparency and does not make a final judgment about the creator’s intent.”            |
| High-confidence Human | “This work shows strong signs of human authorship. No AI-generation concerns were detected at a high confidence level.”                                            |
| Uncertain             | “The system could not confidently determine whether this work was human-written or AI-generated. This content remains visible with no final attribution judgment.” |

---

# Appeals Workflow

A creator can submit an appeal if they believe the system classified their work incorrectly.

## Appeal input

The appeal endpoint accepts:

```json
{
  "content_id": "content-id-here",
  "creator_reasoning": "I wrote this myself from personal experience."
}
```

## What happens when an appeal is received

When an appeal is submitted, the system:

1. Looks up the original content ID.
2. Updates the content status to `under_review`.
3. Stores the creator's reasoning.
4. Writes a new appeal event to the audit log.
5. Returns a confirmation response.

## Appeal output

```json
{
  "content_id": "content-id-here",
  "status": "under_review",
  "appeal_filed": true,
  "message": "Appeal received and logged for review."
}
```

A human reviewer would be able to see:

* original content ID
* creator ID
* original attribution
* original confidence score
* LLM score
* stylometric score
* creator reasoning
* updated review status

Automatic reclassification is not required because the purpose of the appeal is to create a review path.

---

# Audit Log Design

Every submission and appeal is recorded in a structured JSON log.

## Classification log entry

```json
{
  "event_type": "classification",
  "content_id": "5794db48-0bf5-442e-bf74-00e946c544f4",
  "creator_id": "test-ai",
  "timestamp": "2026-06-26T23:00:00Z",
  "attribution": "likely_ai",
  "confidence": 0.634,
  "llm_score": 0.8,
  "stylometric_score": 0.386,
  "label": "This work shows strong signs of AI generation. This label is provided for transparency and does not make a final judgment about the creator’s intent.",
  "status": "classified",
  "appeal_filed": false
}
```

## Appeal log entry

```json
{
  "event_type": "appeal",
  "content_id": "5794db48-0bf5-442e-bf74-00e946c544f4",
  "creator_id": "test-ai",
  "timestamp": "2026-06-26T23:10:00Z",
  "original_attribution": "likely_ai",
  "original_confidence": 0.634,
  "llm_score": 0.8,
  "stylometric_score": 0.386,
  "previous_status": "classified",
  "status": "under_review",
  "appeal_filed": true,
  "appeal_reasoning": "I wrote this myself from personal experience."
}
```

---

# API Surface

## POST /submit

Accepts a text submission for attribution analysis.

### Request

```json
{
  "creator_id": "test-user",
  "text": "Submitted writing goes here."
}
```

### Response

```json
{
  "content_id": "5794db48-0bf5-442e-bf74-00e946c544f4",
  "creator_id": "test-user",
  "attribution": "likely_ai",
  "confidence": 0.634,
  "label": "This work shows strong signs of AI generation. This label is provided for transparency and does not make a final judgment about the creator’s intent.",
  "signals": {
    "llm_score": 0.8,
    "stylometric_score": 0.386
  },
  "status": "classified"
}
```

## POST /appeal

Accepts an appeal for a previous classification.

### Request

```json
{
  "content_id": "5794db48-0bf5-442e-bf74-00e946c544f4",
  "creator_reasoning": "I wrote this myself and can explain my process."
}
```

### Response

```json
{
  "content_id": "5794db48-0bf5-442e-bf74-00e946c544f4",
  "status": "under_review",
  "appeal_filed": true,
  "message": "Appeal received and logged for review."
}
```

## GET /log

Returns recent structured audit log entries.

---

# Anticipated Edge Cases

## Edge Case 1: Poetry with repetition

A poem may intentionally repeat phrases, use simple words, or create rhythm through repeated structure. The stylometric signal may interpret this as AI-like uniformity even if the work is fully human-written.

Expected handling: the system may return `uncertain` or allow an appeal if the creator believes the classification is wrong.

## Edge Case 2: Formal academic writing

Formal writing often avoids emotion and personal detail. It may use polished sentence structure and technical language, which can look AI-like to both signals.

Expected handling: the README notes this as a known limitation, and the appeals workflow gives creators a way to contest the result.

## Edge Case 3: Very short submissions

A short caption, short poem, or single paragraph may not provide enough data for sentence variance or vocabulary diversity to be meaningful.

Expected handling: short text may be harder to classify and should often remain uncertain.

## Edge Case 4: AI-generated writing edited to sound human

A user could prompt an AI system to add slang, emotion, or personal details. This can reduce both signal scores and make AI-generated writing look more human.

Expected handling: the system may miss some AI-generated content. This is acceptable because the project prioritizes transparency over pretending detection is perfect.

---

# AI Tool Plan

## Milestone 3: Submission Endpoint and First Signal

Spec sections to provide to the AI tool:

* Architecture
* Detection Signals
* API Surface

Ask the AI tool to generate:

* Flask app skeleton
* `POST /submit` endpoint
* input validation
* Groq LLM classification function
* starter audit log entry

Verification plan:

* Run Flask locally.
* Submit sample text through `curl`.
* Confirm the API returns `content_id`, `attribution`, `confidence`, `label`, and signal output.
* Confirm the audit log records the classification.

---

## Milestone 4: Second Signal and Confidence Scoring

Spec sections to provide to the AI tool:

* Detection Signals
* Combining Signals
* Uncertainty Representation
* Architecture

Ask the AI tool to generate:

* stylometric heuristic function
* feature calculations
* combined scoring function
* threshold-based classification function

Verification plan:

* Test clearly AI-style writing.
* Test casual personal writing.
* Test borderline formal writing.
* Confirm the confidence scores differ meaningfully.
* Confirm both signal scores appear in the API response and audit log.

---

## Milestone 5: Production Layer

Spec sections to provide to the AI tool:

* Transparency Label Design
* Appeals Workflow
* Audit Log Design
* Architecture

Ask the AI tool to generate:

* transparency label function
* appeal endpoint
* status update logic
* complete audit log entries
* rate limiting setup

Verification plan:

* Confirm all three transparency labels are reachable.
* Submit an appeal and confirm status changes to `under_review`.
* Confirm the appeal appears in the audit log.
* Trigger rate limiting and confirm `429` responses.

---

# Stretch Features

## Stretch Feature 1: Provenance Certificate

### Goal

Allow creators to voluntarily complete an additional verification step that is separate from the AI attribution pipeline.

### Design

A new endpoint (`POST /verify`) accepts:

```json
{
  "creator_id": "test-user",
  "verification_statement": "I can provide drafts, notes, and revision history."
}
```

If verification is successful, the system returns a **Verified Human Creator** certificate.

This certificate is displayed independently from the transparency label because it represents creator verification rather than an AI classification.

---

## Stretch Feature 2: Analytics Dashboard

### Goal

Provide an overview of how the attribution system is performing over time.

### Design

A new endpoint (`GET /analytics`) summarizes information collected from the structured audit log.

The analytics endpoint reports:

- total submissions
- number of likely AI classifications
- number of likely human classifications
- number of uncertain classifications
- total appeals
- appeal rate
- total recorded events

These metrics help moderators understand usage patterns without reading individual audit log entries.

---

## Why These Stretch Features

I selected these stretch features because they extend the usability of the system without changing the core attribution pipeline.

The provenance certificate increases trust by allowing creators to verify their identity, while the analytics endpoint helps moderators monitor how the system is performing over time.