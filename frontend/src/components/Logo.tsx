export default function Logo({ inverted = false }: { inverted?: boolean }) {
  return (
    <span className="flex items-center gap-2 font-semibold tracking-tight">
      <span className="grid size-8 place-items-center rounded-lg bg-brand-600 text-sm font-bold text-white">
        SP
      </span>
      <span className={inverted ? "text-white" : "text-slate-900"}>
        SocialPilot <span className="text-brand-500">AI</span>
      </span>
    </span>
  );
}
