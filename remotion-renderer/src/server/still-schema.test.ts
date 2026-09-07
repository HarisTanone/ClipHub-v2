import { describe, expect, it } from "vitest";
import { STILL_HOOK_ANIMATIONS } from "./index";

describe("native still hook registry", () => {
  it("accepts every custom HookLayer animation exposed by the frontend", () => {
    const required = [
      "comment_reply", "search_prompt", "countdown_list", "pov_stamp",
      "news_viralin_badge", "news_portal_pantau", "news_offset_box",
      "brutalist_bracket", "quote_strip_tape", "paper_clip_scrap",
      "trending_radar", "news_breaking_live",
    ];
    for (const animation of required) {
      expect(STILL_HOOK_ANIMATIONS).toContain(animation);
    }
  });
});