export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Company = {
  id: string;
  name: string;
  legal_name: string | null;
  stage: string;
  business_model: string;
  sector: string | null;
  hq_country: string | null;
  created_at: string | null;
};

export type TrayTile = {
  module: string;
  label: string;
  status: string;
  headline: string | null;
  red_flag_count: number;
};

export type Evidence = {
  id: string;
  module: string;
  claim: string;
  value: string | null;
  value_type: string | null;
  origin: string;
  source_tier: string;
  confidence: string;
  source_name: string | null;
  source_url: string | null;
  source_publication_date: string | null;
  retrieval_date: string | null;
  methodology: string | null;
  supporting_excerpt: string | null;
  assumptions_json: string[] | null;
};

export type ModuleResult = {
  id: string;
  module: string;
  status: string;
  headline: string | null;
  deck_value: string | null;
  platform_value: string | null;
  discrepancy_explanation: string | null;
  reasoning_json: { steps: { step: string; content: unknown; evidence_ids: string[] }[] } | null;
  evidence_ids_json: string[] | null;
  llm_mode: string | null;
  updated_at: string | null;
};

export type RedFlag = {
  id: string;
  module: string | null;
  category: string;
  severity: string;
  explanation: string;
  evidence_id: string | null;
  potential_impact: string | null;
  resolving_information: string | null;
};

export type Memo = {
  id: string;
  version: string;
  sections_json: { title: string; body: string; evidence_ids: string[]; kind?: string; data?: any }[] | null;
  recommendation: string | null;
  key_questions_json: string[] | null;
  generated_at: string | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { ...(init?.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : {}), ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; llm_mode: string; search_mode: string; pappers_mode: string }>("/health"),
  listCompanies: () => request<Company[]>("/companies"),
  createCompany: (name: string) => request<Company>("/companies", { method: "POST", body: JSON.stringify({ name }) }),
  getCompany: (id: string) => request<Company>(`/companies/${id}`),
  getTray: (id: string) => request<TrayTile[]>(`/companies/${id}/tray`),
  uploadDeck: (id: string, form: FormData) => request<{ company: Company; modules_triggered: string[] }>(`/companies/${id}/deck`, { method: "POST", body: form }),
  listModules: (id: string) => request<ModuleResult[]>(`/companies/${id}/modules`),
  getModule: (id: string, module: string) => request<ModuleResult>(`/companies/${id}/modules/${module}`),
  listEvidence: (id: string, module?: string) => request<Evidence[]>(`/companies/${id}/evidence${module ? `?module=${module}` : ""}`),
  listRedFlags: (id: string) => request<RedFlag[]>(`/companies/${id}/red-flags`),
  recalculateMarket: (id: string, body: { methodology: string; inputs: Record<string, number>; assumptions: string[] }) =>
    request(`/companies/${id}/modules/market/recalculate`, { method: "POST", body: JSON.stringify(body) }),
  submitMrrSeries: (id: string, monthly_values_eur: number[]) =>
    request(`/companies/${id}/modules/traction/mrr-series`, { method: "POST", body: JSON.stringify({ monthly_values_eur }) }),
  submitCacLtvCheck: (id: string, body: { cac: number; reported_ltv: number; gross_margin: number; arpa_monthly: number }) =>
    request(`/companies/${id}/modules/traction/cac-ltv-check`, { method: "POST", body: JSON.stringify(body) }),
  generateMemo: (id: string) => request<Memo>(`/companies/${id}/memo/generate`, { method: "POST" }),
  getMemo: (id: string) => request<Memo>(`/companies/${id}/memo`),
};
