"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export default function TractionForensicsForms({ companyId, onDone }: { companyId: string; onDone: () => void }) {
  const [series, setSeries] = useState("70000, 95000, 68000, 100000, 65000, 110000");
  const [seriesOut, setSeriesOut] = useState<any>(null);
  const [seriesBusy, setSeriesBusy] = useState(false);
  const [seriesError, setSeriesError] = useState<string | null>(null);

  const [cac, setCac] = useState("5000");
  const [ltv, setLtv] = useState("150000");
  const [grossMargin, setGrossMargin] = useState("0.8");
  const [arpaMonthly, setArpaMonthly] = useState("500");
  const [cacOut, setCacOut] = useState<any>(null);
  const [cacBusy, setCacBusy] = useState(false);
  const [cacError, setCacError] = useState<string | null>(null);

  async function submitSeries(e: React.FormEvent) {
    e.preventDefault();
    setSeriesBusy(true);
    setSeriesError(null);
    try {
      const values = series.split(",").map((s) => Number(s.trim())).filter((n) => !Number.isNaN(n));
      const out = await api.submitMrrSeries(companyId, values);
      setSeriesOut(out);
      onDone();
    } catch (err) {
      setSeriesError(err instanceof Error ? err.message : String(err));
    } finally {
      setSeriesBusy(false);
    }
  }

  async function submitCacLtv(e: React.FormEvent) {
    e.preventDefault();
    setCacBusy(true);
    setCacError(null);
    try {
      const out = await api.submitCacLtvCheck(companyId, {
        cac: Number(cac),
        reported_ltv: Number(ltv),
        gross_margin: Number(grossMargin),
        arpa_monthly: Number(arpaMonthly),
      });
      setCacOut(out);
      onDone();
    } catch (err) {
      setCacError(err instanceof Error ? err.message : String(err));
    } finally {
      setCacBusy(false);
    }
  }

  return (
    <>
      <form onSubmit={submitSeries} style={{ marginBottom: 22 }}>
        <h3 style={{ margin: "0 0 4px", textTransform: "none", fontSize: 14, color: "var(--text)", letterSpacing: 0 }}>MRR quality / volatility check</h3>
        <p style={{ fontSize: 12.5, color: "var(--text-dim)", marginTop: 0 }}>
          Read the monthly MRR figures off the deck's chart (not parsed automatically) and paste them in order.
          "Up-then-down-then-up" patterns often mean one-off services revenue is mixed into a claimed recurring number.
        </p>
        <label>Monthly MRR values, EUR, comma-separated, oldest first</label>
        <input value={series} onChange={(e) => setSeries(e.target.value)} />
        <div style={{ marginTop: 14 }}>
          <button className="btn" type="submit" disabled={seriesBusy}>{seriesBusy ? "Checking..." : "Run volatility check"}</button>
        </div>
        {seriesError && <p style={{ color: "var(--sev-critical)", fontSize: 12.5, marginTop: 10 }}>{seriesError}</p>}
        {seriesOut && (
          <div style={{ marginTop: 10, fontSize: 12.5 }}>
            <div>CV = {seriesOut.coefficient_of_variation}, {seriesOut.declining_months}/{seriesOut.total_months - 1} declining months</div>
            {seriesOut.flags.map((f: string, i: number) => (
              <div key={i} style={{ color: "var(--conf-medium)", marginTop: 4 }}>{f}</div>
            ))}
          </div>
        )}
      </form>

      <form onSubmit={submitCacLtv}>
        <h3 style={{ margin: "0 0 4px", textTransform: "none", fontSize: 14, color: "var(--text)", letterSpacing: 0 }}>CAC / LTV internal consistency check</h3>
        <p style={{ fontSize: 12.5, color: "var(--text-dim)", marginTop: 0 }}>
          Reverse-solves the monthly churn implied by the reported LTV given ARPA and gross margin — flags LTV claims
          that are only possible with implausibly low churn.
        </p>
        <div style={{ display: "flex", gap: 12 }}>
          <div style={{ flex: 1 }}>
            <label>CAC (EUR)</label>
            <input value={cac} onChange={(e) => setCac(e.target.value)} type="number" />
          </div>
          <div style={{ flex: 1 }}>
            <label>Reported LTV (EUR)</label>
            <input value={ltv} onChange={(e) => setLtv(e.target.value)} type="number" />
          </div>
        </div>
        <div style={{ display: "flex", gap: 12 }}>
          <div style={{ flex: 1 }}>
            <label>Gross margin (0–1)</label>
            <input value={grossMargin} onChange={(e) => setGrossMargin(e.target.value)} type="number" step="0.01" />
          </div>
          <div style={{ flex: 1 }}>
            <label>ARPA / month (EUR)</label>
            <input value={arpaMonthly} onChange={(e) => setArpaMonthly(e.target.value)} type="number" />
          </div>
        </div>
        <div style={{ marginTop: 14 }}>
          <button className="btn" type="submit" disabled={cacBusy}>{cacBusy ? "Checking..." : "Run consistency check"}</button>
        </div>
        {cacError && <p style={{ color: "var(--sev-critical)", fontSize: 12.5, marginTop: 10 }}>{cacError}</p>}
        {cacOut && (
          <p style={{ marginTop: 10, fontSize: 12.5, color: cacOut.plausible ? "var(--status-complete)" : "var(--sev-major)" }}>
            {cacOut.explanation}
          </p>
        )}
      </form>
    </>
  );
}
