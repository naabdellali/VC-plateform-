"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, ModuleResult, Evidence } from "@/lib/api";
import { StatusBadge } from "@/components/Badges";
import EvidenceList from "@/components/EvidenceList";
import ReasoningTraceView from "@/components/ReasoningTrace";
import MarketRecalculateForm from "@/components/MarketRecalculateForm";
import TractionForensicsForms from "@/components/TractionForensicsForms";

const MODULE_LABELS: Record<string, string> = {
  market: "Market",
  competition: "Competition & Moat",
  traction: "Traction & Business Model",
  founders: "Team & Background",
};

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

      {result && result !== "not_found" && (
        <div className="panel">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <h2>Conclusion</h2>
            <StatusBadge status={result.status} />
          </div>
          <p>{result.headline}</p>
          {(result.deck_value || result.platform_value) && (
            <div style={{ display: "flex", gap: 24, marginTop: 8, fontSize: 13 }}>
              {result.deck_value && (
                <div>
                  <div style={{ color: "var(--text-dim)", fontSize: 11 }}>DECK CLAIMS</div>
                  <div style={{ fontWeight: 600 }}>{result.deck_value}</div>
                </div>
              )}
              {result.platform_value && (
                <div>
                  <div style={{ color: "var(--text-dim)", fontSize: 11 }}>PLATFORM ESTIMATE</div>
                  <div style={{ fontWeight: 600, color: "var(--accent)" }}>{result.platform_value}</div>
                </div>
              )}
            </div>
          )}
          {result.discrepancy_explanation && (
            <p style={{ marginTop: 10, fontSize: 13, color: "var(--text-dim)" }}>{result.discrepancy_explanation}</p>
          )}
          <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 8 }}>
            Produced in {result.llm_mode === "mock" ? "MOCK MODE (no live LLM configured)" : "live mode"}.
          </div>
        </div>
      )}

      {module === "market" && (
        <MarketRecalculateForm companyId={companyId} onDone={refresh} />
      )}
      {module === "traction" && (
        <TractionForensicsForms companyId={companyId} onDone={refresh} />
      )}

      {result && result !== "not_found" && (
        <div className="panel">
          <h2>Reasoning trace</h2>
          <p style={{ fontSize: 12, color: "var(--text-dim)", marginTop: -8 }}>
            extract → identify unknowns → research → verify → calculate → benchmark → reality check → contradictions → assumptions
          </p>
          <ReasoningTraceView result={result} />
        </div>
      )}

      <div className="panel">
        <h2>Evidence trail</h2>
        <p style={{ fontSize: 12, color: "var(--text-dim)", marginTop: -8 }}>
          Every conclusion above traces back to one of these rows — claim, origin, confidence and source.
        </p>
        <EvidenceList evidence={evidence} />
      </div>
    </div>
  );
}
