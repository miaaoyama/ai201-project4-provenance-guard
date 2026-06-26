# Provenance Guard Planning

## Milestone 1: System Understanding and Architecture

## Architecture Narrative

When a user submits a piece of text, the request first goes to the `POST /submit` endpoint. This endpoint validates that the submission includes text content and basic creator/content information. After validation, the raw text is sent into the detection pipeline.

The detection pipeline uses two separate signals. The first signal is an LLM-based classification using Groq. This signal looks at the writing holistically and estimates whether the text reads more like human-written or AI-generated content. The second signal is a stylometric heuristic analysis written in Python. This signal measures structural features of the text, such as sentence length variation, vocabulary diversity, punctuation density, and average sentence length.

After both signals return their scores, the confidence scoring component combines them into one final AI-likelihood score. The system does not treat this score as a perfect truth. Instead, it uses thresholds to decide whether the result should be labeled as high-confidence AI, high-confidence human, or uncertain. Because falsely accusing a human creator is more harmful than missing some AI-generated content, the system only uses the high-confidence AI label when the score is strongly above the threshold.

Next, the transparency label component converts the classification into plain language that a reader can understand. The label explains the result without claiming absolute certainty. The classification result, confidence score, signal details, label text, and status are then saved to the structured audit log. Finally, the API returns the result to the platform so it can show the transparency label beside the submitted content.

If a creator believes their work was misclassified, they can submit an appeal through `POST /appeal/<content_id>`. The appeal endpoint captures the creator’s reasoning, updates the content status to `under_review`, and appends the appeal to the audit log alongside the original decision. The system does not automatically re-classify the work during appeal because the goal is to create a fair human review path.

## Detection Signals

### Signal 1: LLM-Based Classification using Groq

This signal asks a Groq-hosted language model to evaluate whether the submitted text appears more likely to be human-written or AI-generated. It captures semantic and stylistic patterns that are hard to measure with simple code, such as generic tone, overly smooth structure, repetition, vague details, and unnatural coherence.

I chose this signal because AI-generated text often has a polished and balanced style that may be recognizable when reading the text as a whole. The LLM can evaluate the overall impression of the writing rather than only counting surface-level statistics.

Blind spot: this signal is not perfect because an LLM can be biased, inconsistent, or overconfident. Strong human writing can sometimes look polished, while messy AI writing can look human. This is why the system does not rely on the LLM signal alone.

### Signal 2: Stylometric Heuristics

This signal uses pure Python to calculate measurable writing features such as sentence length variance, type-token ratio, punctuation density, and average sentence length. These features capture the structure of the writing rather than its meaning.

I chose this signal because AI-generated writing often has more uniform sentence structure, smoother pacing, and less natural variation than human writing. Human writing may include more uneven sentence lengths, unusual word choices, and inconsistent rhythm.

Blind spot: stylometric heuristics cannot truly understand meaning, intent, creativity, or lived experience. A short text may not have enough data for accurate measurements. Some human writers also write in a very consistent style, and some AI-generated text can be prompted to include variation.

## False Positive Scenario

A false positive happens when the system labels a human writer’s work as likely AI-generated. This is the most harmful mistake because it can damage trust, discourage creators, and make someone feel accused of dishonesty.

To reduce this risk, the system uses a high threshold before applying the high-confidence AI label. If the signals are mixed or the score is near the middle, the system returns an uncertain label instead of making a strong claim. The uncertain label tells readers that the system could not confidently determine authorship and avoids treating the creator as guilty.

If a creator still believes the result is wrong, they can submit an appeal. The appeal captures their reasoning, changes the content status to `under_review`, and logs the appeal with the original decision. This gives the creator a clear path to contest the result instead of being stuck with the automated classification.

## API Surface

### POST /submit

Accepts a new text submission for attribution analysis.

Request body:

```json
{
  "creator_id": "creator_123",
  "title": "My Poem",
  "content": "Text content goes here..."
}

# Provenance Guard Planning

## Project Overview

Provenance Guard is a backend system for creative platforms that want to provide transparency about whether submitted writing appears human-written, AI-generated, or uncertain. The goal is not to punish creators or make perfect authorship claims. The goal is to combine multiple signals, communicate uncertainty clearly, log decisions, and provide a fair appeal path.

## Detection Signals

### Signal 1: LLM-Based Classification with Groq

This signal uses a Groq-hosted language model to analyze the submitted text and estimate how likely it is to be AI-generated.

It measures holistic writing qualities such as:

- overall coherence
- generic or overly polished tone
- repetition
- vague wording
- unnatural consistency
- whether the text feels like it was generated from a prompt

The output will be a score between `0.0` and `1.0`.

```json
{
  "groq_ai_probability": 0.72,
  "groq_reason": "The writing is polished and generic, with consistent sentence structure."
}