"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, DashboardSummary } from "@/lib/api";
import { formatEurCompact, initials, gradientForId, stageLabel, timeAgo } from "@/lib/dashboardFormat";

const REC_BADGE_CLASS: Record<string, string> = {
  positive: "dash-rec-positive",
  watch: "dash-rec-watch",
  negative: "dash-rec-negative",
  neutral: "dash-rec-neutral",
};

const ACTIVITY_DOT_COLOR: Record<string, string> = {
  deck_upload: "var(--dash-neutral)",
  memo_generated: "var(--dash-accent)",
  red_flag: "var(--dash-negative)",
};

export default function HomePage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [health, setHealth] = useState<{ llm_mode: string; search_mode: string; pappers_mode: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getDashboardSummary().then(setSummary).catch((e) => setError(String(e)));
    api.health().then(setHealth).catch(() => {});
  }, []);

  const companies = summary?.companies ?? [];
  const totals = summary?.totals;

  // Recommendation breakdown for the donut - "no memo yet" is its own bucket,
  // never folded into a guessed recommendation.
  const donutBuckets = [
    { key: "positive", label: "Prioritaire", color: "var(--dash-positive)", count: companies.filter((c) => c.recommendation === "invest").length },
    { key: "watch", label: "Vigilance", color: "var(--dash-watch)", count: companies.filter((c) => c.recommendation === "watchlist").length },
    { key: "neutral", label: "Données manquantes", color: "var(--dash-neutral)", count: companies.filter((c) => c.recommendation === "need_more_data").length },
    { key: "negative", label: "Refus", color: "var(--dash-negative)", count: companies.filter((c) => c.recommendation === "pass").length },
    { key: "pending", label: "En cours d'analyse", color: "#c7cbd1", count: companies.filter((c) => c.recommendation === null).length },
  ].filter((b) => b.count > 0);
  const donutTotal = donutBuckets.reduce((s, b) => s + b.count, 0);
  let acc = 0;
  const donutGradient = donutBuckets
    .map((b) => {
      const start = donutTotal ? (acc / donutTotal) * 360 : 0;
      acc += b.count;
      const end = donutTotal ? (acc / donutTotal) * 360 : 0;
      return `${b.color} ${start}deg ${end}deg`;
    })
    .join(", ");

  const needsReviewCompanies = companies.filter((c) => c.needs_review);

  return (
    <div className="dash-page">
      <div className="dash-topnav">
        <div className="dash-topnav-left">
          <div className="dash-brand">
            <div className="dash-brand-mark" />
            <span className="dash-brand-name">Seed4Soft</span>
          </div>
          <div className="dash-tabs">
            <span className="dash-tab dash-tab-active">Dossiers</span>
            <Link href="/new" className="dash-tab">Nouveau dossier</Link>
          </div>
        </div>
        <div className="dash-avatar">NR</div>
      </div>

      {health && (health.llm_mode === "mock" || health.search_mode === "mock" || health.pappers_mode === "mock") && (
        <div className="dash-mock-banner">
          Mode mock actif — LLM={health.llm_mode}, Recherche={health.search_mode}, Pappers={health.pappers_mode}.
          Configurez les clés API dans backend/.env pour la recherche et la vérification en direct.
        </div>
      )}
      {error && <div className="dash-error-banner">{error} (le backend tourne-t-il à l'adresse NEXT_PUBLIC_API_URL ?)</div>}

      <div className="dash-body">
        <div className="dash-title-row">
          <h1>Sociétés suivies</h1>
          {summary && <span className="dash-updated dash-mono">{companies.length} dossier{companies.length !== 1 ? "s" : ""}</span>}
        </div>

        {summary && (
          <div className="dash-kpi-grid">
            <div className="dash-kpi">
              <div className="dash-kpi-head">
                <div className="dash-kpi-icon" style={{ background: "var(--dash-accent-soft)" }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><rect x="3" y="4" width="18" height="16" rx="2" stroke="var(--dash-accent)" strokeWidth="1.8" /><path d="M3 9H21" stroke="var(--dash-accent)" strokeWidth="1.8" /></svg>
                </div>
                <span className="dash-kpi-label">Dossiers actifs</span>
              </div>
              <div className="dash-kpi-value dash-mono">{totals!.active_count}</div>
            </div>
            <div className="dash-kpi">
              <div className="dash-kpi-head">
                <div className="dash-kpi-icon" style={{ background: "var(--dash-accent-soft)" }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 2V22M17 6H9.5A2.5 2.5 0 007 8.5V8.5A2.5 2.5 0 009.5 11H14.5A2.5 2.5 0 0117 13.5V13.5A2.5 2.5 0 0114.5 16H7" stroke="var(--dash-accent)" strokeWidth="1.8" strokeLinecap="round" /></svg>
                </div>
                <span className="dash-kpi-label">Montant total demandé</span>
              </div>
              <div className="dash-kpi-value dash-mono">{formatEurCompact(totals!.total_ask_amount)}</div>
              <div className="dash-kpi-sub">sur {totals!.companies_with_ask}/{totals!.active_count} dossiers avec un montant déclaré</div>
            </div>
            <div className="dash-kpi">
              <div className="dash-kpi-head">
                <div className="dash-kpi-icon" style={{ background: "var(--dash-positive-bg)" }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M5 13L10 18L19 6" stroke="var(--dash-positive)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
                </div>
                <span className="dash-kpi-label">Prioritaires</span>
              </div>
              <div className="dash-kpi-value dash-mono" style={{ color: "var(--dash-positive)" }}>{totals!.prioritized_count}</div>
            </div>
            <div className="dash-kpi">
              <div className="dash-kpi-head">
                <div className="dash-kpi-icon" style={{ background: "var(--dash-watch-bg)" }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 9V13M12 17H12.01M10.29 3.86L1.82 18A2 2 0 003.54 21H20.46A2 2 0 0022.18 18L13.71 3.86A2 2 0 0010.29 3.86Z" stroke="var(--dash-watch)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
                </div>
                <span className="dash-kpi-label">À réviser</span>
              </div>
              <div className="dash-kpi-value dash-mono" style={{ color: "var(--dash-watch)" }}>{totals!.needs_review_count}</div>
            </div>
          </div>
        )}

        {needsReviewCompanies.length > 0 && (
          <div className="dash-alert">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M12 9V13M12 17H12.01M10.29 3.86L1.82 18A2 2 0 003.54 21H20.46A2 2 0 0022.18 18L13.71 3.86A2 2 0 0010.29 3.86Z" stroke="var(--dash-watch)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
            <span className="dash-alert-text">
              <strong>{needsReviewCompanies.length} dossier{needsReviewCompanies.length > 1 ? "s" : ""} nécessite{needsReviewCompanies.length > 1 ? "nt" : ""} une revue</strong> — {needsReviewCompanies.map((c) => c.name).join(", ")}.
            </span>
          </div>
        )}

        {!summary && !error && <div className="dash-empty">Chargement…</div>}
        {summary && companies.length === 0 && (
          <div className="dash-empty">Aucun dossier pour l'instant — <Link href="/new">déposer un pitch deck</Link>.</div>
        )}

        {summary && companies.length > 0 && (
          <div className="dash-main-grid">
            <div className="dash-table-card">
              <div className="dash-row-grid dash-table-head">
                <div>Société</div>
                <div>Secteur</div>
                <div>Stade</div>
                <div>Recommandation</div>
                <div style={{ textAlign: "right" }}>Montant</div>
              </div>
              {companies.map((c) => {
                const [gradA, gradB] = gradientForId(c.id);
                return (
                  <Link key={c.id} href={`/company/${c.id}`} className="dash-row dash-row-grid">
                    <div className="dash-row-company">
                      <div className="dash-row-avatar" style={{ background: `linear-gradient(135deg, ${gradA}, ${gradB})` }}>
                        {initials(c.name)}
                      </div>
                      <div>
                        <div className="dash-row-name">{c.name}</div>
                        <div className="dash-row-model">{c.business_model.toUpperCase()}{c.red_flag_count > 0 ? ` · ${c.red_flag_count} red flag${c.red_flag_count > 1 ? "s" : ""}` : ""}</div>
                      </div>
                    </div>
                    <div className="dash-row-sector">{c.sector || c.industry_tag || "—"}</div>
                    <div className="dash-row-stage">{stageLabel(c.stage)}</div>
                    <div>
                      <span className={`dash-rec-badge ${c.recommendation ? REC_BADGE_CLASS[c.recommendation_color || "neutral"] : "dash-rec-pending"}`}>
                        {c.recommendation_label || "Analyse en cours"}
                      </span>
                    </div>
                    <div className="dash-row-ask dash-mono">{c.ask_amount ? formatEurCompact(c.ask_amount) : "—"}</div>
                  </Link>
                );
              })}
            </div>

            <div>
              <div className="dash-side-card">
                <div className="dash-side-title">Répartition par statut</div>
                {donutTotal > 0 ? (
                  <div className="dash-donut-row">
                    <div style={{ width: 96, height: 96, borderRadius: 999, background: `conic-gradient(${donutGradient})`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                      <div style={{ width: 60, height: 60, borderRadius: 999, background: "#fff", display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column" }}>
                        <span className="dash-mono" style={{ fontSize: 16, fontWeight: 700 }}>{donutTotal}</span>
                        <span style={{ fontSize: 9, color: "var(--dash-text-dim)" }}>dossiers</span>
                      </div>
                    </div>
                    <div className="dash-donut-legend">
                      {donutBuckets.map((b) => (
                        <div key={b.key} className="dash-legend-item">
                          <span className="dash-legend-dot" style={{ background: b.color }} />
                          <span>{b.label}</span>
                          <span className="dash-legend-count dash-mono">{b.count}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div style={{ fontSize: 12.5, color: "var(--dash-text-dim)" }}>Pas encore de dossier.</div>
                )}
              </div>

              <div className="dash-side-card">
                <div className="dash-side-title">Activité récente</div>
                {(summary.recent_activity.length === 0) && <div style={{ fontSize: 12.5, color: "var(--dash-text-dim)" }}>Aucune activité récente.</div>}
                {summary.recent_activity.map((a, i) => (
                  <div key={i} className="dash-activity-item">
                    <span className="dash-activity-dot" style={{ background: ACTIVITY_DOT_COLOR[a.type] }} />
                    <div>
                      <div className="dash-activity-text">{a.text}</div>
                      <div className="dash-activity-time dash-mono">{timeAgo(a.at)}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
