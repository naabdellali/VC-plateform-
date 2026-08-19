"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, Company, TrayTile, RedFlag } from "@/lib/api";

const STATUS_COLOR_VAR: Record<string, string> = {
  complete: "--status-complete",
  needs_review: "--status-needs_review",
  insufficient_evidence: "--status-insufficient_evidence",
  high_risk: "--status-high_risk",
  pending: "--status-pending",
};

const SEV_ICON: Record<string, string> = {
  critical: "●",
  major: "▲",
  watch: "◆",
};

const SEV_LABEL: Record<string, string> = {
  critical: "Critique",
  major: "Majeur",
  watch: "À surveiller",
};

const CATEGORY_LABEL: Record<string, string> = {
  market: "Marché",
  competition: "Concurrence",
  moat: "Moat",
  technology: "Technologie",
  traction: "Traction",
  business_model: "Business model",
  founders: "Équipe",
};

const SEV_ORDER: Record<string, number> = { critical: 0, major: 1, watch: 2 };

function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function CompanyTrayPage() {
  const params = useParams<{ id: string }>();
  const companyId = params.id;

  const [company, setCompany] = useState<Company | null>(null);
  const [tray, setTray] = useState<TrayTile[] | null>(null);
  const [flags, setFlags] = useState<RedFlag[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedFlags, setExpandedFlags] = useState<Set<string>>(new Set());
  const [hoveredFlag, setHoveredFlag] = useState<string | null>(null);

  const toggleFlag = (id: string) => {
    setExpandedFlags((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  useEffect(() => {
    if (!companyId) return;
    api.getCompany(companyId).then(setCompany).catch((e) => setError(String(e)));
    api.getTray(companyId).then(setTray).catch((e) => setError(String(e)));
    api.listRedFlags(companyId).then(setFlags).catch(() => {});
  }, [companyId]);

  return (
    <div className="container">
      <div className="header">
        <div>
          <Link href="/" style={{ fontSize: 12 }}>← All companies</Link>
          <h1 style={{ marginTop: 6 }}>{company?.name ?? "Loading..."}</h1>
          {company && (
            <div className="header-chips">
              <span className="header-chip">{company.industry_tag || company.sector || "Secteur n/a"}</span>
              <span className="header-chip">{titleCase(company.stage)}</span>
              <span className="header-chip">{company.hq_country || "Pays n/a"}</span>
            </div>
          )}
        </div>
        <Link href={`/company/${companyId}/memo`}>
          <button className="btn">View investment memo →</button>
        </Link>
      </div>

      {error && <p style={{ color: "var(--sev-critical)" }}>{error}</p>}

      <div className="tray">
        {tray?.map((tile) => (
          <Link key={tile.module} href={`/company/${companyId}/module/${tile.module}`} style={{ textDecoration: "none", color: "inherit" }}>
            <div className="tile" style={{ borderTop: `3px solid var(${STATUS_COLOR_VAR[tile.status] || "--panel-border"})` }}>
              <div className="tile-title">{tile.label}</div>
              <div className="tile-headline">{tile.headline || "Not yet analyzed."}</div>
              {tile.red_flag_count > 0 && <div className="tile-flags">⚑ {tile.red_flag_count} red flag(s)</div>}
            </div>
          </Link>
        ))}
      </div>

      <div className="panel" style={{ marginTop: 24 }}>
        <h2>Red flags summary</h2>
        {flags === null && <p style={{ color: "var(--text-dim)" }}>Loading...</p>}
        {flags?.length === 0 && <p style={{ color: "var(--text-dim)" }}>No red flags identified yet.</p>}
        <div className="redflags-grid">
          {[...(flags || [])].sort((a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9)).map((f) => {
            const isExpanded = expandedFlags.has(f.id) || hoveredFlag === f.id;
            return (
              <div
                key={f.id}
                className={`redflag-card sev-${f.severity}${isExpanded ? " expanded" : ""}`}
                onClick={() => toggleFlag(f.id)}
                onMouseEnter={() => setHoveredFlag(f.id)}
                onMouseLeave={() => setHoveredFlag(null)}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="redflag-icon" style={{ color: `var(--sev-${f.severity})` }}>{SEV_ICON[f.severity] || "●"}</span>
                  <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: `var(--sev-${f.severity})` }}>
                    {SEV_LABEL[f.severity] || f.severity}
                  </span>
                </div>
                <div className="redflag-summary">
                  {CATEGORY_LABEL[f.category] || titleCase(f.category)}
                </div>
                <div className="redflag-detail">
                  <div className="redflag-text">{f.explanation}</div>
                  {f.potential_impact && <div className="redflag-meta"><b>Impact :</b> {f.potential_impact}</div>}
                  {f.resolving_information && <div className="redflag-meta"><b>Pour lever le doute :</b> {f.resolving_information}</div>}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
