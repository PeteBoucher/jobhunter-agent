import type { MatchScore } from "@/lib/types";

interface Props {
  match: MatchScore;
}

const rows = [
  { label: "Skills", key: "skill_score" as const, max: 40 },
  { label: "Title", key: "title_score" as const, max: 30 },
  { label: "Experience", key: "experience_score" as const, max: 10 },
  { label: "Location / Remote", key: "location_or_remote_score" as const, max: 10 },
  { label: "Salary", key: "salary_score" as const, max: 10 },
];

export function ScoreBreakdown({ match }: Props) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5">
      <h3 className="mb-4 text-sm font-semibold text-gray-700">Match breakdown</h3>
      <div className="space-y-3">
        {rows.map(({ label, key, max }) => {
          const val = match[key] ?? 0;
          const pct = (val / max) * 100;
          const colour =
            pct >= 70 ? "bg-green-500" : pct >= 40 ? "bg-amber-400" : "bg-red-400";
          return (
            <div key={key}>
              <div className="mb-1 flex justify-between text-xs text-gray-500">
                <span>{label}</span>
                <span className="font-medium text-gray-700">
                  {val.toFixed(0)} / {max}
                </span>
              </div>
              <div className="h-2 rounded-full bg-gray-100">
                <div
                  className={`h-2 rounded-full ${colour}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-4 flex items-center justify-between border-t border-gray-100 pt-3">
        <span className="text-sm font-semibold text-gray-700">Total</span>
        <span className="text-lg font-bold text-blue-600">
          {Math.round(match.match_score ?? 0)}%
        </span>
      </div>
    </div>
  );
}
