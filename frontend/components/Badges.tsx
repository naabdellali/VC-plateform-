export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge badge-status-${status}`}>{status.replace(/_/g, " ")}</span>;
}

export function ConfidenceBadge({ confidence }: { confidence: string }) {
  return <span className={`badge badge-conf-${confidence}`}>{confidence}</span>;
}

export function SeverityBadge({ severity }: { severity: string }) {
  return <span className={`badge badge-sev-${severity}`}>{severity}</span>;
}
