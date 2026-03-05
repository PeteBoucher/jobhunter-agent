interface Props {
  score: number | null | undefined;
  size?: "sm" | "md";
}

export function MatchScoreBar({ score, size = "md" }: Props) {
  const pct = score ?? 0;
  const colour =
    pct >= 70 ? "bg-green-500" : pct >= 40 ? "bg-amber-400" : "bg-red-400";
  const textColour =
    pct >= 70 ? "text-green-700" : pct >= 40 ? "text-amber-700" : "text-red-600";
  const h = size === "sm" ? "h-1.5" : "h-2";

  return (
    <div className="flex items-center gap-2">
      <div className={`flex-1 rounded-full bg-gray-100 ${h}`}>
        <div
          className={`${h} rounded-full ${colour} transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`text-xs font-semibold tabular-nums ${textColour}`}>
        {Math.round(pct)}%
      </span>
    </div>
  );
}
