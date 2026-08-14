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
    expect(screen.getByText("Burn-in subtitles")).toBeInTheDocument();
    expect(screen.getByText("Background music")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Customize" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("option", { name: /orion/i })).toBeInTheDocument());
  });

  it("submits voice, pacing, scene count, music, and FFmpeg caption style", async () => {
    const { VideoGeneratorPage } = await import("@/pages/VideoGenerator");
    render(<VideoGeneratorPage />);

    await waitFor(() => expect(screen.getByRole("option", { name: /orion/i })).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "Black holes" } });
    fireEvent.change(screen.getByLabelText("Narrator voice"), { target: { value: "aura-2-orion-en" } });
    fireEvent.change(screen.getByLabelText("Pacing"), { target: { value: "1.15" } });
    fireEvent.change(screen.getByLabelText("Scene count"), { target: { value: "8" } });
    fireEvent.click(screen.getByRole("button", { name: /65s balanced/i }));
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
});
