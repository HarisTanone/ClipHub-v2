import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  DEFAULT_HOOK_STYLE,
  DEFAULT_SUBTITLE_STYLE,
  DEFAULT_TEXT_EMPHASIS_STYLE,
  StyleEditorModal,
} from "@/components/StyleEditorModal";

const baseProps = {
  open: true,
  inline: true,
  activeTab: "other" as const,
  onClose: vi.fn(),
  hookStyle: DEFAULT_HOOK_STYLE,
  subtitleStyle: DEFAULT_SUBTITLE_STYLE,
  textEmphasisStyle: DEFAULT_TEXT_EMPHASIS_STYLE,
  onHookChange: vi.fn(),
  onSubtitleChange: vi.fn(),
  onTextEmphasisChange: vi.fn(),
};

describe("StyleEditorModal AI Text feature gate", () => {
  it("disables AI Text while AI Cinematic Text is off", () => {
    render(<StyleEditorModal {...baseProps} aiTextEnabled={false} />);

    const aiTextButton = screen.getByRole("button", { name: "AI Text" });
    expect(aiTextButton).toBeDisabled();
    expect(screen.getByText("Aktifkan AI Cinematic Text untuk mengatur AI Text")).toBeInTheDocument();
    expect(screen.queryByText("AI Cinematic Text", { selector: "h3" })).not.toBeInTheDocument();
    expect(screen.getByText("Transition Style")).toBeInTheDocument();
  });

  it("enables AI Text when AI Cinematic Text is turned on", () => {
    const { rerender } = render(<StyleEditorModal {...baseProps} aiTextEnabled={false} />);

    rerender(<StyleEditorModal {...baseProps} aiTextEnabled />);
    const aiTextButton = screen.getByRole("button", { name: "AI Text" });
    expect(aiTextButton).not.toBeDisabled();

    fireEvent.click(aiTextButton);
    expect(screen.getByText("AI Cinematic Text", { selector: "h3" })).toBeInTheDocument();
  });

  it("closes the AI Text editor when AI Cinematic Text is turned off", async () => {
    const { rerender } = render(<StyleEditorModal {...baseProps} aiTextEnabled />);
    fireEvent.click(screen.getByRole("button", { name: "AI Text" }));
    expect(screen.getByText("AI Cinematic Text", { selector: "h3" })).toBeInTheDocument();

    rerender(<StyleEditorModal {...baseProps} aiTextEnabled={false} />);

    await waitFor(() => {
      expect(screen.queryByText("AI Cinematic Text", { selector: "h3" })).not.toBeInTheDocument();
      expect(screen.getByText("Transition Style")).toBeInTheDocument();
    });
  });
});