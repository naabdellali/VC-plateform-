import { Evidence } from "@/lib/api";
import { ConfidenceBadge } from "@/components/Badges";

export default function EvidenceList({ evidence }: { evidence: Evidence[] }) {
  if (evidence.length === 0) {
    return <p style={{ color: "var(--text-dim)", fontSize: 13 }}>No evidence recorded for this module yet.</p>;
  }
  return (
    <div>
      {evidence.map((e) => (
        <div key={e.id} className="evidence-row">
          <div className="claim">
            {e.claim} {e.value ? <span style={{ color: "var(--accent)" }}> — {typeof e.value === "string" ? e.value : JSON.stringify(e.value)}</span> : null}
          </div>
          <div className="meta">
            <span style={{ textTransform: "uppercase" }}>{e.origin.replace(/_/g, " ")}</span>
            {" · "}
            <ConfidenceBadge confidence={e.confidence} />
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
          {e.methodology && <div className="excerpt">Methodology: {e.methodology}</div>}
          {e.supporting_excerpt && <div className="excerpt">"{e.supporting_excerpt}"</div>}
          {e.assumptions_json && e.assumptions_json.length > 0 && (
            <div className="excerpt">Assumptions: {e.assumptions_json.join("; ")}</div>
          )}
        </div>
      ))}
    </div>
  );
}
