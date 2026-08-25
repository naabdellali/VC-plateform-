/**
 * Technology module view. Three clearly separated blocks, top to bottom,
 * per analyst feedback: (1) what the tech IS, in plain language, with an
 * overall maturity grade; (2) dependencies identified = the risk; (3) the
 * investment hypothesis, at the very bottom, with a plain-language
 * explanation of why it's there. Reading top to bottom should answer:
 * what do they have, is there a tech moat, is there a dependency.
 */
export type TechDependency = { name: string; risk_note?: string | null; critical?: boolean; evidence_text?: string | null };
export type SubCondition = { assumption: string; plausibility: string; reason?: string };
export type CrossModuleSignal = { signal: string; detail: string; rationale: string; activates: string[] };

export type TechnologyData = {
  tech_summary: string | null;
  dependencies: TechDependency[];
  proprietary: string[];
  tech_grade?: string | null;
  tech_grade_reason?: string | null;
  cross_module_signals: CrossModuleSignal[];
  questions_to_ask: string[];
  hypothesis: { claim: string; sub_conditions: SubCondition[] };
};

const ACTIVATES_LABEL: Record<string, string> = { moat: "Moat", competition: "Competitive Landscape" };
const GRADE_CLASS: Record<string, string> = { "Avancé": "grade-wide", "Intermédiaire": "grade-narrow", "Basique": "grade-no" };

export default function TechnologyView({ data }: { data: TechnologyData }) {
  return (
    <div>
      {/* Block 1 - what the tech IS */}
      <div className="tech-block">
        {data.tech_summary && <p className="tech-block-lead">{data.tech_summary}</p>}
        {data.tech_grade && (
          <span className={`moat-badge ${GRADE_CLASS[data.tech_grade] || "grade-narrow"}`} style={{ marginBottom: 10, display: "inline-flex" }}>
            Niveau technique : {data.tech_grade}
          </span>
        )}
        {data.tech_grade_reason && <p className="tech-grade-reason">{data.tech_grade_reason}</p>}
        {data.proprietary.length > 0 && (
          <div className="keyword-tags">
            {data.proprietary.map((p, i) => (
              <span key={i} className="keyword-tag proprietary">{p}</span>
            ))}
          </div>
        )}
      </div>

      {/* Block 2 - dependencies identified = the risk */}
      {data.dependencies.length > 0 && (
        <div className="tech-block">
          <div className="tech-block-heading">Dépendances identifiées</div>
          <div className="tech-dep-list">
            {data.dependencies.map((d, i) => (
              <div key={i} className="tech-dep-item">
                <div className="tech-dep-name">
                  {d.name}
                  {d.critical && <span className="tech-dep-critical">Critique</span>}
                </div>
                {d.risk_note && <div className="tech-dep-role">{d.risk_note}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      {data.cross_module_signals.length > 0 && (
        <p style={{ fontSize: 11.5, fontWeight: 600, color: "var(--text-dim)", marginTop: 4 }}>
          {data.cross_module_signals.map((s, i) => (
            <span key={i}>
              → Signalé à : {s.activates.map((a) => ACTIVATES_LABEL[a] || a).join(", ")} ({s.detail})
              {i < data.cross_module_signals.length - 1 ? " · " : ""}
            </span>
          ))}
        </p>
      )}

      {/* Block 3 - the investment hypothesis, always last */}
      {data.hypothesis && data.hypothesis.sub_conditions?.length > 0 && (
        <div className="tech-block hypothesis-block">
          <div className="tech-block-heading">Hypothèse testée</div>
          <div style={{ fontSize: 11.5, fontWeight: 600, color: "var(--text-dim)", marginBottom: 10, lineHeight: 1.6 }}>
            Concrètement : si chaque condition ci-dessous est vraie, leur avantage technologique tient et sera difficile à copier.
            Si l'une d'elles est fausse, c'est un point à creuser avant d'investir.
          </div>
          <div className="hypothesis-claim">{data.hypothesis.claim}</div>
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
