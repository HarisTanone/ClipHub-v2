import { AlertTriangle, Zap } from "lucide-react";

type Props = {
  id: string;
  label: string;
  accent: string;
};

export function HfFixedStylePreview({ id, label, accent }: Props) {
  // ─── 1. Chromatic Gate (Y2K Split RGB) ───
  if (id === "hook_chromatic_gate_v2") return (
    <div className="absolute inset-x-3 top-[36%] grid grid-cols-[24px_1fr_10px] bg-zinc-950 text-white shadow-[-5px_5px_0_#00E5FF]" style={{ border: `1px solid ${accent}`, clipPath: "polygon(0 0,94% 0,100% 22%,100% 100%,6% 100%,0 76%)" }}>
      <span className="grid place-items-center bg-[#FF2E88] py-2 text-[6px] font-black text-zinc-950 [writing-mode:vertical-rl]">HF//01</span>
      <strong className="px-2 py-3 text-[10px] font-black uppercase leading-tight tracking-tight">{label}</strong>
      <span className="my-auto h-5 w-1 bg-cyan-300" />
    </div>
  );

  // ─── 2. Orbit Stamp (Orbital Verification) ───
  if (id === "hook_orbit_stamp_v2") return (
    <div className="absolute left-1/2 top-[34%] grid h-24 w-36 -translate-x-1/2 place-items-center rounded-[50%] border-2 border-violet-400 bg-zinc-950/85 text-center text-white shadow-[0_0_0_5px_#8B5CF655]">
      <div className="absolute inset-2 -rotate-12 rounded-[50%] border border-dashed border-violet-300" />
      <div className="z-10 px-3">
        <span className="text-[5px] font-black tracking-[.2em] text-violet-300">HYPER / SIGNAL</span>
        <strong className="mt-0.5 block text-[9px] font-black leading-tight">{label}</strong>
      </div>
    </div>
  );

  // ─── 3. Pixel Ticker (Arcade Retro) ───
  if (id === "hook_pixel_ticker_v2") return (
    <div className="absolute inset-x-3 top-[36%] grid grid-cols-[28px_1fr_20px] border-2 border-[#F7FF58] bg-zinc-950 text-white shadow-[3px_3px_0_#FF2E88]">
      <span className="grid place-items-center bg-[#F7FF58] text-[11px] font-black text-black">01</span>
      <div className="px-2 py-1.5">
        <span className="text-[5px] font-bold text-[#F7FF58]">HF_BREAKPOINT</span>
        <strong className="block text-[9px] font-black uppercase leading-tight">{label}</strong>
      </div>
      <div className="m-1.5 grid grid-cols-2 gap-0.5">{Array.from({ length: 6 }).map((_, i) => <i key={i} className="bg-[#FF2E88]" />)}</div>
    </div>
  );

  // ─── 4. Blueprint Reveal (Architectural Cyan) ───
  if (id === "hook_blueprint_v2") return (
    <div className="absolute inset-x-3 top-[35%] overflow-hidden border border-sky-300 bg-[#05233EE8] p-2.5 text-white" style={{ backgroundImage: "linear-gradient(#52C7FF33 1px,transparent 1px),linear-gradient(90deg,#52C7FF33 1px,transparent 1px)", backgroundSize: "8px 8px" }}>
      <span className="text-[5px] font-black tracking-[.2em] text-sky-300">FIG. 01</span>
      <strong className="mt-1 block border-l-2 border-white pl-1.5 text-[9px] font-black leading-tight">{label}</strong>
      <span className="mt-1 block text-[5px] font-bold text-sky-300">1080 / 1920 · LOCKED</span>
    </div>
  );

  // ─── 5. Cyberpunk Tech HUD ───
  if (id === "hook_cyber_hud") return (
    <div className="absolute inset-x-3 top-[35%] relative rounded-xl border border-cyan-400 bg-slate-950/90 p-2.5 text-white shadow-[0_0_15px_rgba(0,240,255,0.3)]">
      <div className="flex items-center justify-between text-[6px] font-mono font-bold text-cyan-400">
        <span>SYS//HOOK</span>
        <span className="h-px flex-1 bg-cyan-500/30 mx-2" />
        <span>#01</span>
      </div>
      <strong className="mt-1 block text-[10px] font-black leading-tight text-white drop-shadow-[0_0_8px_rgba(0,240,255,0.6)] font-mono">{label}</strong>
      <div className="absolute -top-1 -left-1 w-2 h-2 border-t-2 border-l-2 border-cyan-400" />
      <div className="absolute -bottom-1 -right-1 w-2 h-2 border-b-2 border-r-2 border-cyan-400" />
    </div>
  );

  // ─── 6. Frosted Glassmorphism ───
  if (id === "hook_glass_minimal") return (
    <div className="absolute inset-x-4 top-[36%] flex items-center gap-2 rounded-2xl border border-white/30 bg-white/10 px-3 py-2.5 text-white backdrop-blur-md shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
      <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-violet-400 shadow-[0_0_10px_#a78bfa]" />
      <strong className="text-[10px] font-bold leading-tight tracking-tight text-white">{label}</strong>
    </div>
  );

  // ─── 7. Breaking News Live Banner ───
  if (id === "hook_breaking_news") return (
    <div className="absolute inset-x-2 top-[35%] grid grid-cols-[48px_1fr] overflow-hidden rounded-lg border-2 border-red-500 bg-zinc-950 text-white shadow-[0_4px_20px_rgba(239,68,68,0.4)]">
      <div className="flex flex-col items-center justify-center bg-red-600 px-1 py-2 text-center">
        <span className="text-[5px] font-mono font-bold text-yellow-300 leading-none">● LIVE</span>
        <span className="text-[7px] font-black uppercase text-white leading-tight mt-0.5">UPDATE</span>
      </div>
      <div className="flex items-center px-2.5 py-2">
        <strong className="text-[9px] font-black uppercase leading-tight text-white">{label}</strong>
      </div>
    </div>
  );

  // ─── 8. 80s Retro Synthwave ───
  if (id === "hook_retro_synth") return (
    <div className="absolute inset-x-3 top-[35%] rounded-xl border-2 border-rose-500 bg-gradient-to-br from-purple-950/90 to-pink-950/90 p-2.5 text-white shadow-[0_0_20px_rgba(244,63,94,0.4)]">
      <span className="text-[5px] font-mono font-black text-cyan-300 tracking-widest drop-shadow-[0_0_4px_#00f0ff]">TOPIC // REVEAL</span>
      <strong className="mt-0.5 block text-[10px] font-black italic leading-tight text-transparent bg-clip-text bg-gradient-to-r from-white via-pink-200 to-rose-400">{label}</strong>
    </div>
  );

  // ─── 9. Comic Pop Burst ───
  if (id === "hook_comic_pop") return (
    <div className="absolute inset-x-4 top-[35%] -rotate-2 rounded-xl border-3 border-black bg-yellow-400 p-2.5 text-black shadow-[4px_4px_0_#000]">
      <span className="inline-block rounded-md border border-black bg-red-500 px-1.5 py-0.2 text-[6px] font-black text-white mb-1">HEY!</span>
      <strong className="block text-[10px] font-black uppercase leading-tight text-black">{label}</strong>
    </div>
  );

  // ─── 10. Editorial Minimal Pill ───
  if (id === "hook_editorial_pill") return (
    <div className="absolute inset-x-5 top-[36%] flex items-center gap-2 rounded-full border border-white/20 bg-zinc-950/95 px-3 py-2 text-white shadow-xl">
      <span className="h-2 w-2 shrink-0 rounded-full bg-amber-400 shadow-[0_0_8px_#fbbf24]" />
      <div>
        <span className="block text-[5px] font-mono uppercase tracking-widest text-amber-400">FOCUS</span>
        <strong className="text-[9px] font-bold leading-tight text-zinc-100">{label}</strong>
      </div>
    </div>
  );

  // ─── 11. Gradient Aura Glow ───
  if (id === "hook_gradient_aura") return (
    <div className="absolute inset-x-3 top-[35%] rounded-2xl border border-sky-400/40 bg-zinc-950/90 p-3 text-white shadow-[0_0_25px_rgba(56,189,248,0.35),inset_0_0_15px_rgba(167,139,250,0.2)]">
      <strong className="block text-[10px] font-black leading-tight text-transparent bg-clip-text bg-gradient-to-r from-sky-400 via-purple-300 to-pink-400">{label}</strong>
    </div>
  );

  // ─── 12. Caution Stencil Tape ───
  if (id === "hook_cinema_tape") return (
    <div className="absolute inset-x-2 top-[35%] border-y-4 border-yellow-400 bg-black py-2.5 px-3 text-center shadow-2xl">
      <span className="block text-[5px] font-mono text-yellow-400/70 tracking-widest">/// CAUTION WATCH ///</span>
      <strong className="mt-0.5 block font-mono text-[10px] font-black uppercase tracking-wide text-yellow-400">{label}</strong>
    </div>
  );

  // ─── 13. Sci-Fi Hologram Scanner ───
  if (id === "hook_hologram_scan") return (
    <div className="absolute inset-x-3 top-[35%] rounded-xl border border-cyan-400/80 bg-cyan-950/70 p-2.5 text-white shadow-[0_0_20px_rgba(6,182,212,0.35)]">
      <div className="flex items-center gap-1 text-[6px] font-mono font-bold text-cyan-300 mb-0.5">
        <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-pulse" />
        <span>DATA_FEED // 01</span>
      </div>
      <strong className="block text-[9px] font-extrabold leading-tight text-cyan-100">{label}</strong>
    </div>
  );

  // ─── 14. Luxury Obsidian & Gold ───
  if (id === "hook_luxury_noir") return (
    <div className="absolute inset-x-3 top-[35%] rounded-xl border border-amber-400/80 bg-gradient-to-b from-zinc-900 to-black p-3 text-white shadow-[0_10px_25px_rgba(0,0,0,0.8),inset_0_0_10px_rgba(212,175,55,0.15)]">
      <span className="block text-[5px] font-serif uppercase tracking-[0.25em] text-amber-400">INSIGHT</span>
      <strong className="mt-0.5 block font-serif text-[10px] font-black leading-tight text-amber-200 tracking-wide">{label}</strong>
    </div>
  );

  // ─── 15. Top Floating Badge ───
  if (id === "hook_floating_badge") return (
    <div className="absolute left-3 top-[35%] max-w-[85%] flex items-center gap-2 rounded-full border border-emerald-400 bg-zinc-950/90 px-3 py-1.5 text-white shadow-[0_0_15px_rgba(16,185,129,0.3)]">
      <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_#10b981]" />
      <span className="text-[6px] font-mono font-bold text-emerald-400">TOPIC</span>
      <strong className="text-[9px] font-extrabold leading-tight text-white truncate">{label}</strong>
    </div>
  );

  // ─── 16. Kinetic Duotone Split ───
  if (id === "hook_kinetic_split") return (
    <div className="absolute inset-x-3 top-[35%] grid grid-cols-[28px_1fr] overflow-hidden rounded-xl bg-zinc-900 shadow-xl border border-zinc-800">
      <div className="grid place-items-center bg-orange-500 text-[12px] font-black text-white font-mono">01</div>
      <div className="p-2 flex flex-col justify-center">
        <strong className="text-[9px] font-black leading-tight text-white">{label}</strong>
      </div>
    </div>
  );

  // ─── 17. Matrix Rain Cyber Term (NEW) ───
  if (id === "hook_neon_matrix") return (
    <div className="absolute inset-x-3 top-[35%] rounded-lg border-2 border-emerald-400 bg-black/95 p-2.5 text-white shadow-[0_0_20px_rgba(16,185,129,0.45)]">
      <div className="flex items-center justify-between border-b border-emerald-500/30 pb-1 text-[6px] font-mono font-bold text-emerald-400">
        <span>[SYS_ALERT::ROOT]</span>
        <span className="animate-pulse text-emerald-300">ONLINE</span>
      </div>
      <strong className="mt-1 block font-mono text-[9px] font-black uppercase leading-tight text-emerald-300 drop-shadow-[0_0_6px_#10b981]">
        &gt; {label}<span className="animate-pulse">_</span>
      </strong>
    </div>
  );

  // ─── 18. Warning Industrial Hazard (NEW) ───
  if (id === "hook_warning_hazard") return (
    <div className="absolute inset-x-2 top-[34%] rounded-xl border-3 border-amber-500 bg-zinc-950 p-2 text-white shadow-[0_0_25px_rgba(245,158,11,0.35)]">
      <div className="flex items-center justify-between rounded bg-amber-500 px-1.5 py-0.5 text-[6px] font-mono font-black text-black">
        <span className="flex items-center gap-1">
          <AlertTriangle className="h-2.5 w-2.5 text-black fill-black" />
          CRITICAL NOTICE
        </span>
        <span>! ! !</span>
      </div>
      <div className="my-1.5 border-l-3 border-amber-500 pl-2">
        <strong className="block text-[10px] font-black uppercase leading-tight text-amber-300">{label}</strong>
      </div>
      <div className="h-1 w-full bg-[repeating-linear-gradient(45deg,#f59e0b,#f59e0b_6px,#000_6px,#000_12px)] rounded-sm" />
    </div>
  );

  // ─── 19. Y2K Scrapbook Sticker (NEW) ───
  if (id === "hook_sticker_scrapbook") return (
    <div className="absolute inset-x-4 top-[35%] rotate-2 rounded-2xl border-2 border-dashed border-white bg-gradient-to-br from-pink-600 to-rose-700 p-2.5 text-white shadow-[0_8px_0_rgba(0,0,0,0.5),0_0_20px_rgba(236,72,153,0.5)]">
      <div className="absolute -top-2 left-1/2 -translate-x-1/2 rounded-sm bg-white/40 px-2 py-0.5 text-[5px] font-bold text-black/80 backdrop-blur-sm">TAPE</div>
      <strong className="block text-center text-[10px] font-black uppercase leading-tight text-yellow-200 drop-shadow-[0_2px_4px_rgba(0,0,0,0.8)]">{label}</strong>
    </div>
  );

  // ─── 20. Ultra Modern Serif Slate (NEW) ───
  if (id === "hook_cinematic_minimal") return (
    <div className="absolute inset-x-3 top-[36%] border-t border-b border-zinc-500/60 bg-black/85 py-2.5 px-3 text-center backdrop-blur-md">
      <span className="block text-[5px] font-serif uppercase tracking-[0.3em] text-zinc-400">ESSENTIAL DOSSIER</span>
      <strong className="mt-1 block font-serif text-[10px] font-medium leading-tight text-zinc-100 tracking-wider">{label}</strong>
    </div>
  );

  // ─── 21. Electric Plasma Shockwave (NEW) ───
  if (id === "hook_electric_surge") return (
    <div className="absolute inset-x-3 top-[35%] rounded-xl border-2 border-indigo-400 bg-gradient-to-r from-slate-950 via-indigo-950 to-slate-950 p-2.5 text-white shadow-[0_0_25px_rgba(129,140,248,0.5),inset_0_0_10px_rgba(99,102,241,0.3)]">
      <div className="flex items-center gap-1 text-[6px] font-black text-indigo-300 tracking-wider">
        <Zap className="h-2.5 w-2.5 text-yellow-400 fill-yellow-400" />
        VOLTAGE SURGE
      </div>
      <strong className="mt-0.5 block text-[10px] font-black italic uppercase leading-tight text-transparent bg-clip-text bg-gradient-to-r from-indigo-200 via-white to-cyan-300">{label}</strong>
    </div>
  );

  // ─── Subtitles ───
  if (id === "sub_speech_capsule_v2") return (
    <div className="absolute inset-x-7 bottom-14 flex items-center gap-2 rounded-full bg-white px-3 py-2.5 text-zinc-950 shadow-[0_4px_0_#000] after:absolute after:-bottom-3 after:left-5 after:border-[7px] after:border-transparent after:border-t-white">
      <i className="h-2 w-2 shrink-0 rounded-full bg-[#FF2E88]" />
      <strong className="flex-1 text-center text-[10px] font-black leading-tight">{label}</strong>
    </div>
  );

  if (id === "sub_signal_rail_v2") return (
    <div className="absolute inset-x-3 bottom-12 border-t border-[#B7FF00] bg-zinc-950/90 p-2.5 text-white">
      <strong className="block font-mono text-[9px] font-black uppercase leading-tight">{label}</strong>
      <div className="relative mt-2 h-1 bg-lime-950"><i className="block h-full w-2/3 bg-[#B7FF00]" /><b className="absolute left-2/3 top-1/2 h-2 w-2 -translate-y-1/2 rounded-full bg-white shadow-[0_0_8px_#B7FF00]" /></div>
      <span className="mt-1 block font-mono text-[5px] text-[#B7FF00]">HF LIVE TRANSCRIPT</span>
    </div>
  );

  if (id === "sub_vertical_caption_v2") return (
    <div className="absolute bottom-20 left-2 grid w-36 grid-cols-[22px_1fr] border border-cyan-400 bg-zinc-950/90 text-white">
      <span className="grid place-items-center bg-cyan-400 py-2 font-mono text-[5px] font-black text-zinc-950 [writing-mode:vertical-rl]">01 / HF</span>
      <strong className="p-3 text-[10px] font-black leading-tight">{label}</strong>
    </div>
  );

  if (id === "sub_notch_transcript_v2") return (
    <div className="absolute inset-x-6 bottom-12 grid grid-cols-[24px_1fr_3px] items-center gap-2 rounded-t-xl border-b-2 border-amber-500 bg-black px-3 py-2.5 text-white">
      <span className="font-mono text-[5px] font-black text-amber-500">● REC</span>
      <strong className="font-mono text-[9px] font-bold leading-tight">{label}</strong>
      <i className="h-5 bg-amber-500 shadow-[0_0_7px_#FFB000]" />
    </div>
  );

  return <div className="absolute inset-x-3 bottom-8 rounded-lg border-l-4 bg-zinc-950/90 px-3 py-3 text-center text-[11px] font-black text-white" style={{ borderColor: accent }}>{label}</div>;
}

