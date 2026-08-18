"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, Company, Memo } from "@/lib/api";

const REC_COLORS: Record<string, string> = {
  invest: "var(--status-complete)",
  pass: "var(--sev-critical)",
  watchlist: "var(--sev-major)",
  need_more_data: "var(--conf-medium)",
};

export default function MemoPage() {
  const params = useParams<{ id: string }>();
  const companyId = params.id;

  const [memo, setMemo] = useState<Memo | null>(null);
  const [company, setCompany] = useState<Company | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!companyId) return;
    api.getMemo(companyId).then((m) => { setMemo(m); setNotFound(false); }).catch(() => setNotFound(true));
    api.getCompany(companyId).then(setCompany).catch(() => {});
  }, [companyId]);

  useEffect(() => load(), [load]);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      const m = await api.generateMemo(companyId);
      setMemo(m);
      setNotFound(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="container">
      <div className="header">
        <div>
          <Link href={`/company/${companyId}`} className="no-print" style={{ fontSize: 12 }}>← Back to tray</Link>
          <h1 style={{ marginTop: 6 }}>Investment memo{company?.name ? ` — ${company.name}` : ""}</h1>
        </div>
        <div className="no-print" style={{ display: "flex", gap: 10 }}>
          {memo && (
            <button className="btn-secondary" onClick={() => window.print()}>
              Download as PDF
            </button>
          )}
          <button className="btn-secondary" onClick={generate} disabled={busy}>
            {busy ? "Generating..." : memo ? "Regenerate memo" : "Generate memo"}
          </button>
        </div>
      </div>

      {error && <p style={{ color: "var(--sev-critical)" }}>{error}</p>}

      {notFound && !memo && (
        <div className="panel">
          <p>No memo generated yet. Click "Generate memo" once you've reviewed the modules on the tray.</p>
        </div>
      )}

      {memo && (
        <>
          {memo.recommendation && (
            <div className="panel" style={{ borderColor: REC_COLORS[memo.recommendation] }}>
              <div style={{ fontSize: 11, color: "var(--text-dim)", textTransform: "uppercase" }}>Recommendation</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: REC_COLORS[memo.recommendation] }}>
                {memo.recommendation.replace(/_/g, " ").toUpperCase()}
              </div>
            </div>
          )}

          {memo.sections_json?.map((s, i) => (
            <div key={i} className="panel">
              <h2>{s.title}</h2>
              <p style={{ whiteSpace: "pre-wrap", fontSize: 13.5, lineHeight: 1.6 }}>{s.body}</p>
            </div>
          ))}

          {memo.key_questions_json && memo.key_questions_json.length > 0 && (
            <div className="panel">
              <h2>Questions for the founders</h2>
              <ul style={{ fontSize: 13.5, lineHeight: 1.7, paddingLeft: 20 }}>
                {memo.key_questions_json.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
