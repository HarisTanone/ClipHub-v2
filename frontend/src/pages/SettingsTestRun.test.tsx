import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

let isSuperadmin = true;

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({ user: { is_superadmin: isSuperadmin }, isAuthenticated: true }),
}));

vi.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn() }),
}));

vi.mock("@/lib/api", () => ({
  system: { health: () => Promise.resolve({ version: "1.0", mode: "test" }) },
  storage: { clearProcessingData: vi.fn() },
  API_BASE: "http://localhost:8000",
  getToken: () => "test-token",
}));

describe("Settings server test gate", () => {
  beforeEach(() => {
    isSuperadmin = true;
    vi.stubGlobal("confirm", vi.fn(() => true));
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/settings/test-run/status")) {
        return Promise.resolve(new Response(JSON.stringify({
          data: { status: "idle", stage: "not_started", message: "No runs", video_available: false, deploy_requested: false },
          log: "waiting",
        }), { status: 200, headers: { "Content-Type": "application/json" } }));
      }
      if (url.endsWith("/api/settings/test-run") && init?.method === "POST") {
        return Promise.resolve(new Response(JSON.stringify({
          data: { status: "running", stage: "initializing", message: "started", video_available: false, deploy_requested: false },
        }), { status: 202, headers: { "Content-Type": "application/json" } }));
      }
      return Promise.resolve(new Response(JSON.stringify({ data: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }));
    }));
  });

  it("is visible to superadmin and can trigger test.sh in no-deploy mode", async () => {
    const { Settings } = await import("@/pages/Settings");
    render(<Settings />);
    fireEvent.click(screen.getByText("Test & Deploy"));
    await waitFor(() => expect(screen.getByTestId("test-run-log")).toHaveTextContent("waiting"));

    fireEvent.click(screen.getByRole("button", { name: "Run Tests" }));
    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/settings/test-run",
      expect.objectContaining({ method: "POST" }),
    ));
  });

  it("is hidden from non-superadmin users", async () => {
    isSuperadmin = false;
    const { Settings } = await import("@/pages/Settings");
    render(<Settings />);
    expect(screen.queryByText("Test & Deploy")).not.toBeInTheDocument();
  });
});