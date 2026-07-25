"""Tests for metadata/transcript content profiling."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.content_intelligence import ContentIntelligence


def test_gaming_content_forces_gameplay_facecam_grid_when_enabled():
    profile = ContentIntelligence().detect(
        metadata={"title": "Valorant ranked clutch gameplay with facecam"},
        transcript_text="kita push rank dan lihat clutch terakhir di round ini",
        autogrid_enabled=True,
    )

    assert profile.content_type == "gaming"
    assert profile.grid_strategy == "gaming_gameplay_facecam"
    assert profile.force_grid is True


def test_podcast_content_uses_visual_auto_grid_when_enabled():
    profile = ContentIntelligence().detect(
        metadata={"title": "Podcast ngobrol dengan bintang tamu"},
        transcript_text="host bertanya ke guest tentang cerita mereka di studio",
        autogrid_enabled=True,
    )

    assert profile.content_type == "podcast"
    assert profile.grid_strategy == "speaker_grid_auto"
    assert profile.force_grid is False


def test_autogrid_off_disables_grid_strategy():
    profile = ContentIntelligence().detect(
        metadata={"title": "Mobile Legends gameplay"},
        autogrid_enabled=False,
    )

    assert profile.content_type == "gaming"
    assert profile.grid_strategy == "disabled"
    assert profile.force_grid is False


def test_dialogue_density_soft_classifies_podcast_not_general_zero():
    """Long multi-turn transcript without podcast keywords still soft-classifies."""
    text = " ".join(
        ["iya betul menurut saya kamu benar setuju gue elu bro guys"] * 3
    )
    profile = ContentIntelligence().detect(
        metadata={"title": "clip harian"},
        transcript_text=text,
        autogrid_enabled=True,
    )
    assert profile.content_type == "podcast"
    assert profile.confidence > 0.0
    assert profile.grid_strategy == "speaker_grid_auto"


def test_clip_hint_boosts_interview_to_podcast():
    profile = ContentIntelligence().detect(
        metadata={"title": "random title"},
        transcript_text="kita bahas topik hari ini",
        clip_hints=[{"content_type": "interview"}],
        autogrid_enabled=True,
    )
    assert profile.content_type == "podcast"
    assert profile.confidence > 0.0


if __name__ == "__main__":
    test_gaming_content_forces_gameplay_facecam_grid_when_enabled()
    test_podcast_content_uses_visual_auto_grid_when_enabled()
    test_autogrid_off_disables_grid_strategy()
    test_dialogue_density_soft_classifies_podcast_not_general_zero()
    test_clip_hint_boosts_interview_to_podcast()
    print("content intelligence tests passed")
