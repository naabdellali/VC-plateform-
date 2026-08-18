"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, ModuleResult, Evidence } from "@/lib/api";
import { StatusBadge } from "@/components/Badges";
import EvidenceList from "@/components/EvidenceList";
import ReasoningTraceView from "@/components/ReasoningTrace";
import MarketRecalculateForm from "@/components/MarketRecalculateForm";
import TractionForensicsForms from "@/components/TractionForensicsForms";
import CompetitorGrid from "@/components/CompetitorGrid";

const MODULE_LABELS: Record<string, string> = {
  market: "Market",
  competition: "Competition & Moat",
  traction: "Traction & Business Model",
  founders: "Team & Background",
};

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
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    if (!companyId || !module) return;
    api.getModule(companyId, module).then(setResult).catch(() => setResult("not_found"));
    api.listEvidence(companyId, module).then(setEvidence).catch((e) => setError(String(e)));
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
  const platformDisplay = hasResult ? formatMoneyMaybe((result as ModuleResult).platform_value) : null;
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
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
            <div className="hero-label">
              {module === "competition" ? "What we found independently" : "Our independent conclusion"}
            </div>
            <StatusBadge status={(result as ModuleResult).status} />
          </div>

          {module === "competition" && competitors.length > 0 ? (
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

          {(deckDisplay || (module === "competition" && (result as ModuleResult).deck_value)) && (
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
            {(result as ModuleResult).llm_mode === "mock" ? "Produced in mock mode (no live LLM configured)." : "Produced in live mode."}
          </div>
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

      {hasResult && (
        <details className="collapsible">
          <summary>
            See our full analysis
            <span className="summary-sub">extract → research → verify → calculate → benchmark → reason</span>
          </summary>
          <div className="collapsible-body">
            <ReasoningTraceView result={result as ModuleResult} />
          </div>
        </details>
      )}

      <details className="collapsible">
        <summary>
          Sources
          <span className="summary-sub">{evidence.length} row(s) — every figure above traces back to one of these</span>
        </summary>
        <div className="collapsible-body">
          <EvidenceList evidence={evidence} />
        </div>
      </details>
    </div>
  );
}
