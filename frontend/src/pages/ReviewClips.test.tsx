import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ReviewClips } from "./ReviewClips";

const mockToast = {
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
  warning: vi.fn(),
};

vi.mock("@/components/ui/Toast", () => ({
  useToast: () => mockToast,
}));

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({
    user: { id: 1, email: "admin@test.com", is_superadmin: true },
  }),
}));

const mockAnalyzeResult = {
  success: true,
  job_id: "analyze_12345",
  youtube_url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  video_duration: 212,
  video_title: "Never Gonna Give You Up",
  thumbnail: "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
  clips: [
    {
      rank: 1,
      start: 15.0,
      end: 55.0,
      duration: 40.0,
      score: 95,
      hook: "Momen Intro Paling Ikonik",
      reason: "High energy buildup",
      content_type: "hook",
      speaker_energy: "high",
    },
    {
      rank: 2,
      start: 70.0,
      end: 110.0,
      duration: 40.0,
      score: 88,
      hook: "Chorus Bagian Pertama",
      reason: "Punchy vocal section",
      content_type: "climax",
      speaker_energy: "high",
    },
  ],
  creative_direction: {
    primary_color: "#FFCC00",
  },
};

vi.mock("@/lib/api", () => ({
  API_BASE: "http://localhost:8000",
  getToken: () => "mock-token",
  analyze: {
    getAnalyzeSession: vi.fn().mockImplementation((jobId: string) => {
      if (jobId === "analyze_12345") {
        return Promise.resolve(mockAnalyzeResult);
      }
      return Promise.reject(new Error("Sesi analisis tidak ditemukan atau sudah kedaluwarsa"));
    }),
    updateAnalyzeSession: vi.fn().mockResolvedValue({ success: true, message: "Updated" }),
    getSourceVideoUrl: vi.fn((jobId: string) => `http://localhost:8000/api/jobs/${jobId}/source-video`),
  },
  presets: {
    list: vi.fn().mockResolvedValue([
      { id: 1, name: "Shorts Modern", slug: "shorts-modern" },
    ]),
  },
  socialApi: {
    getPlatformsStatus: vi.fn().mockResolvedValue({
      platforms: {},
      auto_post_enabled: false,
    }),
  },
  jobs: {
    create: vi.fn().mockResolvedValue({ job_id: "job_created_999" }),
  },
}));

describe("ReviewClips Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loads and displays video title and clips from analyze session", async () => {
    render(
      <MemoryRouter initialEntries={["/jobs/review/analyze_12345"]}>
        <Routes>
          <Route path="/jobs/review/:sessionId" element={<ReviewClips />} />
        </Routes>
      </MemoryRouter>
    );

    // Initial loading indicator
    expect(screen.getByText(/Memuat Sesi Review Clips/i)).toBeInTheDocument();

    // Wait for content to appear
    await waitFor(() => {
      expect(screen.getByText("Review & Edit Clips")).toBeInTheDocument();
    });

    expect(screen.getByText(/Never Gonna Give You Up/i)).toBeInTheDocument();
    expect(screen.getAllByText("Momen Intro Paling Ikonik").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Chorus Bagian Pertama").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Proses 2 Klip Terpilih")).toBeInTheDocument();
  });

  it("handles clip inclusion/exclusion toggle and updates count", async () => {
    render(
      <MemoryRouter initialEntries={["/jobs/review/analyze_12345"]}>
        <Routes>
          <Route path="/jobs/review/:sessionId" element={<ReviewClips />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Proses 2 Klip Terpilih")).toBeInTheDocument();
    });

    // Checkboxes for the 2 clips
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes.length).toBe(2);

    // Uncheck first clip
    fireEvent.click(checkboxes[0]);

    await waitFor(() => {
      expect(screen.getByText("Proses 1 Klip Terpilih")).toBeInTheDocument();
    });
  });

  it("opens render settings modal and allows choosing aspect ratio", async () => {
    render(
      <MemoryRouter initialEntries={["/jobs/review/analyze_12345"]}>
        <Routes>
          <Route path="/jobs/review/:sessionId" element={<ReviewClips />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Pengaturan Render")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Pengaturan Render"));

    await waitFor(() => {
      expect(screen.getByText("Format Rasio Video")).toBeInTheDocument();
      expect(screen.getByText("16:9 (YouTube)")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("16:9 (YouTube)"));
    fireEvent.click(screen.getByText("Tutup & Simpan"));

    await waitFor(() => {
      expect(screen.queryByText("Format Rasio Video")).not.toBeInTheDocument();
    });
  });

  it("shows error state when session is invalid or not found", async () => {
    render(
      <MemoryRouter initialEntries={["/jobs/review/invalid_session"]}>
        <Routes>
          <Route path="/jobs/review/:sessionId" element={<ReviewClips />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Sesi Review Tidak Ditemukan")).toBeInTheDocument();
      expect(screen.getByText("Kembali ke Buat Job Baru")).toBeInTheDocument();
    });
  });
});
