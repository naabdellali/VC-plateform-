import { ModuleResult } from "@/lib/api";

export default function ReasoningTraceView({ result }: { result: ModuleResult }) {
  const steps = result.reasoning_json?.steps || [];
  if (steps.length === 0) {
    return <p style={{ color: "var(--text-dim)", fontSize: 13 }}>No reasoning trace recorded yet.</p>;
  }
  return (
    <div>
      {steps.map((s, i) => (
        <div key={i} className="reasoning-step">
          <div className="step-name">{s.step.replace(/_/g, " ")}</div>
          <pre>{typeof s.content === "string" ? s.content : JSON.stringify(s.content, null, 2)}</pre>
          {s.evidence_ids.length > 0 && (
            <div style={{ marginTop: 6, fontSize: 11, color: "var(--text-dim)" }}>
              → {s.evidence_ids.length} evidence row(s) linked
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
