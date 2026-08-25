"use client";

type Competitor = {
  name: string;
  description: string;
  domain: string | null;
  source_url: string | null;
  source_name: string | null;
  in_deck: boolean;
};

const PALETTE = ["#0f9d8f", "#dd6b20", "#3b82c4", "#7c5cbf", "#c0577a", "#1f9366"];

function colorFor(name: string) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return PALETTE[Math.abs(hash) % PALETTE.length];
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

function Avatar({ name, domain }: { name: string; domain: string | null }) {
  if (domain) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={`https://logo.clearbit.com/${domain}`}
        alt={name}
        className="competitor-avatar"
        style={{ background: "#fff", border: "1px solid var(--panel-border)" }}
        onError={(e) => {
          const target = e.currentTarget;
          target.onerror = null;
          target.style.display = "none";
          const fallback = target.nextSibling as HTMLElement | null;
          if (fallback) fallback.style.display = "flex";
        }}
      />
    );
  }
  return null;
}

export default function CompetitorGrid({ competitors }: { competitors: Competitor[] }) {
  if (competitors.length === 0) return null;
  return (
    <div className="competitor-grid">
      {competitors.map((c, i) => (
        <div key={i} className="competitor-card">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ position: "relative" }}>
              <Avatar name={c.name} domain={c.domain} />
              <div className="competitor-avatar" style={{ background: colorFor(c.name), display: c.domain ? "none" : "flex" }}>
                {initials(c.name)}
              </div>
            </div>
            <div className="competitor-name">{c.name}</div>
          </div>
          <div className="competitor-desc">{c.description || "No description available from sources."}</div>
          <div className={`competitor-tag ${c.in_deck ? "known" : "new"}`}>
            {c.in_deck ? "In deck" : "Not in deck"}
          </div>
          {c.source_url && (
            <a href={c.source_url} target="_blank" rel="noreferrer" style={{ fontSize: 11.5 }}>
              {c.source_name || "Source"}
            </a>
          )}
        </div>
      ))}
    </div>
  );
}
