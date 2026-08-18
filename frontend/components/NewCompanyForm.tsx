"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function NewCompanyForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [sector, setSector] = useState("");
  const [hqCountry, setHqCountry] = useState("France");
  const [stage, setStage] = useState("seed");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name || !file) {
      setError("Company name and pitch deck (.pptx or .pdf) are required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setStatus("Creating company workspace...");
      const company = await api.createCompany(name);

      setStatus("Uploading deck and running extract -> research -> verify -> reason pipeline (this can take a little while in live mode)...");
      const form = new FormData();
      form.append("file", file);
      form.append("stage", stage);
      form.append("business_model", "saas");
      if (sector) form.append("sector", sector);
      if (hqCountry) form.append("hq_country", hqCountry);
      await api.uploadDeck(company.id, form);

      router.push(`/company/${company.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
      setStatus(null);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="panel">
      <h2>New company workspace</h2>
      <label>Company name</label>
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme SaaS" />

      <label>Sector</label>
      <input value={sector} onChange={(e) => setSector(e.target.value)} placeholder="B2B expense management software" />

      <div style={{ display: "flex", gap: 12 }}>
        <div style={{ flex: 1 }}>
          <label>HQ country</label>
          <input value={hqCountry} onChange={(e) => setHqCountry(e.target.value)} />
        </div>
        <div style={{ flex: 1 }}>
          <label>Stage</label>
          <select value={stage} onChange={(e) => setStage(e.target.value)}>
            <option value="pre_seed">Pre-seed</option>
            <option value="seed">Seed</option>
            <option value="series_a">Series A</option>
            <option value="series_b_plus">Series B+</option>
          </select>
        </div>
      </div>

      <label>Pitch deck (.pptx or .pdf)</label>
      <input type="file" accept=".pptx,.pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />

      <div style={{ marginTop: 16 }}>
        <button className="btn" type="submit" disabled={busy}>
          {busy ? "Analyzing..." : "Upload & analyze"}
        </button>
      </div>

      {status && <p style={{ color: "var(--text-dim)", fontSize: 12.5, marginTop: 10 }}>{status}</p>}
      {error && <p style={{ color: "var(--sev-critical)", fontSize: 12.5, marginTop: 10 }}>{error}</p>}
    </form>
  );
}
