/**
 * Technology module view. Order matters here per analyst feedback: lead
 * with a plain-language description of what the tech actually is, THEN
 * dependencies, THEN the investment hypothesis at the very bottom with an
 * explanation of why it's there - not the other way around, which read as
 * "hypotheses first, description nowhere."
 */
export type TechDependency = { name: string; role?: string | null; critical?: boolean; evidence_text?: string | null };
export type SubCondition = { assumption: string; plausibility: string; reason?: string };
export type CrossModuleSignal = { signal: string; detail: string; rationale: string; activates: string[] };

export type TechnologyData = {
  tech_summary: string | null;
  dependencies: TechDependency[];
  proprietary: string[];
  cross_module_signals: CrossModuleSignal[];
  questions_to_ask: string[];
  hypothesis: { claim: string; sub_conditions: SubCondition[] };
};

const ACTIVATES_LABEL: Record<string, string> = { moat: "Moat", competition: "Competitive Landscape" };

export default function TechnologyView({ data }: { data: TechnologyData }) {
  return (
    <div>
      {data.tech_summary && (
        <p style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.6, margin: "0 0 14px" }}>{data.tech_summary}</p>
      )}

      {data.proprietary.length > 0 && (
        <p style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-dim)", margin: "0 0 10px" }}>
          Propriétaire : {data.proprietary.join(" ")}
        </p>
      )}

      {data.dependencies.length > 0 && (
        <div className="tech-dep-list">
          {data.dependencies.map((d, i) => (
            <div key={i} className="tech-dep-item">
              <div className="tech-dep-name">
                {d.name}
                {d.critical && <span className="tech-dep-critical">Critique</span>}
              </div>
              {d.role && <div className="tech-dep-role">{d.role}</div>}
            </div>
          ))}
        </div>
      )}

      {data.cross_module_signals.length > 0 && (
        <p style={{ fontSize: 11.5, fontWeight: 600, color: "var(--text-dim)", marginTop: 10 }}>
          {data.cross_module_signals.map((s, i) => (
            <span key={i}>
              → Signalé à : {s.activates.map((a) => ACTIVATES_LABEL[a] || a).join(", ")} ({s.detail})
              {i < data.cross_module_signals.length - 1 ? " · " : ""}
            </span>
          ))}
        </p>
      )}

      {data.questions_to_ask.length > 0 && (
        <div style={{ marginTop: 18, borderTop: "1px dashed var(--panel-border)", paddingTop: 14 }}>
          <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 8 }}>Questions à poser</div>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, lineHeight: 1.7 }}>
            {data.questions_to_ask.map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ul>
        </div>
      )}

      {data.hypothesis && data.hypothesis.sub_conditions?.length > 0 && (
        <div className="hypothesis-block">
          <div className="hypothesis-claim">Hypothèse testée : {data.hypothesis.claim}</div>
          <div style={{ fontSize: 11.5, fontWeight: 600, color: "var(--text-dim)", marginBottom: 8 }}>
            On part d'une hypothèse d'investissement, puis on vérifie ce qui doit être vrai pour qu'elle tienne — ça montre précisément ce qui reste à prouver, plutôt que de conclure directement.
          </div>
          {data.hypothesis.sub_conditions.map((sc, i) => (
            <div key={i} className="subcondition-row">
              <span className={`plausibility-badge ${sc.plausibility}`}>{sc.plausibility}</span>
              <span>
                {sc.assumption}
                {sc.reason && <span style={{ color: "var(--text-dim)" }}> — {sc.reason}</span>}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
