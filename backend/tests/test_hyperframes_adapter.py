"""HyperFrames polish — events from AI overlay / visual entities."""
from __future__ import annotations


def test_events_from_object_overlay_cards():
    from src.infrastructure.hyperframes_adapter import events_from_clip_ai

    events = events_from_clip_ai(
        object_overlay_events=[
            {
                "word": "Shisha",
                "label": "Shisha",
                "at_time": 76.0,
                "duration": 2.4,
                "query_en": "hookah shisha close up",
                "image_path": "/tmp/does-not-need-exist.jpg",
            },
            {
                "word": "Rokok",
                "label": "Rokok",
                "at_time": 53.4,
                "duration": 2.4,
                "query_en": "cigarette pack",
            },
            {
                "word": "Itu",
                "label": "Itu",
                "at_time": 3.0,
                "duration": 2.4,
                "query_en": "Itu product",
            },
        ],
        clip_hook="Berhenti rokok, hidup baru",
        clip_duration=127.0,
        max_events=3,
    )
    labels = [e["label"] for e in events]
    assert "Shisha" in labels
    assert "Rokok" in labels
    assert len(events) <= 3
    assert all(e["end"] > e["start"] for e in events)


def test_events_from_visual_entities_fallback():
    from src.infrastructure.hyperframes_adapter import events_from_clip_ai

    events = events_from_clip_ai(
        visual_entities=[
            {
                "word": "1 Januari",
                "label": "Kalender 1 Januari",
                "start": 14.9,
                "end": 17.0,
                "query_en": "desk calendar january first",
            },
            {
                "word": "Aikos",
                "label": "Aikos",
                "start": 69.4,
                "end": 71.0,
                "query_en": "iqos heated tobacco",
            },
        ],
        clip_hook="Berhenti rokok",
        clip_duration=127.0,
    )
    assert len(events) == 2
    assert events[0]["label"] == "Kalender 1 Januari"
    assert "iqos" in events[1]["sub"].lower() or "aikos" in events[1]["label"].lower()


def test_adapter_enabled_default_true():
    from src.config import settings
    from src.infrastructure.hyperframes_adapter import HyperFramesAdapter

    assert bool(settings.HYPERFRAMES_ENABLED) is True
    ad = HyperFramesAdapter()
    # property may also OR DB; at least env true
    assert ad.enabled is True
