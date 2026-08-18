"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, Company, TrayTile, RedFlag } from "@/lib/api";
import { StatusBadge } from "@/components/Badges";

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
  critical: "Critical",
  major: "Major",
  watch: "Watch",
};

export default function CompanyTrayPage() {
  const params = useParams<{ id: string }>();
  const companyId = params.id;

  const [company, setCompany] = useState<Company | null>(null);
  const [tray, setTray] = useState<TrayTile[] | null>(null);
  const [flags, setFlags] = useState<RedFlag[] | null>(null);
  const [error, setError] = useState<string | null>(null);

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
            <div className="sub">
              {company.sector || "sector n/a"} · {company.stage} · {company.business_model} · {company.hq_country || "n/a"}
            </div>
          )}
        </div>
        <Link href={`/company/${companyId}/memo`}>
          <button className="btn">View investment memo →</button>
        </Link>
      </div>

      {error && <p style={{ color: "var(--sev-critical)" }}>{error}</p>}

      <h3 style={{ color: "var(--text-dim)", fontSize: 12.5, textTransform: "uppercase", letterSpacing: "0.05em" }}>
        The tray — click a module to drill into conclusion → reasoning → calculation → evidence → source
      </h3>
      <div className="tray">
        {tray?.map((tile) => (
          <Link key={tile.module} href={`/company/${companyId}/module/${tile.module}`} style={{ textDecoration: "none", color: "inherit" }}>
            <div className="tile" style={{ borderTop: `3px solid var(${STATUS_COLOR_VAR[tile.status] || "--panel-border"})` }}>
              <div className="tile-title">{tile.label}</div>
              <StatusBadge status={tile.status} />
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
          {flags?.map((f) => (
            <div key={f.id} className={`redflag-card sev-${f.severity}`}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span className="redflag-icon" style={{ color: `var(--sev-${f.severity})` }}>{SEV_ICON[f.severity] || "●"}</span>
                <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: `var(--sev-${f.severity})` }}>
                  {SEV_LABEL[f.severity] || f.severity}
                </span>
              </div>
              <div className="redflag-text">{f.explanation}</div>
              {f.potential_impact && <div className="redflag-meta"><b>Impact:</b> {f.potential_impact}</div>}
              {f.resolving_information && <div className="redflag-meta"><b>Resolve by:</b> {f.resolving_information}</div>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
