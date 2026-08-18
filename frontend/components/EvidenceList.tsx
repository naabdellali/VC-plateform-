import { Evidence } from "@/lib/api";

const ORIGIN_LABEL: Record<string, string> = {
  company_claim: "Deck claim",
  external_source: "External source",
  platform_calculation: "Our calculation",
  platform_inference: "Our analysis",
  unknown: "Unverified",
};

export default function EvidenceList({ evidence }: { evidence: Evidence[] }) {
  // Structured competitor lists get their own visual (CompetitorGrid) - don't
  // also dump them here as raw JSON.
  const visible = evidence.filter((e) => e.value_type !== "competitor_list_json");

  if (visible.length === 0) {
    return <p style={{ color: "var(--text-dim)", fontSize: 13 }}>No sources recorded for this module yet.</p>;
  }
  return (
    <div>
      {visible.map((e) => (
        <div key={e.id} className="source-row">
          <div className={`source-dot conf-${e.confidence}`} title={e.confidence} />
          <div style={{ flex: 1 }}>
            <div className="source-claim">
              {e.claim} {e.value ? <span style={{ color: "var(--accent-strong)" }}> — {typeof e.value === "string" ? e.value : JSON.stringify(e.value)}</span> : null}
            </div>
            <div className="source-meta">
              {ORIGIN_LABEL[e.origin] || e.origin}
              {e.source_name && (
                <>
                  {" · "}
                  {e.source_url ? (
                    <a href={e.source_url} target="_blank" rel="noreferrer">{e.source_name}</a>
                  ) : (
                    <span>{e.source_name}</span>
                  )}
                </>
              )}
              {e.source_publication_date && <> · {e.source_publication_date}</>}
            </div>
            {e.methodology && <div className="source-excerpt">How: {e.methodology}</div>}
            {e.supporting_excerpt && <div className="source-excerpt">"{e.supporting_excerpt}"</div>}
            {e.assumptions_json && e.assumptions_json.length > 0 && (
              <div className="source-excerpt">Assumptions: {e.assumptions_json.join("; ")}</div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
