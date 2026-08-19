import FootnoteList, { withFootnoteLinks, Footnote } from "@/components/Footnotes";

const OCEAN_LABEL: Record<string, string> = {
  blue_ocean: "Blue Ocean",
  red_ocean: "Red Ocean",
  blood_red_ocean: "Blood Red Ocean",
};
const OCEAN_ICON: Record<string, string> = {
  blue_ocean: "🔵",
  red_ocean: "🔴",
  blood_red_ocean: "🩸",
};

export type Ocean = { type: string; label: string; reasoning: string | null };

export type CompetitiveLandscape = {
  functions: string[];
  geographies: string[];
  matrix: { function: string; cells: Record<string, string> }[];
  closest_comparable: { name: string; description: string; source_url: string | null; source_name: string | null } | null;
  differentiator: string | null;
  risk: string | null;
  ocean: Ocean | null;
  footnotes: Footnote[];
};

const withFootnotes = withFootnoteLinks;

export default function CompetitiveLandscapeView({
  data,
  variant = "card",
  footnotePrefix = "competition",
}: {
  data: CompetitiveLandscape;
  variant?: "card" | "document";
  footnotePrefix?: string;
}) {
  const oceanBadge = data.ocean && (
    <div style={{ marginBottom: 14, display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
      <span className={`ocean-badge ocean-${data.ocean.type}`}>
        {OCEAN_ICON[data.ocean.type] || "●"} {data.ocean.label || OCEAN_LABEL[data.ocean.type]}
      </span>
      {data.ocean.reasoning && <span style={{ fontSize: 12.5, color: "var(--text-dim)" }}>{data.ocean.reasoning}</span>}
    </div>
  );

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
        {oceanBadge}
        {table}
        {narrative}
        <FootnoteList footnotes={data.footnotes} prefix={footnotePrefix} />
      </div>
    );
  }

  return (
    <div>
      {oceanBadge}
      {table}
      {narrative}
      {data.footnotes.length > 0 && (
        <details className="collapsible" style={{ marginTop: 14, boxShadow: "none" }}>
          <summary>
            Sources
            <span className="summary-sub">{data.footnotes.length} footnote(s)</span>
          </summary>
          <div className="collapsible-body">
            <FootnoteList footnotes={data.footnotes} prefix={footnotePrefix} />
          </div>
        </details>
      )}
    </div>
  );
}
