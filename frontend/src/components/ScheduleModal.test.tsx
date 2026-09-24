import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ScheduleModal } from "./ScheduleModal";

vi.mock("@/components/ui/Toast", () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }) }));
vi.mock("@/hooks/useAuth", () => ({ useAuth: () => ({ user: { id: 1, role: "admin" }, isSuperadmin: true }) }));
vi.mock("@/lib/api", () => ({
  API_BASE: "http://localhost:8000",
  getToken: () => "test-token",
  socialApi: {
    getTikTokTrendingMusic: vi.fn().mockResolvedValue({ tracks: [] }),
    getBatchTikTokMusicRecommendations: vi.fn().mockResolvedValue({ recommendations: [] }),
  },
}));

beforeEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ docs: [], gdrive_configured: true, repliz_configured: true }) }));
});

describe("ScheduleModal hook ordering", () => {
  it("renders, closes, and reopens without changing hook order", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    const props = {
      onClose: vi.fn(),
      jobId: "job_4a82e55aa833",
      clipRank: 1,
      defaultCaption: "Caption",
      hookText: "Hook",
    };
    const { rerender } = render(<ScheduleModal {...props} open />);
    expect(screen.getByText("Post to Social Media")).toBeTruthy();

    rerender(<ScheduleModal {...props} open={false} />);
    expect(screen.queryByText("Post to Social Media")).toBeNull();

    rerender(<ScheduleModal {...props} open />);
    expect(screen.getByText("Post to Social Media")).toBeTruthy();
    expect(consoleError.mock.calls.flat().join(" ")).not.toMatch(/Rendered (more|fewer) hooks|change in the order of Hooks/i);
  });
});
