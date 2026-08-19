/**
 * Technology module view - pilot for the trigger/signal engine and the
 * InvestmentHypothesis pattern. Shows what's genuinely different here vs.
 * a plain module: a claim ("tech differentiation is defensible") broken
 * into testable sub-conditions rather than asserted outright, and the
 * cross-module signals it fired (e.g. a watch flag raised in Moat's
 * territory) instead of a silent rewrite of another module's conclusion.
 */
export type TechDependency = { name: string; role?: string | null; critical?: boolean; evidence_text?: string | null };
export type SubCondition = { assumption: string; plausibility: string; reason?: string };
export type CrossModuleSignal = { signal: string; detail: string; rationale: string; activates: string[] };

export type TechnologyData = {
  dependencies: TechDependency[];
  proprietary: string[];
  cross_module_signals: CrossModuleSignal[];
  hypothesis: { claim: string; sub_conditions: SubCondition[] };
};

const ACTIVATES_LABEL: Record<string, string> = { moat: "Moat", competition: "Competitive Landscape" };

export default function TechnologyView({ data }: { data: TechnologyData }) {
  return (
    <div>
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

      {data.proprietary.length > 0 && (
        <p style={{ fontSize: 12.5, color: "var(--text-dim)", margin: "8px 0 0" }}>
          Déclaré propriétaire : {data.proprietary.join(", ")}
        </p>
      )}

      {data.cross_module_signals.length > 0 && (
        <p style={{ fontSize: 11.5, color: "var(--text-dim)", marginTop: 10 }}>
          {data.cross_module_signals.map((s, i) => (
            <span key={i}>
              → Signalé à : {s.activates.map((a) => ACTIVATES_LABEL[a] || a).join(", ")} ({s.detail})
              {i < data.cross_module_signals.length - 1 ? " · " : ""}
            </span>
          ))}
        </p>
      )}

      {data.hypothesis && data.hypothesis.sub_conditions?.length > 0 && (
        <div className="hypothesis-block">
          <div className="hypothesis-claim">Hypothèse : {data.hypothesis.claim}</div>
          <div style={{ fontSize: 11, color: "var(--text-dim)", marginBottom: 6 }}>
            Pour que cette hypothèse tienne, les conditions suivantes doivent être vraies — non vérifiées indépendamment à ce stade :
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
