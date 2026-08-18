type Footnote = { n: number; detail: string; source_url: string | null; source_name: string | null };

export type CompetitiveLandscape = {
  functions: string[];
  geographies: string[];
  matrix: { function: string; cells: Record<string, string> }[];
  closest_comparable: { name: string; description: string; source_url: string | null; source_name: string | null } | null;
  differentiator: string | null;
  risk: string | null;
  footnotes: Footnote[];
};

function withFootnotes(text: string, prefix: string) {
  const parts = text.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const m = part.match(/^\[(\d+)\]$/);
    if (m) {
      return (
        <a key={i} href={`#fn-${prefix}-${m[1]}`} style={{ fontSize: 11, verticalAlign: "super", fontWeight: 700 }}>
          [{m[1]}]
        </a>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

export default function CompetitiveLandscapeView({
  data,
  variant = "card",
  footnotePrefix = "competition",
}: {
  data: CompetitiveLandscape;
  variant?: "card" | "document";
  footnotePrefix?: string;
}) {
  const table = (
    <table className={variant === "document" ? "doc-table" : "doc-table doc-table-card"}>
      <thead>
        <tr>
          <th>Fonction</th>
          {data.geographies.map((g) => (
            <th key={g}>{g}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {data.matrix.map((row) => (
          <tr key={row.function}>
            <td style={{ fontWeight: 600 }}>{row.function}</td>
            {data.geographies.map((g) => (
              <td key={g} style={{ color: !row.cells[g] || /quasi absent|—|^-$/i.test(row.cells[g]) ? "var(--text-dim)" : "var(--text)" }}>
                {row.cells[g] || "—"}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );

  const narrative = (
    <>
      {data.closest_comparable && (
        <p style={{ margin: variant === "document" ? "10px 0" : "10px 0 0", fontSize: variant === "document" ? undefined : 13.5, lineHeight: 1.6 }}>
          Le comparable le plus proche est <b>{data.closest_comparable.name}</b> : {data.closest_comparable.description}
          {data.closest_comparable.source_url && (
            <>
              {" "}
              <a href={data.closest_comparable.source_url} target="_blank" rel="noreferrer" style={{ fontSize: 11 }}>
                [source]
              </a>
            </>
          )}
        </p>
      )}
      {data.differentiator && (
        <p style={{ margin: "6px 0", fontSize: variant === "document" ? undefined : 13.5, lineHeight: 1.6 }}>{withFootnotes(data.differentiator, footnotePrefix)}</p>
      )}
      {data.risk && (
        <p style={{ margin: "6px 0", fontSize: variant === "document" ? undefined : 13.5, lineHeight: 1.6 }}>{withFootnotes(data.risk, footnotePrefix)}</p>
      )}
    </>
  );

  if (variant === "document") {
    return (
      <div className="doc-section">
        {table}
        {narrative}
        {data.footnotes.length > 0 && (
          <div className="doc-footnotes">
            {data.footnotes.map((fn) => (
              <div key={fn.n} id={`fn-${footnotePrefix}-${fn.n}`}>
                <sup>{fn.n}</sup>{fn.detail}
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
    );
  }

  return (
    <div>
      {table}
      {narrative}
      {data.footnotes.length > 0 && (
        <details className="collapsible" style={{ marginTop: 14, boxShadow: "none" }}>
          <summary>
            Sources
            <span className="summary-sub">{data.footnotes.length} footnote(s)</span>
          </summary>
          <div className="collapsible-body">
            {data.footnotes.map((fn) => (
              <div key={fn.n} id={`fn-${footnotePrefix}-${fn.n}`} style={{ fontSize: 11.5, color: "var(--text-dim)", marginBottom: 4 }}>
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
        </details>
      )}
    </div>
  );
}
