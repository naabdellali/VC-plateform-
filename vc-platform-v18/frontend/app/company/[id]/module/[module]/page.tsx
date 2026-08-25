"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, ModuleResult, Evidence, RedFlag } from "@/lib/api";
import MarketRecalculateForm from "@/components/MarketRecalculateForm";
import TractionForensicsForms from "@/components/TractionForensicsForms";
import CompetitorGrid from "@/components/CompetitorGrid";
import TamSamSomView, { TamSamSom } from "@/components/TamSamSomView";
import CompetitiveLandscapeView, { CompetitiveLandscape } from "@/components/CompetitiveLandscapeView";
import MoatView, { Moat } from "@/components/MoatView";
import TechnologyView, { TechnologyData } from "@/components/TechnologyView";
import MarketDynamicsView, { MarketDynamicsData } from "@/components/MarketDynamicsView";
import QuestionsToAsk from "@/components/QuestionsToAsk";

const MODULE_LABELS: Record<string, string> = {
  market: "Market Sizing",
  market_dynamics: "Market Dynamics",
  competition: "Competitive Landscape",
  moat: "Moat",
  technology: "Technology",
  traction: "Traction",
  business_model: "Business Model",
  founders: "Team & Background",
};

type BusinessModelData = { label: string; pricing_model: string | null; target_segment: string | null; explanation: string | null };
type Founder = { name: string; title: string | null; status: "positive" | "flag" | "unverified"; status_label: string; detail: string | null };
type TractionClaim = { claim: string; value: string | null };
type TractionData = { today: TractionClaim[]; tomorrow: TractionClaim[] };

function formatMoneyMaybe(raw: string | null): string | null {
  if (!raw) return null;
  const n = Number(raw);
  if (!Number.isFinite(n)) return raw;
  return `${n.toLocaleString(undefined, { maximumFractionDigits: 0 })} EUR`;
}

export default function ModuleDetailPage() {
  const params = useParams<{ id: string; module: string }>();
  const { id: companyId, module } = params;

  const [result, setResult] = useState<ModuleResult | null | "not_found">(null);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [redFlags, setRedFlags] = useState<RedFlag[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    if (!companyId || !module) return;
    api.getModule(companyId, module).then(setResult).catch(() => setResult("not_found"));
    api.listEvidence(companyId, module).then(setEvidence).catch((e) => setError(String(e)));
    api.listRedFlags(companyId).then(setRedFlags).catch(() => {});
  }, [companyId, module]);

  useEffect(() => refresh(), [refresh]);

  const competitors = useMemo(() => {
    if (module !== "competition") return [];
    const row = evidence.find((e) => e.value_type === "competitor_list_json");
    if (!row || !row.value) return [];
    try {
      return JSON.parse(row.value);
    } catch {
      return [];
    }
  }, [evidence, module]);

  const hasResult = result && result !== "not_found";
  const isInsufficient = hasResult && (result as ModuleResult).status === "insufficient_evidence";

  const tamSamSom = useMemo<TamSamSom | null>(() => {
    if (module !== "market" || !hasResult) return null;
    const raw = (result as ModuleResult).platform_value;
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw);
      if (parsed && parsed.tam && parsed.sam && parsed.som) return parsed as TamSamSom;
    } catch {
      /* not JSON - fall through to the generic display below */
    }
    return null;
  }, [module, hasResult, result]);

  const landscape = useMemo<CompetitiveLandscape | null>(() => {
    if (module !== "competition" || !hasResult) return null;
    const raw = (result as ModuleResult).platform_value;
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw);
      if (parsed && parsed.matrix) return parsed as CompetitiveLandscape;
    } catch {
      /* not JSON */
    }
    return null;
  }, [module, hasResult, result]);

  const marketDynamics = useMemo<MarketDynamicsData | null>(() => {
    if (module !== "market_dynamics" || !hasResult) return null;
    const raw = (result as ModuleResult).platform_value;
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw);
      if (parsed && (parsed.trend || parsed.consolidation)) return parsed as MarketDynamicsData;
    } catch {
      /* not JSON */
    }
    return null;
  }, [module, hasResult, result]);

  const moat = useMemo<Moat | null>(() => {
    if (module !== "moat" || !hasResult) return null;
    const raw = (result as ModuleResult).platform_value;
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw);
      if (parsed && parsed.grade) return parsed as Moat;
    } catch {
      /* not JSON */
    }
    return null;
  }, [module, hasResult, result]);

  const technology = useMemo<TechnologyData | null>(() => {
    if (module !== "technology" || !hasResult) return null;
    const raw = (result as ModuleResult).platform_value;
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw);
      if (parsed && parsed.dependencies) return parsed as TechnologyData;
    } catch {
      /* not JSON */
    }
    return null;
  }, [module, hasResult, result]);

  const businessModel = useMemo<BusinessModelData | null>(() => {
    if (module !== "business_model" || !hasResult) return null;
    const raw = (result as ModuleResult).platform_value;
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw);
      if (parsed && parsed.label) return parsed as BusinessModelData;
    } catch {
      /* not JSON */
    }
    return null;
  }, [module, hasResult, result]);

  const founders = useMemo<Founder[] | null>(() => {
    if (module !== "founders" || !hasResult) return null;
    const raw = (result as ModuleResult).platform_value;
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw);
      if (parsed && Array.isArray(parsed.founders) && parsed.founders.length > 0) return parsed.founders as Founder[];
    } catch {
      /* not JSON */
    }
    return null;
  }, [module, hasResult, result]);

  const [bmExplanationOpen, setBmExplanationOpen] = useState(false);
  const [expandedFounders, setExpandedFounders] = useState<Set<number>>(new Set());
  const toggleFounder = (i: number) => {
    setExpandedFounders((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  };

  const traction = useMemo<TractionData | null>(() => {
    if (module !== "traction" || !hasResult) return null;
    const raw = (result as ModuleResult).platform_value;
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw);
      if (parsed && (Array.isArray(parsed.today) || Array.isArray(parsed.tomorrow))) return parsed as TractionData;
    } catch {
      /* not JSON - e.g. a recalculated single MRR figure; falls through to platformDisplay */
    }
    return null;
  }, [module, hasResult, result]);

  const platformDisplay = hasResult && !tamSamSom && !landscape && !moat && !technology && !businessModel && !founders && !traction && !marketDynamics ? formatMoneyMaybe((result as ModuleResult).platform_value) : null;
  const deckDisplay = hasResult ? formatMoneyMaybe((result as ModuleResult).deck_value) : null;

  return (
    <div className="container">
      <div className="header">
        <div>
          <Link href={`/company/${companyId}`} style={{ fontSize: 12 }}>← Back to tray</Link>
          <h1 style={{ marginTop: 6 }}>{MODULE_LABELS[module] || module}</h1>
        </div>
      </div>

      {error && <p style={{ color: "var(--sev-critical)" }}>{error}</p>}

      {result === "not_found" && <p style={{ color: "var(--text-dim)" }}>This module has not been analyzed yet.</p>}

      {hasResult && (
        <div className="hero">
          <div className="hero-label">
            {module === "competition" || module === "moat"
              ? "What we found independently"
              : module === "business_model"
              ? "As entered on the workspace"
              : "Our independent conclusion"}
          </div>

          {module === "market" && tamSamSom ? (
            <TamSamSomView data={tamSamSom} />
          ) : module === "market_dynamics" && marketDynamics ? (
            <MarketDynamicsView data={marketDynamics} />
          ) : module === "competition" && landscape ? (
            <CompetitiveLandscapeView data={landscape} />
          ) : module === "moat" && moat ? (
            <MoatView data={moat} />
          ) : module === "technology" && technology ? (
            <TechnologyView data={technology} />
          ) : module === "business_model" && businessModel ? (
            <div className="business-model-block">
              {businessModel.pricing_model && (
                <div className="bm-fact">
                  <div className="bm-fact-label">Pricing</div>
                  <div className="bm-fact-value">{businessModel.pricing_model}</div>
                </div>
              )}
              {businessModel.target_segment && (
                <div className="bm-fact">
                  <div className="bm-fact-label">Cible</div>
                  <div className="bm-fact-value">{businessModel.target_segment}</div>
                </div>
              )}
              {!businessModel.pricing_model && !businessModel.target_segment && (
                <p className="hero-empty">{(result as ModuleResult).headline}</p>
              )}
              {businessModel.explanation && (
                <div className={`bm-explanation${bmExplanationOpen ? " expanded" : ""}`} onClick={() => setBmExplanationOpen((v) => !v)}>
                  <div className="bm-explanation-toggle">
                    {bmExplanationOpen ? "Masquer le détail ▲" : "Comment ça marche concrètement ▼"}
                  </div>
                  {bmExplanationOpen && <p className="bm-explanation-text">{businessModel.explanation}</p>}
                </div>
              )}
            </div>
          ) : module === "founders" && founders ? (
            <div className="founder-list">
              {founders.map((f, i) => {
                const isExpanded = expandedFounders.has(i);
                return (
                  <div
                    key={i}
                    className={`founder-row status-${f.status}${isExpanded ? " expanded" : ""}`}
                    onClick={() => f.detail && toggleFounder(i)}
                  >
                    <div className="founder-name">{f.name}{f.title && <span className="founder-title"> — {f.title}</span>}</div>
                    <div className={`founder-status status-${f.status}`}>{f.status_label}</div>
                    {f.detail && <div className="founder-detail">{f.detail}</div>}
                  </div>
                );
              })}
            </div>
          ) : module === "traction" && traction && (traction.today.length > 0 || traction.tomorrow.length > 0) ? (
            <div className="traction-split">
              <div className="traction-col">
                <div className="traction-col-heading">Aujourd'hui</div>
                {traction.today.length > 0 ? (
                  traction.today.map((c, i) => (
                    <div key={i} className="traction-item">{c.value || c.claim}</div>
                  ))
                ) : (
                  <div className="traction-item-empty">Rien de vérifiable pour l'instant.</div>
                )}
              </div>
              <div className="traction-col">
                <div className="traction-col-heading">Demain</div>
                {traction.tomorrow.length > 0 ? (
                  traction.tomorrow.map((c, i) => (
                    <div key={i} className="traction-item projection">{c.value || c.claim}</div>
                  ))
                ) : (
                  <div className="traction-item-empty">Aucune projection communiquée.</div>
                )}
              </div>
            </div>
          ) : module === "competition" && competitors.length > 0 ? (
            <>
              <CompetitorGrid competitors={competitors} />
              <p className="hero-note">{(result as ModuleResult).headline}</p>
            </>
          ) : isInsufficient ? (
            <p className="hero-empty">
              Not enough information to conclude yet. {(result as ModuleResult).headline}
              {module === "market" && " Use “Refine this estimate” below to calculate it with real inputs."}
            </p>
          ) : platformDisplay ? (
            <>
              <div className="hero-value">{platformDisplay}</div>
              <p className="hero-note">{(result as ModuleResult).discrepancy_explanation || (result as ModuleResult).headline}</p>
            </>
          ) : (
            <p className="hero-empty">{(result as ModuleResult).headline}</p>
          )}

          {module !== "market" && !landscape && (deckDisplay || (module === "competition" && (result as ModuleResult).deck_value)) && (
            <div className="hero-secondary">
              <div>
                <div className="item-label">What the deck says</div>
                <div className="item-value">
                  {module === "competition" ? (result as ModuleResult).deck_value || "Nothing named" : deckDisplay}
                </div>
              </div>
              {platformDisplay && (
                <div>
                  <div className="item-label">Our estimate</div>
                  <div className="item-value" style={{ color: "var(--accent-strong)" }}>{platformDisplay}</div>
                </div>
              )}
            </div>
          )}

          <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 14 }}>
            {module === "business_model"
              ? "Champ du formulaire de workspace — non recherché indépendamment."
              : (result as ModuleResult).llm_mode === "mock"
              ? "Produced in mock mode (no live LLM configured)."
              : "Produced in live mode."}
          </div>

          <QuestionsToAsk moduleKey={module} redFlags={redFlags} extraQuestions={module === "technology" ? technology?.questions_to_ask : undefined} />
        </div>
      )}

      {module === "market" && (
        <details className="collapsible">
          <summary>
            Refine this estimate
            <span className="summary-sub">optional — supply real inputs to calculate a defensible TAM</span>
          </summary>
          <div className="collapsible-body">
            <MarketRecalculateForm companyId={companyId} onDone={refresh} />
          </div>
        </details>
      )}
      {module === "traction" && (
        <details className="collapsible">
          <summary>
            Add real traction figures
            <span className="summary-sub">optional — run MRR quality and CAC/LTV checks</span>
          </summary>
          <div className="collapsible-body">
            <TractionForensicsForms companyId={companyId} onDone={refresh} />
          </div>
        </details>
      )}

      {module === "market" && hasResult && tamSamSom && (
        <div className="panel">
          <h2>Comparison with the deck</h2>
          {deckDisplay ? (
            <p style={{ fontSize: 13.5, lineHeight: 1.6 }}>
              The deck claims <b>{deckDisplay}</b>. {(result as ModuleResult).discrepancy_explanation}
            </p>
          ) : (
            <p style={{ fontSize: 13.5, color: "var(--text-dim)", lineHeight: 1.6 }}>
              The deck did not provide its own market-size figure — nothing to compare our estimate against.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
