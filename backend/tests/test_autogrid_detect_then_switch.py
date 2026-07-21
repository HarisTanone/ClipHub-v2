"""Detect-then-switch Auto Grid behavior.

Rules under test:
1. 1 person in frame -> single layout (no forced grid)
2. >=2 distinct people co-visible -> double layout after hysteresis
3. Grid panels must use different identities
4. Layout events start single then switch to double when second person enters
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.infrastructure.person_tracker import BBox, TrackedDetection
from src.infrastructure.podcast_reframe_engine import PodcastReframeEngine


FRAME_WIDTH = 1920
FRAME_HEIGHT = 1080
TOTAL_FRAMES = 30


def make_bbox(center_x: float, center_y: float, width: float, height: float) -> BBox:
    return BBox(
        x1=center_x - width / 2,
        y1=center_y - height / 2,
        x2=center_x + width / 2,
        y2=center_y + height / 2,
    )


def make_det(track_id: int, cx: float, cy: float, w: float, h: float, frame_idx: int) -> TrackedDetection:
    return TrackedDetection(track_id=track_id, bbox=make_bbox(cx, cy, w, h), frame_idx=frame_idx)


def create_engine() -> PodcastReframeEngine:
    engine = PodcastReframeEngine()
    engine._face_detector = None
    return engine


def decide(engine: PodcastReframeEngine, per_frame_tracked, skip_ghost_pair_check: bool = False):
    model = engine._build_position_model(per_frame_tracked, FRAME_WIDTH, FRAME_HEIGHT)
    tracked = {
        "per_frame_tracked": per_frame_tracked,
        "person_count": model["person_count"],
        "position_targets": model["position_targets"],
        "position_target_profiles": model["position_target_profiles"],
        "track_to_position": model["track_to_position"],
        "stable_positions": model["stable_positions"],
        "sample_timestamps": [i * engine.SAMPLE_INTERVAL_SEC for i in range(len(per_frame_tracked))],
    }
    decision = engine._decide_autogrid_layout(
        tracked_data=tracked,
        speaker_result=None,
        width=FRAME_WIDTH,
        height=FRAME_HEIGHT,
        skip_ghost_pair_check=skip_ghost_pair_check,
    )
    return model, decision


class TestDetectThenSwitch:
    def setup_method(self):
        self.engine = create_engine()

    def test_single_person_stays_single(self):
        frames = []
        for i in range(TOTAL_FRAMES):
            frames.append([make_det(1, 900, 400, 240, 280, i)])
        model, decision = decide(self.engine, frames, skip_ghost_pair_check=True)
        assert model["person_count"] == 1
        assert decision["layout"] == "single"

    def test_two_people_switch_to_double_with_distinct_ids(self):
        frames = []
        for i in range(TOTAL_FRAMES):
            frames.append([
                make_det(1, 450, 400, 250, 290, i),
                make_det(2, 1450, 410, 240, 280, i),
            ])
        model, decision = decide(self.engine, frames, skip_ghost_pair_check=True)
        assert model["person_count"] == 2
        assert decision["layout"] == "double"
        assert decision["top_track_id"] != decision["bottom_track_id"]
        events = decision.get("layout_events") or []
        assert any(e.get("layout") == "double" for e in events)

    def test_second_person_enters_later_starts_single_then_double(self):
        frames = []
        for i in range(TOTAL_FRAMES):
            dets = [make_det(1, 450, 400, 250, 290, i)]
            # Second person appears from frame 12 onward (~4s @ 3fps)
            if i >= 12:
                dets.append(make_det(2, 1450, 410, 240, 280, i))
            frames.append(dets)

        model, decision = decide(self.engine, frames, skip_ghost_pair_check=True)
        assert model["person_count"] == 2
        assert decision["layout"] == "double"
        assert decision["top_track_id"] != decision["bottom_track_id"]

        events = self.engine._normalise_layout_events(decision.get("layout_events") or [])
        assert events[0]["layout"] == "single"
        assert any(e["layout"] == "double" and e["time"] > 0 for e in events)

    def test_same_person_duplicate_ids_not_forced_as_grid(self):
        # Two track IDs but almost same location (ghost/duplicate)
        frames = []
        for i in range(TOTAL_FRAMES):
            frames.append([
                make_det(1, 960, 400, 260, 300, i),
                make_det(2, 980, 405, 250, 290, i),
            ])
        model, decision = decide(self.engine, frames, skip_ghost_pair_check=False)
        # Ghost elimination / separation should keep this single
        assert decision["layout"] == "single"

    def test_person_first_rejects_two_ids_on_the_same_physical_person(self):
        # Regression: person-first used to trust distinct seat/track IDs and
        # could put two overlapping detections of one person in both panels.
        frames = []
        for i in range(TOTAL_FRAMES):
            frames.append([
                make_det(1, 900, 400, 300, 360, i),
                make_det(2, 1010, 405, 300, 360, i),
            ])

        _, decision = decide(self.engine, frames, skip_ghost_pair_check=True)

        assert decision["layout"] == "single"

    def test_person_first_rejects_fragmented_tracks_pointing_to_same_face(self):
        # Nested loose/tight body boxes can become separate seats even though
        # crop detection resolves both tracker IDs to the same physical face.
        frames = []
        for i in range(TOTAL_FRAMES):
            shared_face = make_bbox(960, 250, 120, 140)
            frames.append([
                TrackedDetection(
                    track_id=1,
                    bbox=BBox(100, 80, 1300, 1000),
                    frame_idx=i,
                    face_bbox=shared_face,
                ),
                TrackedDetection(
                    track_id=2,
                    bbox=BBox(800, 230, 1200, 780),
                    frame_idx=i,
                    face_bbox=shared_face,
                ),
            ])

        model = self.engine._build_position_model_person_first(
            frames, FRAME_WIDTH, FRAME_HEIGHT
        )
        tracked = {
            **model,
            "per_frame_tracked": frames,
            "sample_timestamps": [
                i * self.engine.SAMPLE_INTERVAL_SEC for i in range(TOTAL_FRAMES)
            ],
        }
        decision = self.engine._decide_autogrid_layout(
            tracked_data=tracked,
            speaker_result=None,
            width=FRAME_WIDTH,
            height=FRAME_HEIGHT,
            skip_ghost_pair_check=True,
        )

        assert model["person_count"] == 1
        assert decision["layout"] == "single"

    def test_nested_body_boxes_without_face_are_not_two_people(self):
        # Nested tight-inside-loose body boxes with no face evidence must not
        # unlock double layout (IoU alone can be low while containment is high).
        frames = []
        for i in range(TOTAL_FRAMES):
            frames.append([
                TrackedDetection(
                    track_id=1,
                    bbox=BBox(100, 80, 1300, 1000),
                    frame_idx=i,
                    person_bbox=BBox(100, 80, 1300, 1000),
                ),
                TrackedDetection(
                    track_id=2,
                    bbox=BBox(800, 230, 1200, 780),
                    frame_idx=i,
                    person_bbox=BBox(800, 230, 1200, 780),
                ),
            ])

        assert not self.engine._frame_has_distinct_people(
            frames[0][:1], frames[0][1:], FRAME_WIDTH, FRAME_HEIGHT
        )

        model = self.engine._build_position_model_person_first(
            frames, FRAME_WIDTH, FRAME_HEIGHT
        )
        tracked = {
            **model,
            "per_frame_tracked": frames,
            "sample_timestamps": [
                i * self.engine.SAMPLE_INTERVAL_SEC for i in range(TOTAL_FRAMES)
            ],
        }
        decision = self.engine._decide_autogrid_layout(
            tracked_data=tracked,
            speaker_result=None,
            width=FRAME_WIDTH,
            height=FRAME_HEIGHT,
            skip_ghost_pair_check=True,
        )
        assert model["person_count"] == 1
        assert decision["layout"] == "single"

    def test_normalise_layout_events_inserts_leading_single(self):
        events = self.engine._normalise_layout_events([
            {"layout": "double", "start_time": 2.0, "end_time": 10.0}
        ])
        assert events[0] == {"time": 0.0, "layout": "single"}
        assert events[1]["layout"] == "double"
        assert events[1]["time"] == 2.0
