type Tier = {
  estimate?: number;
  estimate_low?: number;
  estimate_high?: number;
  pct_of_tam?: number | null;
  capture_rate_low_pct?: number;
  capture_rate_high_pct?: number;
  reasoning?: string;
};

type Footnote = { n: number; detail: string; source_url: string | null; source_name: string | null };

export type TamSamSom = {
  currency: string;
  tam: Tier;
  sam: Tier;
  som: Tier;
  footnotes: Footnote[];
};

function fmt(n: number | undefined | null, symbol: string): string {
  if (n === undefined || n === null || !Number.isFinite(n)) return "?";
  const abs = Math.abs(n);
  if (abs >= 1e9) return `${symbol}${(n / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${symbol}${(n / 1e6).toFixed(0)}M`;
  if (abs >= 1e3) return `${symbol}${(n / 1e3).toFixed(0)}K`;
  return `${symbol}${n.toLocaleString()}`;
}

function rangeStr(tier: Tier, symbol: string): string {
  if (tier.estimate !== undefined && tier.estimate !== null) return fmt(tier.estimate, symbol);
  if (tier.estimate_low !== undefined || tier.estimate_high !== undefined) {
    if (tier.estimate_low === tier.estimate_high) return fmt(tier.estimate_low, symbol);
    return `${fmt(tier.estimate_low, symbol)} – ${fmt(tier.estimate_high, symbol)}`;
  }
  return "?";
}

function ReasoningWithFootnotes({ text }: { text: string }) {
  // Turn "...figure [1]..." into a superscript link jumping to the footnote anchor.
  const parts = text.split(/(\[\d+\])/g);
  return (
    <p style={{ margin: 0 }}>
      {parts.map((part, i) => {
        const m = part.match(/^\[(\d+)\]$/);
        if (m) {
          return (
            <a key={i} href={`#fn-market-${m[1]}`} style={{ fontSize: 11, verticalAlign: "super", fontWeight: 700 }}>
              [{m[1]}]
            </a>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </p>
  );
}

const TIER_COLOR: Record<string, string> = {
  TAM: "#0f9d8f", // teal - matches brand accent
  SAM: "#3b6fc4", // corporate blue
  SOM: "#c0577a", // muted plum
};

export default function TamSamSomView({ data }: { data: TamSamSom }) {
  const symbol = data.currency === "EUR" ? "€" : "$";
  const rows: { level: string; def: string; tier: Tier }[] = [
    { level: "TAM", def: "Marché total adressable", tier: data.tam },
    { level: "SAM", def: "Part adressable sur nos zones ciblées", tier: data.sam },
    { level: "SOM", def: "Part captable de façon réaliste (3–5 ans)", tier: data.som },
  ];

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 14, marginBottom: 4 }}>
        {rows.map((r) => (
          <div
            key={r.level}
            style={{
              border: "1px solid var(--panel-border)", borderTop: `4px solid ${TIER_COLOR[r.level]}`,
              borderRadius: 14, padding: "20px 20px 18px", background: "#fbfcfe",
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 800, color: TIER_COLOR[r.level], textTransform: "uppercase", letterSpacing: "0.06em" }}>{r.level}</div>
            <div style={{ fontSize: 12, color: "var(--text-dim)", margin: "4px 0 10px" }}>{r.def}</div>
            <div style={{ fontSize: 28, fontWeight: 800, color: "var(--text)", letterSpacing: "-0.01em" }}>{rangeStr(r.tier, symbol)}</div>
          </div>
        ))}
      </div>

      <details className="collapsible" style={{ marginTop: 16, boxShadow: "none" }} open>
        <summary>
          Calculation details
          <span className="summary-sub">how we got these numbers — top-down, sourced</span>
        </summary>
        <div className="collapsible-body" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {rows.map((r) => (
            <div key={r.level}>
              <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 4, color: TIER_COLOR[r.level] }}>{r.level}</div>
              <ReasoningWithFootnotes text={r.tier.reasoning || "No detail provided."} />
              {r.level === "SAM" && r.tier.pct_of_tam != null && (
                <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 4 }}>
                  Appliqué au TAM : {(r.tier.pct_of_tam * 100).toFixed(0)}%
                </div>
              )}
              {r.level === "SOM" && r.tier.capture_rate_low_pct != null && (
                <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 4 }}>
                  Taux de capture retenu : {r.tier.capture_rate_low_pct}–{r.tier.capture_rate_high_pct}% (convention d'analyste, pas une donnée sourcée)
                </div>
              )}
            </div>
          ))}

          {data.footnotes.length > 0 && (
            <div style={{ borderTop: "1px dashed var(--panel-border)", paddingTop: 10, marginTop: 4 }}>
              {data.footnotes.map((fn) => (
                <div key={fn.n} id={`fn-market-${fn.n}`} style={{ fontSize: 11.5, color: "var(--text-dim)", marginBottom: 4 }}>
                  <sup style={{ fontWeight: 700 }}>{fn.n}</sup> {fn.detail}
                  {fn.source_url && (
                    <>
                      {" — "}
                      <a href={fn.source_url} target="_blank" rel="noreferrer">{fn.source_name || fn.source_url}</a>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </details>
    </div>
  );
}
