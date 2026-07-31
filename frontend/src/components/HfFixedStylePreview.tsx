type Props = {
  id: string;
  label: string;
  accent: string;
};

export function HfFixedStylePreview({ id, label, accent }: Props) {
  if (id === "hook_chromatic_gate_v2") return (
    <div className="absolute inset-x-3 bottom-[40%] grid grid-cols-[24px_1fr_10px] bg-zinc-950 text-white shadow-[-5px_5px_0_#00E5FF]" style={{ border: `1px solid ${accent}`, clipPath: "polygon(0 0,94% 0,100% 22%,100% 100%,6% 100%,0 76%)" }}>
      <span className="grid place-items-center bg-[#FF2E88] py-2 text-[6px] font-black text-zinc-950 [writing-mode:vertical-rl]">HF//01</span>
      <strong className="px-2 py-4 text-[11px] font-black uppercase leading-tight tracking-tight">{label}</strong>
      <span className="my-auto h-5 w-1 bg-cyan-300" />
    </div>
  );

  if (id === "hook_orbit_stamp_v2") return (
    <div className="absolute left-1/2 top-[34%] grid h-28 w-40 -translate-x-1/2 place-items-center rounded-[50%] border-2 border-violet-400 bg-zinc-950/85 text-center text-white shadow-[0_0_0_7px_#8B5CF655]">
      <div className="absolute inset-3 -rotate-12 rounded-[50%] border border-dashed border-violet-300" />
      <div className="z-10 px-4">
        <span className="text-[5px] font-black tracking-[.2em] text-violet-300">HYPER / SIGNAL</span>
        <strong className="mt-1 block text-[11px] font-black leading-tight">{label}</strong>
      </div>
    </div>
  );

  if (id === "hook_pixel_ticker_v2") return (
    <div className="absolute inset-x-3 bottom-16 grid grid-cols-[32px_1fr_26px] border-2 border-[#F7FF58] bg-zinc-950 text-white shadow-[4px_4px_0_#FF2E88]">
      <span className="grid place-items-center bg-[#F7FF58] text-[13px] font-black text-black">01</span>
      <div className="px-2 py-2">
        <span className="text-[5px] font-bold text-[#F7FF58]">HF_BREAKPOINT</span>
        <strong className="block text-[10px] font-black uppercase leading-tight">{label}</strong>
      </div>
      <div className="m-2 grid grid-cols-2 gap-0.5">{Array.from({ length: 8 }).map((_, i) => <i key={i} className="bg-[#FF2E88]" />)}</div>
    </div>
  );

  if (id === "hook_blueprint_v2") return (
    <div className="absolute inset-x-3 top-[38%] overflow-hidden border border-sky-300 bg-[#05233EE8] p-3 text-white" style={{ backgroundImage: "linear-gradient(#52C7FF33 1px,transparent 1px),linear-gradient(90deg,#52C7FF33 1px,transparent 1px)", backgroundSize: "8px 8px" }}>
      <span className="text-[5px] font-black tracking-[.2em] text-sky-300">FIG. 01</span>
      <strong className="mt-2 block border-l-2 border-white pl-2 text-[11px] font-black leading-tight">{label}</strong>
      <span className="mt-2 block text-[5px] font-bold text-sky-300">1080 / 1920 · LOCKED</span>
    </div>
  );

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
