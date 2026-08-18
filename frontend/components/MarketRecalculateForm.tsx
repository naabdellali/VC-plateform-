"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export default function MarketRecalculateForm({ companyId, onDone }: { companyId: string; onDone: () => void }) {
  const [methodology, setMethodology] = useState<"bottom_up" | "top_down">("bottom_up");
  const [numCustomers, setNumCustomers] = useState("50000");
  const [avgSpend, setAvgSpend] = useState("2000");
  const [penetration, setPenetration] = useState("0.2");
  const [industrySize, setIndustrySize] = useState("10000000000");
  const [segmentPct, setSegmentPct] = useState("0.1");
  const [addressablePct, setAddressablePct] = useState("0.3");
  const [assumptions, setAssumptions] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [out, setOut] = useState<any>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const inputs: Record<string, number> =
        methodology === "bottom_up"
          ? {
              num_potential_customers: Number(numCustomers),
              avg_annual_spend_eur: Number(avgSpend),
              realistic_penetration: Number(penetration),
            }
          : {
              industry_size_eur: Number(industrySize),
              relevant_segment_pct: Number(segmentPct),
              addressable_pct: Number(addressablePct),
            };
      const result = await api.recalculateMarket(companyId, {
        methodology,
        inputs,
        assumptions: assumptions.split("\n").map((s) => s.trim()).filter(Boolean),
      });
      setOut(result);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <p style={{ fontSize: 12.5, color: "var(--text-dim)", marginTop: 0 }}>
        We won't guess a penetration or segment percentage on our own — that's exactly the kind of number a model
        will happily fabricate. Give us the inputs you'd defend to an IC, and we'll compute the estimate and record
        your assumptions alongside it.
      </p>
      <label>Methodology</label>
      <select value={methodology} onChange={(e) => setMethodology(e.target.value as any)}>
        <option value="bottom_up">Bottom-up (customers × spend × penetration)</option>
        <option value="top_down">Top-down (industry size × segment % × addressable %)</option>
      </select>

      {methodology === "bottom_up" ? (
        <>
          <label>Number of potential customers</label>
          <input value={numCustomers} onChange={(e) => setNumCustomers(e.target.value)} type="number" />
          <label>Average annual spend per customer (EUR)</label>
          <input value={avgSpend} onChange={(e) => setAvgSpend(e.target.value)} type="number" />
          <label>Realistic penetration (0–1)</label>
          <input value={penetration} onChange={(e) => setPenetration(e.target.value)} type="number" step="0.01" />
        </>
      ) : (
        <>
          <label>Industry size (EUR)</label>
          <input value={industrySize} onChange={(e) => setIndustrySize(e.target.value)} type="number" />
          <label>Relevant segment (0–1)</label>
          <input value={segmentPct} onChange={(e) => setSegmentPct(e.target.value)} type="number" step="0.01" />
          <label>Realistically addressable (0–1)</label>
          <input value={addressablePct} onChange={(e) => setAddressablePct(e.target.value)} type="number" step="0.01" />
        </>
      )}

      <label>Assumptions (one per line — required for auditability)</label>
      <textarea value={assumptions} onChange={(e) => setAssumptions(e.target.value)} rows={3} placeholder="e.g. 20% penetration based on comparable vertical SaaS adoption curves" />

      <div style={{ marginTop: 14 }}>
        <button className="btn" type="submit" disabled={busy}>{busy ? "Calculating..." : "Recalculate"}</button>
      </div>
      {error && <p style={{ color: "var(--sev-critical)", fontSize: 12.5, marginTop: 10 }}>{error}</p>}
      {out && (
        <p style={{ color: "var(--accent)", fontSize: 12.5, marginTop: 10 }}>
          Platform estimate: {out.estimate.value.toLocaleString()} EUR. {out.comparison?.verdict}
        </p>
      )}
    </form>
  );
}
