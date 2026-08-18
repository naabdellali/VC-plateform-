"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, Company, TrayTile, RedFlag } from "@/lib/api";
import { StatusBadge, SeverityBadge } from "@/components/Badges";

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
            <div className="tile">
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
        {flags?.map((f) => (
          <div key={f.id} className="evidence-row">
            <div className="claim">
              <SeverityBadge severity={f.severity} /> <span style={{ marginLeft: 8 }}>{f.explanation}</span>
            </div>
            {f.potential_impact && <div className="meta">Impact: {f.potential_impact}</div>}
            {f.resolving_information && <div className="meta">Resolve by: {f.resolving_information}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
