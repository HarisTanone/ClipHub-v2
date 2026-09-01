import { useEffect } from "react";
import { PAGINATION_PAGE_SIZE } from "./types";

export function loadGoogleFont(fontFamily?: string) {
  if (!fontFamily || fontFamily === "monospace" || typeof document === "undefined") return;
  const id = `gfont-${fontFamily.replace(/\s/g, "")}`;
  if (document.getElementById(id)) return;
  const link = document.createElement("link");
  link.id = id;
  link.rel = "stylesheet";
  link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(fontFamily)}:wght@400;500;600;700;800;900&display=swap`;
  document.head.appendChild(link);
}

export function useGoogleFont(fontFamily?: string) {
  useEffect(() => {
    loadGoogleFont(fontFamily);
  }, [fontFamily]);
}

export function getHookAnimationClass(animation: string): string {
  switch (animation) {
    case "fade_scale": return "animate-[fadeScalePreview_2.5s_ease-in-out_infinite]";
    case "slide_up": return "animate-[slideUpPreview_2s_ease-in-out_infinite]";
    case "slide_punch_framer": return "animate-[slidePunchPreview_2s_ease-out_infinite]";
    case "glitch": return "animate-[glitchJitter_0.5s_steps(2)_infinite]";
    case "typewriter": return "animate-[typewriterReveal_3s_steps(20)_infinite]";
    case "glitch_rgb": return ""; // uses DOM-based multi-layer render
    case "shake_neon": return ""; // uses DOM-based multi-layer render
    case "cinematic_reveal": return "animate-[cinematicRevealText_3.5s_ease-out_infinite]";
    case "danger_bold": return "animate-[dangerPulse_1.2s_ease-in-out_infinite]";
    case "bold_slam": return "animate-[boldSlamPreview_2s_ease-out_infinite]";
    case "podcast_lower_third": return "animate-[podcastLowerPreview_2.8s_ease-out_infinite]";
    case "quote_card": return "animate-[quoteCardPreview_3s_ease-out_infinite]";
    case "waveform_pulse": return "animate-[waveformTextPreview_1.1s_ease-in-out_infinite]";
    case "breaking_tape": return "animate-[breakingTapePreview_2.5s_ease-out_infinite]";
    case "mic_drop": return "animate-[micDropPreview_2.5s_cubic-bezier(.2,.85,.25,1)_infinite]";
    case "split_panel": return "animate-[splitPanelPreview_2.6s_ease-in-out_infinite]";
    case "kinetic_stack": return "animate-[kineticStackPreview_2.4s_ease-in-out_infinite]";
    case "glass_flash": return "animate-[glassFlashPreview_2.8s_ease-in-out_infinite]";
    case "marker_swipe": return "animate-[markerSwipePreview_2.4s_ease-in-out_infinite]";
    case "signal_scan": return "animate-[signalScanPreview_2.5s_ease-in-out_infinite]";
    case "comment_reply": return "animate-[slideUpPreview_2.4s_ease-in-out_infinite]";
    case "search_prompt": return "animate-[fadeScalePreview_2.5s_ease-in-out_infinite]";
    case "countdown_list": return "animate-[slidePunchPreview_2.4s_ease-out_infinite]";
    case "pov_stamp": return "animate-[fadeScalePreview_2.5s_ease-in-out_infinite]";
    default: return "";
  }
}

export function getHookPreviewSample(animation: string): string {
  switch (animation) {
    case "podcast_lower_third": return "bagian ini bikin hostnya diam";
    case "quote_card": return "kalimat ini mengubah cara lihat topiknya";
    case "waveform_pulse": return "dengerin 5 detik ini dulu";
    case "breaking_tape": return "opini ini bakal kebelah dua";
    case "mic_drop": return "ini jawaban paling brutalnya";
    case "split_panel": return "dua sisi ini bikin debat panas";
    case "kinetic_stack": return "ini alasan orang salah paham";
    case "glass_flash": return "bagian kecil ini paling mahal";
    case "marker_swipe": return "kalimat ini wajib ditandai";
    case "signal_scan": return "sinyalnya kelihatan dari sini";
    case "comment_reply": return "gimana caranya mulai dari nol?";
    case "search_prompt": return "cara naik jabatan tanpa burnout";
    case "countdown_list": return "3 kesalahan yang bikin kamu stuck";
    case "pov_stamp": return "kamu akhirnya berani bilang tidak";
    case "cinematic_reveal": return "mereka gak cerita bagian ini";
    case "danger_bold": return "jangan skip bagian ini";
    case "shake_neon": return "ini yang bikin rame";
    case "glitch_rgb": return "ada yang janggal di sini";
    default: return "hook podcast yang bikin berhenti scroll";
  }
}

export function getSubAnimationClass(animation: string): string {
  switch (animation) {
    case "pop": return "animate-[popIn_1.5s_ease-in-out_infinite]";
    case "fade": return "animate-[fadeIn_2s_ease-in-out_infinite]";
    case "slide": return "animate-[slideInUp_1.5s_ease-in-out_infinite]";
    default: return "";
  }
}

/** Downscale an uploaded watermark image to a max of 512px so the data URL
 *  stays small (it is persisted in job payloads & presets). PNG is re-encoded
 *  to preserve alpha transparency. */
export function downscaleImageDataUrl(file: File, maxSize = 512): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      try {
        const scale = Math.min(1, maxSize / Math.max(img.naturalWidth, img.naturalHeight));
        const w = Math.max(1, Math.round(img.naturalWidth * scale));
        const h = Math.max(1, Math.round(img.naturalHeight * scale));
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          // No canvas context — fall back to reading the raw file as a data URL
          URL.revokeObjectURL(url);
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result || ""));
          reader.onerror = () => reject(new Error("Gagal membaca gambar"));
          reader.readAsDataURL(file);
          return;
        }
        ctx.drawImage(img, 0, 0, w, h);
        URL.revokeObjectURL(url);
        resolve(canvas.toDataURL("image/png"));
      } catch { URL.revokeObjectURL(url); reject(new Error("Gagal memproses gambar")); }
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Gagal membaca gambar")); };
    img.src = url;
  });
}

export function getPageItems<T>(items: T[], page: number, pageSize = PAGINATION_PAGE_SIZE) {
  return items.slice((page - 1) * pageSize, page * pageSize);
}

export function getPageForIndex(index: number, pageSize = PAGINATION_PAGE_SIZE) {
  return index < 0 ? 1 : Math.floor(index / pageSize) + 1;
}

export const STYLE_EDITOR_KEYFRAMES = `
  @keyframes fadeScalePreview { 0%,100% { opacity:0.3; transform:translateY(-50%) scale(0.92); } 50% { opacity:1; transform:translateY(-50%) scale(1); } }
  @keyframes slideUpPreview { 0%,100% { opacity:0; transform:translateY(-40%); } 20%,80% { opacity:1; transform:translateY(-50%); } }
  @keyframes slidePunchPreview { 0% { opacity:0; transform:translateY(-50%) translateX(-50px); } 20% { opacity:1; transform:translateY(-50%) translateX(3px) scale(1.02); } 30%,80% { opacity:1; transform:translateY(-50%) translateX(0) scale(1); } 100% { opacity:0; transform:translateY(-50%); } }
  @keyframes glitchJitter { 0% { transform:translateY(-50%) translate(-2px,0); } 25% { transform:translateY(-50%) translate(2px,1px); } 50% { transform:translateY(-50%) translate(-1px,-1px); } 75% { transform:translateY(-50%) translate(1px,0); } 100% { transform:translateY(-50%); } }
  @keyframes typewriterReveal { 0% { width:0; } 50%,100% { width:100%; } }
  @keyframes glitchRedLayer {
    0%,100% { transform:translate(-4px,0); }
    25% { transform:translate(-1px,0); }
    50% { transform:translate(-7px,0); }
    75% { transform:translate(-2px,1px); }
  }
  @keyframes glitchCyanLayer {
    0%,100% { transform:translate(4px,0); }
    25% { transform:translate(1px,0); }
    50% { transform:translate(7px,0); }
    75% { transform:translate(2px,-1px); }
  }
  @keyframes shakeNeonGlow {
    0%,100% { transform:translate(0,0); }
    20% { transform:translate(2px,-1px); }
    40% { transform:translate(-1px,2px); }
    60% { transform:translate(1px,1px); }
    80% { transform:translate(-2px,-1px); }
  }
  @keyframes shakeNeonMain {
    0%,100% { transform:translate(0,0); }
    15% { transform:translate(1.5px,-1px); }
    30% { transform:translate(-1px,1px); }
    45% { transform:translate(1px,0.5px); }
    60% { transform:translate(-1.5px,-0.5px); }
    75% { transform:translate(0.5px,1px); }
    90% { transform:translate(-0.5px,-1px); }
  }
  @keyframes cinematicRevealText {
    0% { opacity:0; transform:translateY(-50%) scale(0.96); }
    25% { opacity:1; transform:translateY(-50%) scale(1); }
    75% { opacity:1; transform:translateY(-50%) scale(1); }
    100% { opacity:0; transform:translateY(-50%) scale(0.96); }
  }
  @keyframes dangerPulse {
    0%,100% { transform:translateY(-50%) scale(1); }
    25% { transform:translateY(-50%) scale(1.03); }
    50% { transform:translateY(-50%) scale(1); }
    75% { transform:translateY(-50%) scale(1.02); }
  }
  @keyframes boldSlamPreview {
    0% { transform:translateY(-50%) scale(0) rotate(-8deg); }
    20% { transform:translateY(-50%) scale(1.05) rotate(0deg); }
    30% { transform:translateY(-50%) scale(1) rotate(0deg); }
    50%,60% { transform:translateY(-50%) translate(2px,-1px) scale(1); }
    55% { transform:translateY(-50%) translate(-2px,1px) scale(1); }
    70% { transform:translateY(-50%) scale(1) rotate(0deg); }
    100% { transform:translateY(-50%) scale(1) rotate(0deg); }
  }
  @keyframes podcastLowerPreview {
    0% { opacity:0; transform:translateY(22px) scale(0.98); }
    18%,82% { opacity:1; transform:translateY(0) scale(1); }
    100% { opacity:0; transform:translateY(10px) scale(0.99); }
  }
  @keyframes podcastOnAirPulse {
    0%,100% { opacity:0.35; transform:scale(0.85); }
    50% { opacity:1; transform:scale(1.12); }
  }
  @keyframes quoteCardPreview {
    0% { opacity:0; transform:translateY(-50%) rotate(-2deg) scale(0.88); }
    20%,82% { opacity:1; transform:translateY(-50%) rotate(-1deg) scale(1); }
    100% { opacity:0; transform:translateY(-50%) rotate(1deg) scale(0.95); }
  }
  @keyframes waveformTextPreview {
    0%,100% { transform:translateY(-50%) scale(0.98); }
    50% { transform:translateY(-50%) scale(1.03); }
  }
  @keyframes waveformBarPreview {
    0%,100% { transform:scaleY(0.34); opacity:0.45; }
    50% { transform:scaleY(1); opacity:1; }
  }
  @keyframes breakingTapePreview {
    0% { opacity:0; transform:translateY(-50%) translateX(-70px) rotate(-4deg); }
    18%,82% { opacity:1; transform:translateY(-50%) translateX(0) rotate(-4deg); }
    100% { opacity:0; transform:translateY(-50%) translateX(55px) rotate(-4deg); }
  }
  @keyframes micDropPreview {
    0% { opacity:0; transform:translateY(-95%) scale(1.18) rotate(-8deg); }
    18% { opacity:1; transform:translateY(-50%) scale(0.94) rotate(2deg); }
    28%,78% { opacity:1; transform:translateY(-50%) scale(1) rotate(0deg); }
    100% { opacity:0; transform:translateY(-42%) scale(0.96); }
  }
  @keyframes splitPanelPreview {
    0% { opacity:0; transform:translateY(-50%) translateX(-32px); }
    18% { opacity:1; transform:translateY(-50%) translateX(0); }
    50% { opacity:1; transform:translateY(calc(-50% - 3px)) translateX(0); }
    82% { opacity:1; transform:translateY(-50%) translateX(0); }
    100% { opacity:0; transform:translateY(-50%) translateX(24px); }
  }
  @keyframes kineticStackPreview {
    0% { opacity:0; transform:translateY(-50%) scale(0.92) rotate(-2deg); }
    18%,78% { opacity:1; transform:translateY(-50%) scale(1) rotate(-1deg); }
    45% { opacity:1; transform:translateY(calc(-50% - 4px)) scale(1.02) rotate(1deg); }
    100% { opacity:0; transform:translateY(-42%) scale(0.96) rotate(2deg); }
  }
  @keyframes glassFlashPreview {
    0% { opacity:0; transform:translateY(-50%) scale(0.96); }
    20%,84% { opacity:1; transform:translateY(-50%) scale(1); }
    52% { opacity:1; transform:translateY(calc(-50% - 3px)) scale(1.01); }
    100% { opacity:0; transform:translateY(-50%) scale(0.97); }
  }
  @keyframes markerSwipePreview {
    0% { transform:scaleX(0); opacity:0; }
    18%,78% { transform:scaleX(1); opacity:1; }
    100% { transform:scaleX(0.15); opacity:0; }
  }
  @keyframes signalScanPreview {
    0% { opacity:0; transform:translateY(-50%) scale(0.98); }
    20%,82% { opacity:1; transform:translateY(-50%) scale(1); }
    50% { opacity:1; transform:translateY(calc(-50% - 2px)) scale(1.01); }
    100% { opacity:0; transform:translateY(-50%) scale(0.98); }
  }
  @keyframes signalScanLine {
    0% { transform:translateX(-120%); opacity:0; }
    18%,76% { opacity:1; }
    100% { transform:translateX(120%); opacity:0; }
  }
  @keyframes popIn { 0%,100% { transform:scale(0.9); opacity:0.5; } 50% { transform:scale(1.05); opacity:1; } }
  @keyframes fadeIn { 0%,100% { opacity:0.3; } 50% { opacity:1; } }
  @keyframes slideInUp { 0%,100% { transform:translateY(4px); opacity:0.4; } 50% { transform:translateY(0); opacity:1; } }
`;
