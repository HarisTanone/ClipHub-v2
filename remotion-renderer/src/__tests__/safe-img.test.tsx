import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import { SafeImg } from "../components/SafeImg";

// delayRender/continueRender are remotion runtime APIs; stub them for DOM tests.
vi.mock("remotion", async () => {
  const actual = await vi.importActual<any>("remotion");
  return {
    ...actual,
    delayRender: vi.fn(() => 1),
    continueRender: vi.fn(),
    Img: (props: any) => <img alt="" {...props} />,
  };
});

describe("SafeImg", () => {
  it("renders placeholder div when src is empty (no hang)", () => {
    const { container } = render(<SafeImg src="" placeholderColor="#222222" />);
    const div = container.querySelector("div");
    expect(div).toBeTruthy();
    expect(div?.getAttribute("style")).toContain("#222222");
    expect(container.querySelector("img")).toBeNull();
  });

  it("renders Img when src provided", () => {
    const { container } = render(<SafeImg src="http://localhost/ok.png" />);
    expect(container.querySelector("img")).toBeTruthy();
    expect(container.querySelector("img")?.getAttribute("src")).toBe("http://localhost/ok.png");
  });
});
