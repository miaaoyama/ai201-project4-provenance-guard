from app import (
    app,
    classify_score,
    combine_scores,
    generate_transparency_label,
    stylometric_signal,
)


def test_classify_score_thresholds():
    assert classify_score(0.20) == "likely_human"
    assert classify_score(0.40) == "uncertain"
    assert classify_score(0.65) == "likely_ai"


def test_combine_scores():
    result = combine_scores(0.8, 0.4)
    assert result == 0.64


def test_transparency_labels_are_different():
    ai_label = generate_transparency_label("likely_ai")
    human_label = generate_transparency_label("likely_human")
    uncertain_label = generate_transparency_label("uncertain")

    assert ai_label != human_label
    assert human_label != uncertain_label
    assert "AI generation" in ai_label
    assert "human authorship" in human_label
    assert "could not confidently determine" in uncertain_label


def test_stylometric_signal_returns_expected_fields():
    text = "I tried the ramen place yesterday. Honestly, it was fine but too salty."
    result = stylometric_signal(text)

    assert "stylometric_score" in result
    assert "features" in result
    assert "word_count" in result["features"]
    assert "type_token_ratio" in result["features"]
    assert "sentence_length_variance" in result["features"]


def test_submit_missing_fields_returns_error():
    client = app.test_client()

    response = client.post("/submit", json={
        "text": "This has text but no creator id."
    })

    assert response.status_code == 400
    assert "error" in response.get_json()


def test_appeal_unknown_content_returns_404():
    client = app.test_client()

    response = client.post("/appeal", json={
        "content_id": "not-a-real-id",
        "creator_reasoning": "I wrote this myself."
    })

    assert response.status_code == 404
    assert "error" in response.get_json()