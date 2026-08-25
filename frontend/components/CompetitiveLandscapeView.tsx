import { useState } from "react";
import FootnoteList, { withFootnoteLinks, Footnote } from "@/components/Footnotes";

const OCEAN_LABEL: Record<string, string> = {
  blue_ocean: "Blue Ocean",
  red_ocean: "Red Ocean",
  blood_red_ocean: "Blood Red Ocean",
};
const OCEAN_DOT_CLASS: Record<string, string> = {
  blue_ocean: "blue",
  red_ocean: "",
  blood_red_ocean: "dark",
};

export type Ocean = { type: string; label: string; reasoning: string | null };
export type LandscapeCompetitor = {
  name: string;
  description: string;
  domain: string | null;
  competitor_type: "direct" | "indirect" | null;
  country: string | null;
  size: string | null;
  in_deck: boolean;
};

export type CompetitiveLandscape = {
  market_intro: string | null;
  functions: string[];
  geographies: string[];
  matrix: { function: string; cells: Record<string, string> }[];
  competitors: LandscapeCompetitor[];
  closest_comparable: { name: string; description: string; source_url: string | null; source_name: string | null } | null;
  risk: string | null;
  ocean: Ocean | null;
  consolidation: string | null;
  footnotes: Footnote[];
};

function isEmptyCell(v: string | undefined) {
  return !v || /quasi absent|aucun acteur identifié|—|^-$/i.test(v);
}

// Public brand logo via the competitor's own domain - never fabricated, only
// rendered when `domain` was itself extracted from a source (see identify_competitors
// in llm_client.py). Hides itself silently if the logo can't be found.
function CompetitorLogo({ domain }: { domain: string | null }) {
  const [failed, setFailed] = useState(false);
  if (!domain || failed) return null;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={`https://logo.clearbit.com/${domain}`}
      alt=""
      className="competitor-logo"
      onError={() => setFailed(true)}
    />
  );
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
  const isDoc = variant === "document";

  const oceanBlock = data.ocean && (
    isDoc ? (
      <p style={{ fontSize: 13.5, lineHeight: 1.65, margin: "0 0 14px" }}>
        Le marché se comporte comme un <b>{data.ocean.label || OCEAN_LABEL[data.ocean.type]}</b>
        {data.ocean.reasoning ? ` : ${data.ocean.reasoning}` : "."}
      </p>
    ) : (
      <div className="landscape-hero">
        <span className={`ocean-badge large ocean-${data.ocean.type}`}>
          <span className={`ocean-dot ${OCEAN_DOT_CLASS[data.ocean.type] || ""}`} />
          {data.ocean.label || OCEAN_LABEL[data.ocean.type]}
        </span>
        {data.ocean.reasoning && <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-dim)", maxWidth: 640 }}>{data.ocean.reasoning}</span>}
        {data.closest_comparable && (
          <span className="comparable-sub">
            Comparable le plus proche : <b>{data.closest_comparable.name}</b>
          </span>
        )}
      </div>
    )
  );

  const functionGroups = data.matrix.length > 0 && (
    <div className="function-group-list">
      {data.matrix.map((row, i) => (
        <div key={row.function} className="function-group">
          <div className="function-name">{isDoc ? `${i + 1}. ` : ""}{row.function}</div>
          <div className="geo-row">
            {data.geographies.map((g) => (
              <div key={g} className="geo-col">
                <div className="geo-label">{g}</div>
                {isEmptyCell(row.cells[g]) ? (
                  <span className="player-chip empty">Aucun acteur identifié</span>
                ) : (
                  row.cells[g].split(/,\s*/).map((name, i) => (
                    <span key={i} className="player-chip">{name}</span>
                  ))
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );

  const direct = data.competitors.filter((c) => c.competitor_type !== "indirect");
  const indirect = data.competitors.filter((c) => c.competitor_type === "indirect");
  const isFrance = (c: LandscapeCompetitor) => (c.country || "").toLowerCase().includes("france");
  const noDirectInFrance = direct.length > 0 && !direct.some(isFrance) && data.geographies.some((g) => g.toLowerCase() === "france");
  // Logos are a dashboard/tray affordance (CompetitorGrid) - the printable/downloadable
  // memo document never gets them, per analyst feedback that a memo should read as a
  // written document, not a card grid. The business-model description, on the other
  // hand, belongs in the memo - it's the actual analytical content, not chrome.
  const competitorCols = data.competitors.length > 0 && (
    <div className="competitor-type-cols">
      {direct.length > 0 && (
        <div className="competitor-type-col">
          <div className="type-heading">Concurrents directs</div>
          {noDirectInFrance && <div className="competitor-type-row-empty">Aucun concurrent direct identifié en France.</div>}
          {direct.map((c, i) => (
            <div key={i} className="competitor-type-row">
              {!isDoc && <CompetitorLogo domain={c.domain} />}
              <span className="name">{c.name}</span>
              <span className="meta">{[c.size, c.country || "Pays non précisé"].filter(Boolean).join(" · ")}</span>
              {c.description && <div className="competitor-desc-line">{c.description}</div>}
            </div>
          ))}
        </div>
      )}
      {indirect.length > 0 && (
        <div className="competitor-type-col">
          <div className="type-heading">Concurrents indirects</div>
          {indirect.map((c, i) => (
            <div key={i} className="competitor-type-row">
              {!isDoc && <CompetitorLogo domain={c.domain} />}
              <span className="name">{c.name}</span>
              <span className="meta">{[c.size, c.country || "Pays non précisé"].filter(Boolean).join(" · ")}</span>
              {c.description && <div className="competitor-desc-line">{c.description}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const narrative = (
    <>
      {data.closest_comparable && isDoc && (
        <p className="comparable-line">
          <b>Le comparable le plus proche est {data.closest_comparable.name}.</b> {data.closest_comparable.description}
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
      {data.risk && (
        <p style={{ margin: "6px 0", fontSize: isDoc ? undefined : 13.5, lineHeight: 1.6 }}>{withFootnoteLinks(data.risk, footnotePrefix)}</p>
      )}
      {data.consolidation && (
        <p style={{ margin: "10px 0 0", fontSize: isDoc ? undefined : 13.5, lineHeight: 1.6, color: "var(--text-dim)" }}>
          <b style={{ color: "var(--text)" }}>Consolidation du secteur.</b> {withFootnoteLinks(data.consolidation, footnotePrefix)}
        </p>
      )}
    </>
  );

  return (
    <div>
      {data.market_intro && <p className="landscape-intro">{data.market_intro}</p>}
      {oceanBlock}
      {functionGroups}
      {competitorCols}
      {narrative}
      <FootnoteList footnotes={data.footnotes} prefix={footnotePrefix} variant={variant} />
    </div>
  );
}
