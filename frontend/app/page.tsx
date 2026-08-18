"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Company } from "@/lib/api";
import NewCompanyForm from "@/components/NewCompanyForm";

export default function HomePage() {
  const [companies, setCompanies] = useState<Company[] | null>(null);
  const [health, setHealth] = useState<{ llm_mode: string; search_mode: string; pappers_mode: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listCompanies().then(setCompanies).catch((e) => setError(String(e)));
    api.health().then(setHealth).catch(() => {});
  }, []);

  return (
    <div className="container">
      <div className="header">
        <div>
          <h1>VC Investment Intelligence Platform</h1>
          <div className="sub">Extract → Research → Verify → Challenge → Benchmark → Reason → Conclude</div>
        </div>
      </div>

      {health && (health.llm_mode === "mock" || health.search_mode === "mock" || health.pappers_mode === "mock") && (
        <div className="mock-banner">
          Running with mock providers: LLM={health.llm_mode}, Search={health.search_mode}, Pappers={health.pappers_mode}.
          Configure API keys in backend/.env for live research and verification - see README.
        </div>
      )}

      <NewCompanyForm />

      <div className="panel">
        <h2>Companies</h2>
        {error && <p style={{ color: "var(--sev-critical)" }}>{error} (is the backend running at NEXT_PUBLIC_API_URL?)</p>}
        {companies === null && !error && <p style={{ color: "var(--text-dim)" }}>Loading...</p>}
        {companies?.length === 0 && <p style={{ color: "var(--text-dim)" }}>No companies analyzed yet - upload a pitch deck above.</p>}
        {companies?.map((c) => (
          <Link key={c.id} href={`/company/${c.id}`} style={{ textDecoration: "none" }}>
            <div className="company-list-item">
              <div>
                <div style={{ fontWeight: 600, color: "var(--text)" }}>{c.name}</div>
                <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
                  {c.sector || "sector n/a"} · {c.stage} · {c.business_model}
                </div>
              </div>
              <span style={{ color: "var(--accent)" }}>Open →</span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
