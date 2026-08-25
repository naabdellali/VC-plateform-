"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, Company, Memo } from "@/lib/api";
import TamSamSomView from "@/components/TamSamSomView";
import CompetitiveLandscapeView from "@/components/CompetitiveLandscapeView";
import MoatView from "@/components/MoatView";

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

  let sectionNumber = 0;

  function titleCase(s: string): string {
    return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }

  return (
    <div className="container">
      <div className="no-print" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", maxWidth: 860, margin: "0 auto 18px" }}>
        <Link href={`/company/${companyId}`} style={{ fontSize: 12 }}>← Back to tray</Link>
        <div style={{ display: "flex", gap: 10 }}>
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

      {error && <p style={{ color: "var(--sev-critical)", maxWidth: 860, margin: "0 auto 14px" }}>{error}</p>}

      {notFound && !memo && (
        <div className="panel" style={{ maxWidth: 860, margin: "0 auto" }}>
          <p>No memo generated yet. Click "Generate memo" once you've reviewed the modules on the tray.</p>
        </div>
      )}

      {memo && (
        <div className="doc-page">
          <div className="doc-header">
            <h1>{company?.name || "…"} — Investment Memo</h1>
            {company && (
              <div className="header-chips" style={{ marginTop: 8 }}>
                <span className="header-chip">{company.industry_tag || company.sector || "Secteur n/a"}</span>
                <span className="header-chip">{titleCase(company.stage)}</span>
              </div>
            )}
          </div>
          <hr className="doc-rule" />

          {memo.sections_json?.map((s, i) => {
            if (s.kind === "overview_tags") {
              return (
                <div key={i} className="doc-section overview-chips">
                  {(s.data?.tags || []).map((tag: string, j: number) => (
                    <span key={j} className="overview-chip">{tag}</span>
                  ))}
                </div>
              );
            }
            if (s.kind === "recommendation") {
              sectionNumber += 1;
              return (
                <div key={i} className="doc-section">
                  <div className="doc-section-title">{sectionNumber}. {s.title}</div>
                  <div className="continue-block">
                    <span className={`continue-label rec-${s.data?.value}`}>{s.data?.label}</span>
                  </div>
                  {s.body && <p className="doc-body-text">{s.body}</p>}
                </div>
              );
            }
            if (s.kind === "tam_sam_som" || s.kind === "competitive_landscape" || s.kind === "moat") {
              sectionNumber += 1;
              return (
                <div key={i}>
                  <div className="doc-section-title">{sectionNumber}. {s.title}</div>
                  {s.kind === "tam_sam_som" ? (
                    <TamSamSomView data={s.data} variant="document" footnotePrefix={`memo-${i}`} />
                  ) : s.kind === "competitive_landscape" ? (
                    <CompetitiveLandscapeView data={s.data} variant="document" footnotePrefix={`memo-${i}`} />
                  ) : (
                    <MoatView data={s.data} variant="document" footnotePrefix={`memo-${i}`} />
                  )}
                </div>
              );
            }
            sectionNumber += 1;
            return (
              <div key={i} className="doc-section">
                <div className="doc-section-title">{sectionNumber}. {s.title}</div>
                <p className="doc-body-text" style={{ whiteSpace: "pre-wrap" }}>{s.body}</p>
              </div>
            );
          })}

          {memo.key_questions_json && memo.key_questions_json.length > 0 && (
            <div className="doc-section">
              <div className="doc-section-title">{sectionNumber + 1}. Questions pour les fondateurs</div>
              <ul className="doc-body-text" style={{ paddingLeft: 20, margin: 0 }}>
                {memo.key_questions_json.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
