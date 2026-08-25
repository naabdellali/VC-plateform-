// Small presentation helpers shared by the dashboard and the new-dossier page.
// Kept separate from lib/api.ts since these are pure display formatting, not
// API concerns.

export function formatEurCompact(amount: number): string {
  if (amount >= 1_000_000) {
    const millions = amount / 1_000_000;
    return `${millions.toLocaleString("fr-FR", { minimumFractionDigits: millions < 10 ? 1 : 0, maximumFractionDigits: 1 })} M €`;
  }
  if (amount >= 1_000) {
    return `${Math.round(amount / 1000).toLocaleString("fr-FR")} K €`;
  }
  return `${Math.round(amount).toLocaleString("fr-FR")} €`;
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

// A small fixed palette of gradient pairs, picked deterministically from the
// company id so a given company always gets the same colors across reloads
// without needing to persist a color choice anywhere.
const AVATAR_GRADIENTS: [string, string][] = [
  ["#0d8a5f", "#37b483"],
  ["#1c3d63", "#3f6d99"],
  ["#b7791f", "#dba552"],
  ["#6b3fa0", "#9a6fc9"],
  ["#0f6fa8", "#3f9fd6"],
  ["#9c7a35", "#c2a25f"],
];

export function gradientForId(id: string): [string, string] {
  let hash = 0;
  for (let i = 0; i < id.length; i++) {
    hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
  }
  return AVATAR_GRADIENTS[hash % AVATAR_GRADIENTS.length];
}

export function stageLabel(stage: string): string {
  return stage.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diffMs = Math.max(0, now - then);
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "à l'instant";
  if (mins < 60) return `il y a ${mins} min`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `il y a ${hours} h`;
  const days = Math.round(hours / 24);
  return `il y a ${days} j`;
}
