"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

const STAGES = [
  { value: "pre_seed", label: "Pre-seed" },
  { value: "seed", label: "Seed" },
  { value: "series_a", label: "Series A" },
  { value: "series_b_plus", label: "Series B+" },
];

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
      setError("Le nom de la société et le pitch deck (.pptx ou .pdf) sont obligatoires.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setStatus("Création de l'espace de travail…");
      const company = await api.createCompany(name);

      setStatus("Dépôt du deck et lancement du pipeline extraction → recherche → vérification → raisonnement (peut prendre un moment en mode direct)…");
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
    <form onSubmit={handleSubmit} className="new-dossier-card">
      <label>Nom de la société</label>
      <div className="new-dossier-field">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ex. Noria" />
      </div>

      <label>Secteur</label>
      <div className="new-dossier-field">
        <input value={sector} onChange={(e) => setSector(e.target.value)} placeholder="Ex. Assurance paramétrique B2B" />
      </div>

      <div className="new-dossier-row">
        <div>
          <label>Pays du siège</label>
          <div className="new-dossier-field">
            <input value={hqCountry} onChange={(e) => setHqCountry(e.target.value)} />
          </div>
        </div>
        <div>
          <label>Stade</label>
          <div className="new-dossier-field">
            <select value={stage} onChange={(e) => setStage(e.target.value)}>
              {STAGES.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <label>Pitch deck</label>
      <label className="new-dossier-dropzone" htmlFor="deck-file-input">
        <input
          id="deck-file-input"
          type="file"
          accept=".pptx,.pdf"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" style={{ marginBottom: 8 }}>
          <path d="M12 4V16M12 4L7 9M12 4L17 9" stroke="var(--dash-accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M4 16V18C4 19.1 4.9 20 6 20H18C19.1 20 20 19.1 20 18V16" stroke="var(--dash-accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <div className="new-dossier-dropzone-title">
          {file ? file.name : "Clique pour choisir un fichier"}
        </div>
        <div className="new-dossier-dropzone-sub">.pptx ou .pdf</div>
      </label>

      <button className="new-dossier-submit" type="submit" disabled={busy}>
        {busy ? "Analyse en cours…" : "Lancer l'analyse →"}
      </button>

      {status && <p className="new-dossier-status">{status}</p>}
      {error && <p className="new-dossier-error">{error}</p>}
    </form>
  );
}
