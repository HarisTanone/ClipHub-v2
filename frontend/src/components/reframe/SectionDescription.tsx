/**
 * SectionDescription — Reusable component for section-level pipeline descriptions.
 *
 * Renders a small badge indicating the pipeline stage plus a muted description paragraph.
 * Used once per Card section in the Reframe Tuning tab to give users contextual guidance
 * about what group of sliders controls which processing phase.
 */

interface SectionDescriptionProps {
  /** Pipeline stage label (e.g. "Frame Sampling", "Split-Screen Composition") */
  pipelineStage: string;
  /** 1-2 sentence explanation of what this section controls */
  description: string;
}

export function SectionDescription({ pipelineStage, description }: SectionDescriptionProps) {
  return (
    <div className="flex flex-col gap-1.5 mb-3" data-testid="section-description">
      <span className="inline-flex items-center self-start px-1.5 py-0.5 rounded bg-zinc-800 text-[10px] font-medium text-zinc-400 border border-zinc-700/50">
        {pipelineStage}
      </span>
      <p className="text-[11px] text-zinc-500 leading-relaxed">
        {description}
      </p>
    </div>
  );
}
