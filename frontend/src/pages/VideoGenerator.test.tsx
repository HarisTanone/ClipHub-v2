import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const toast = { success: vi.fn(), error: vi.fn() };

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({
    user: { is_superadmin: true, is_premium: true, features: [] },
  }),
}));

vi.mock("@/components/ui/Toast", () => ({
  useToast: () => toast,
}));

vi.mock("@/components/StyleEditorModal", () => ({
  DEFAULT_HOOK_STYLE: {},
  DEFAULT_SUBTITLE_STYLE: {
    stylePreset: "classic",
    engine: "ffmpeg",
    fontFamily: "DejaVu Sans",
    fontSize: 54,
    fontWeight: "800",
    color: "#FFFFFF",
    highlightColor: "#FACC15",
    bgEnabled: true,
    bgColor: "#000000",
    bgOpacity: 0.42,
    bgRadius: 8,
    position: "bottom",
    positionY: 84,
    italic: false,
    uppercase: false,
    strokeEnabled: true,
    strokeColor: "#000000",
    shadowEnabled: true,
    shadowBlur: 8,
    maxWordsPerLine: 3,
    lineTransition: "word_pop",
  },
  StyleEditorModal: () => null,
}));

vi.mock("@/lib/api", () => ({
  API_BASE: "http://localhost:8000",
  getToken: () => "test-token",
}));

describe("VideoGeneratorPage", () => {
  beforeEach(() => {
    localStorage.clear();
    toast.success.mockReset();
    toast.error.mockReset();
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/video-generator/voices")) {
        return Promise.resolve(new Response(JSON.stringify([{ key: "orion", model: "aura-2-orion-en" }]), { status: 200 }));
      }
      if (url.endsWith("/api/video-generator/jobs")) {
        return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }));
      }
      if (url.endsWith("/api/video-generator/generate") && init?.method === "POST") {
        return Promise.resolve(new Response(JSON.stringify({
          job_id: "job-123",
          topic: "Black holes",
          status: "queued",
          progress: 0,
          step_label: "Waiting in queue...",
          target_duration: 65,
          voice: "aura-2-orion-en",
          speed: 1.15,
          num_scenes: 8,
          subtitles_enabled: true,
          subtitle_style_config: {},
          include_bgm: true,
          bgm_volume: 0.15,
          title: null,
          error: null,
          output_path: null,
          created_at: 0,
          completed_at: null,
          scenes_count: 0,
          estimated_duration: null,
          thumbnail_url: null,
        }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({ detail: "Not found" }), { status: 404 }));
    }));
  });

  it("shows render controls for a complete video request", async () => {
    const { VideoGeneratorPage } = await import("@/pages/VideoGenerator");
    render(<VideoGeneratorPage />);

    expect(screen.getByRole("heading", { name: "Video Generator" })).toBeInTheDocument();
    expect(screen.getByText("Opening Hook Title")).toBeInTheDocument();
    expect(screen.getByText("Karaoke Subtitles")).toBeInTheDocument();
    expect(screen.getByText("Background Music")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hook" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("option", { name: /orion/i })).toBeInTheDocument());
  });

  it("submits voice, pacing, scene count, music, and FFmpeg caption style", async () => {
    const { VideoGeneratorPage } = await import("@/pages/VideoGenerator");
    render(<VideoGeneratorPage />);

    await waitFor(() => expect(screen.getByRole("option", { name: /orion/i })).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/topic/i), { target: { value: "Black holes" } });
    fireEvent.change(screen.getByRole("combobox", { name: /voice/i }), { target: { value: "aura-2-orion-en" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Pacing" }), { target: { value: "1.15" } });
    fireEvent.change(screen.getByRole("combobox", { name: /footage pacing & cuts/i }), { target: { value: "8" } });
    fireEvent.click(screen.getByRole("button", { name: /65s/i }));
    fireEvent.click(screen.getByRole("button", { name: "Generate video" }));

    await waitFor(() => {
      const call = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.find(([url, init]) => (
        String(url).endsWith("/api/video-generator/generate") && init?.method === "POST"
      ));
      expect(call).toBeTruthy();
      const payload = JSON.parse(call?.[1]?.body as string);
      expect(payload).toMatchObject({
        topic: "Black holes",
        target_duration: 65,
        voice: "aura-2-orion-en",
        speed: 1.15,
        num_scenes: 8,
        subtitles_enabled: true,
        include_bgm: true,
      });
      expect(payload.subtitle_style_config.engine).toBe("ffmpeg");
    });

    expect(toast.success).toHaveBeenCalled();
  });

  it("triggers Studio Plan and opens the interactive footage studio", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockImplementation((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/video-generator/voices")) {
        return Promise.resolve(new Response(JSON.stringify([{ key: "orion", model: "aura-2-orion-en" }]), { status: 200 }));
      }
      if (url.includes("/api/video-generator/jobs")) {
        return Promise.resolve(new Response(JSON.stringify({
          items: [],
          total: 0,
          page: 1,
          limit: 8,
          total_pages: 1,
        }), { status: 200 }));
      }
      if (url.endsWith("/api/video-generator/plan") && init?.method === "POST") {
        return Promise.resolve(new Response(JSON.stringify({
          job_id: "plan-job-1",
          topic: "Ocean Giants",
          status: "awaiting_selection",
          progress: 100,
          step_label: "Ready for footage selection",
          target_duration: 65,
          voice: "aura-2-orion-en",
          speed: 1.0,
          num_scenes: 2,
          subtitles_enabled: true,
          subtitle_style_config: {},
          include_bgm: true,
          bgm_volume: 0.15,
          title: "Giants of the Deep Ocean",
          error: null,
          output_path: null,
          created_at: 0,
          completed_at: null,
          scenes_count: 2,
          estimated_duration: 60,
          thumbnail_url: null,
          scenes: [
            {
              id: 1,
              narration: "Deep under the waves, colossal creatures thrive.",
              visual: "Giant blue whale swimming in sunlit ocean",
              search_queries: ["blue whale underwater 4k"],
              duration_estimate: 7,
              footage_candidates: [
                {
                  video_id: "cand_1",
                  title: "Blue Whale Ocean 4K",
                  url: "https://youtube.com/watch?v=whale1",
                  thumbnail_url: "https://img.youtube.com/vi/whale1/hqdefault.jpg",
                  duration_seconds: 15,
                  view_count: 120000,
                  channel: "Ocean Planet",
                  platform: "youtube",
                },
                {
                  video_id: "cand_2",
                  title: "Underwater Drone Whale",
                  url: "https://youtube.com/watch?v=whale2",
                  thumbnail_url: "https://img.youtube.com/vi/whale2/hqdefault.jpg",
                  duration_seconds: 22,
                  view_count: 85000,
                  channel: "Deep Sea Docs",
                  platform: "youtube",
                },
              ],
            },
          ],
        }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({ detail: "Not found" }), { status: 404 }));
    });

    const { VideoGeneratorPage } = await import("@/pages/VideoGenerator");
    render(<VideoGeneratorPage />);

    fireEvent.change(screen.getByLabelText(/topic/i), { target: { value: "Ocean Giants" } });
    fireEvent.click(screen.getByRole("button", { name: "Studio Plan & Select Footage" }));

    await waitFor(() => {
      expect(screen.getByRole("dialog", { name: "Scene & Footage Studio" })).toBeInTheDocument();
      expect(screen.getByText(/Footage Studio: Giants of the Deep Ocean/i)).toBeInTheDocument();
      expect(screen.getByText("Blue Whale Ocean 4K")).toBeInTheDocument();
    });
  });
});
