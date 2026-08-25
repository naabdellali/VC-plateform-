import { ModuleResult } from "@/lib/api";

function humanKey(key: string) {
  return key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

function isEmpty(v: unknown) {
  if (v === null || v === undefined) return true;
  if (typeof v === "string") return v.trim() === "";
  if (Array.isArray(v)) return v.length === 0;
  return false;
}

function renderValue(v: unknown): string {
  if (typeof v === "number") return v.toLocaleString();
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}

function StepBody({ content }: { content: unknown }) {
  if (content === null || content === undefined) return null;

  if (typeof content === "string") {
    return <p style={{ margin: 0 }}>{content}</p>;
  }

  if (Array.isArray(content)) {
    if (content.length === 0) return <p style={{ margin: 0, color: "var(--text-dim)" }}>Nothing to report.</p>;
    if (typeof content[0] === "string") {
      return (
        <ul>
          {content.map((s, i) => (
            <li key={i}>{s as string}</li>
          ))}
        </ul>
      );
    }
    return (
      <ul>
        {content.map((item, i) => (
          <li key={i}>
            {typeof item === "object" && item !== null
              ? Object.entries(item as Record<string, unknown>)
                  .filter(([, v]) => !isEmpty(v))
                  .map(([k, v]) => `${humanKey(k)}: ${renderValue(v)}`)
                  .join(" — ")
              : renderValue(item)}
          </li>
        ))}
      </ul>
    );
  }

  if (typeof content === "object") {
    const entries = Object.entries(content as Record<string, unknown>).filter(([, v]) => !isEmpty(v));
    if (entries.length === 0) return <p style={{ margin: 0, color: "var(--text-dim)" }}>Nothing to report.</p>;
    // A single "answer"-shaped object (common for research synthesis steps) reads better as prose.
    if (typeof (content as any).answer === "string") {
      const c = content as any;
      return (
        <div>
          <p style={{ margin: 0 }}>{c.answer}</p>
          {c.conflicting && c.conflict_note && (
            <p style={{ margin: "6px 0 0", color: "var(--sev-major)" }}>⚠ Sources disagree: {c.conflict_note}</p>
          )}
        </div>
      );
    }
    return (
      <ul>
        {entries.map(([k, v]) => (
          <li key={k}>
            <b>{humanKey(k)}:</b> {renderValue(v)}
          </li>
        ))}
      </ul>
    );
  }

  return <p style={{ margin: 0 }}>{renderValue(content)}</p>;
}

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
          <div className="step-body">
            <StepBody content={s.content} />
          </div>
          {s.evidence_ids.length > 0 && (
            <div className="step-link">→ backed by {s.evidence_ids.length} row(s) in the sources list below</div>
          )}
        </div>
      ))}
    </div>
  );
}
