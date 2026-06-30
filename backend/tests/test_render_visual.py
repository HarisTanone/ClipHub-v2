"""Visual render test: Apply hook + subtitle to 10s test video.

Creates a synthetic 10s video, renders with all subtitle presets,
extracts screenshots at 2s (hook active) and 4s, 6s, 8s (subtitle active).
Output: PNG screenshots in tests/render_output/ for manual review.

Usage:
    python tests/test_render_visual.py [input_video.mp4]
    
    If no input video provided, generates a 1080x1920 test video.
"""
import os
import sys
import subprocess
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.subtitle_renderer import SubtitleRenderer
from src.domain.entities import SubtitleStyleConfig

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "render_output")


def generate_test_video(output_path: str, duration: float = 10.0) -> bool:
    """Generate a 1080x1920 test video with visible frame counter."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i",
        f"color=c=0x1a1a2e:s=1080x1920:d={duration}:r=30,"
        "drawtext=text='%{n}':x=(w-tw)/2:y=h/2:fontsize=80:fontcolor=white:borderw=3:bordercolor=black,"
        "drawtext=text='FRAME %{n} | t=%{pts\\:hms}':x=20:y=20:fontsize=28:fontcolor=gray",
        "-f", "lavfi", "-i",
        f"sine=frequency=440:duration={duration}:sample_rate=44100",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-shortest",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        print(f"  [ERROR] FFmpeg test video generation failed: {result.stderr[:200]}")
        return False
    return True


def extract_frames(video_path: str, timestamps: list[float], prefix: str) -> list[str]:
    """Extract PNG frames at specific timestamps."""
    paths = []
    for t in timestamps:
        out_path = os.path.join(OUTPUT_DIR, f"{prefix}_t{t:.1f}s.png")
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-ss", str(t), "-frames:v", "1",
            "-q:v", "2", out_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and os.path.exists(out_path):
            paths.append(out_path)
        else:
            print(f"    [WARN] Frame extraction at t={t}s failed")
    return paths


def render_hook_ffmpeg(video_path: str, hook_text: str, output_path: str, hook_style: str = "fade_scale") -> bool:
    """Simple FFmpeg hook overlay for testing (3s duration)."""
    escaped = hook_text.replace("'", "'\\''").replace(":", "\\:")
    # Hook: white text with shadow, visible 0-3s, fade in first 0.5s
    hook_filter = (
        f"drawtext=text='{escaped}'"
        f":fontsize=52:fontcolor=white:borderw=4:bordercolor=black"
        f":shadowx=2:shadowy=2:shadowcolor=black@0.8"
        f":x=(w-text_w)/2:y=(h-text_h)/2"
        f":enable='between(t,0,3)'"
        f":alpha='if(lt(t,0.5),t/0.5,if(gt(t,2.5),1-(t-2.5)/0.5,1))'"
    )
    # Dark overlay behind hook
    overlay_filter = (
        "drawbox=x=0:y=0:w=iw:h=ih:color=black@0.5:t=fill"
        ":enable='between(t,0,3)'"
    )
    filter_chain = f"{overlay_filter},{hook_filter}"
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", filter_chain,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy", "-movflags", "+faststart",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.returncode == 0


def test_subtitle_presets(video_path: str):
    """Test all subtitle rendering modes."""
    renderer = SubtitleRenderer(font_dir="assets/fonts")
    
    # Simulated words (relative to clip start, representing speech at 3-9s)
    test_words = [
        {"word": "Halo", "start": 3.2, "end": 3.6, "highlight": False},
        {"word": "semua", "start": 3.7, "end": 4.1, "highlight": False},
        {"word": "apa", "start": 4.2, "end": 4.5, "highlight": False},
        {"word": "kabar", "start": 4.6, "end": 5.0, "highlight": True},
        {"word": "hari", "start": 5.2, "end": 5.5, "highlight": False},
        {"word": "ini", "start": 5.6, "end": 5.9, "highlight": False},
        {"word": "kita", "start": 6.1, "end": 6.4, "highlight": False},
        {"word": "bahas", "start": 6.5, "end": 6.9, "highlight": True},
        {"word": "tentang", "start": 7.0, "end": 7.4, "highlight": False},
        {"word": "topik", "start": 7.5, "end": 7.9, "highlight": False},
        {"word": "menarik", "start": 8.0, "end": 8.5, "highlight": True},
    ]
    
    presets = {
        "word_pop": SubtitleStyleConfig(
            font_family="Poppins",
            font_size=42,
            color="#FFFFFF",
            highlight_color="#FFCC00",
            line_transition="word_pop",
            max_words_per_line=3,
            position="bottom",
            stroke_width=3,
            background_opacity=0.0,
        ),
        "karaoke_default": SubtitleStyleConfig(
            font_family="Poppins",
            font_size=36,
            color="#FFFFFF",
            highlight_color="#FF4444",
            line_transition="default",
            max_words_per_line=3,
            position="bottom",
            stroke_width=3,
            background_opacity=0.4,
        ),
        "emphasis": SubtitleStyleConfig(
            font_family="Anton",
            font_size=34,
            color="#FFFFFF",
            highlight_color="#FFA500",
            line_transition="emphasis",
            max_words_per_line=3,
            position="bottom",
            stroke_width=2,
        ),
    }
    
    results = {}
    for preset_name, style in presets.items():
        print(f"\n  ─── Preset: {preset_name} ───")
        
        # Step 1: Apply hook
        hooked_path = os.path.join(OUTPUT_DIR, f"{preset_name}_hooked.mp4")
        hook_success = render_hook_ffmpeg(video_path, "Ini Hook Text Testing", hooked_path)
        if not hook_success:
            print(f"    [SKIP] Hook render failed for {preset_name}")
            continue
        print(f"    [OK] Hook rendered")
        
        # Step 2: Apply subtitle
        final_path = os.path.join(OUTPUT_DIR, f"{preset_name}_final.mp4")
        try:
            result_path = renderer.render_subtitles(
                video_path=hooked_path,
                words=test_words,
                style=style,
                output_path=final_path,
                start_offset=0.0,
            )
            if os.path.exists(final_path):
                print(f"    [OK] Subtitle rendered ({os.path.getsize(final_path) // 1024}KB)")
            else:
                print(f"    [WARN] Subtitle output missing, using: {result_path}")
                final_path = result_path
        except Exception as e:
            print(f"    [ERROR] Subtitle render failed: {e}")
            final_path = hooked_path
        
        # Step 3: Extract screenshots
        timestamps = [2.0, 4.0, 6.0, 8.0]
        frames = extract_frames(final_path, timestamps, preset_name)
        print(f"    [OK] Screenshots: {len(frames)} frames extracted")
        results[preset_name] = frames
    
    return results


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Check for input video argument
    input_video = sys.argv[1] if len(sys.argv) > 1 else None
    
    if input_video and os.path.exists(input_video):
        # Use provided video (trim to 10s if needed)
        test_video = os.path.join(OUTPUT_DIR, "test_input_10s.mp4")
        cmd = [
            "ffmpeg", "-y", "-i", input_video,
            "-t", "10", "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
            "-c:a", "aac",
            test_video,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f"[ERROR] Failed to prepare input video: {result.stderr[:200]}")
            return
        print(f"[OK] Input video prepared: {test_video}")
    else:
        # Generate synthetic test video
        test_video = os.path.join(OUTPUT_DIR, "test_synthetic_10s.mp4")
        print("[INFO] No input video provided, generating synthetic test...")
        if not generate_test_video(test_video):
            print("[ERROR] Cannot generate test video (FFmpeg required)")
            return
        print(f"[OK] Synthetic test video: {test_video}")
    
    # Verify video
    probe_cmd = ["ffprobe", "-v", "quiet", "-show_format", "-show_streams", test_video]
    probe = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
    if probe.returncode != 0:
        print("[ERROR] Test video is invalid")
        return
    
    print(f"\n{'='*60}")
    print("VISUAL RENDER TEST — Hook + Subtitle on 10s video")
    print(f"{'='*60}")
    
    # Run all preset tests
    results = test_subtitle_presets(test_video)
    
    # Summary
    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")
    total_frames = 0
    for preset, frames in results.items():
        print(f"  {preset}: {len(frames)} screenshots")
        for f in frames:
            size_kb = os.path.getsize(f) // 1024
            print(f"    → {os.path.basename(f)} ({size_kb}KB)")
        total_frames += len(frames)
    
    print(f"\n  Output directory: {OUTPUT_DIR}")
    print(f"  Total screenshots: {total_frames}")
    print(f"\n  Review screenshots to verify:")
    print(f"  • t=2.0s — Hook should be visible (dark overlay + centered text)")
    print(f"  • t=4.0s — Hook gone, subtitle should appear (no double-render)")
    print(f"  • t=6.0s — Subtitle mid-stream (clear single layer)")
    print(f"  • t=8.0s — Later subtitle (verify no overlap/ghost)")


if __name__ == "__main__":
    main()
