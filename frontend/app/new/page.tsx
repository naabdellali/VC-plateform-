"use client";

import Link from "next/link";
import NewCompanyForm from "@/components/NewCompanyForm";

export default function NewDossierPage() {
  return (
    <div className="new-dossier-page">
      <div className="dash-topnav">
        <div className="dash-brand">
          <div className="dash-brand-mark" />
          <span className="dash-brand-name">Seed4Soft</span>
        </div>
        <Link href="/" className="dash-tab">Retour aux dossiers</Link>
      </div>

      <div className="new-dossier-body">
        <div className="new-dossier-stepper">
          <div className="new-dossier-step">
            <div className="new-dossier-step-n" style={{ background: "var(--dash-accent)", color: "#fff" }}>1</div>
            <span style={{ fontSize: 12, fontWeight: 600 }}>Infos société</span>
          </div>
          <span className="new-dossier-step-line" style={{ background: "var(--dash-border)" }} />
          <div className="new-dossier-step">
            <div className="new-dossier-step-n" style={{ background: "var(--dash-accent)", color: "#fff" }}>2</div>
            <span style={{ fontSize: 12, fontWeight: 600 }}>Pitch deck</span>
          </div>
          <span className="new-dossier-step-line" style={{ background: "var(--dash-border)" }} />
          <div className="new-dossier-step">
            <div className="new-dossier-step-n" style={{ background: "var(--dash-border)", color: "var(--dash-text-dim)" }}>3</div>
            <span style={{ fontSize: 12, color: "var(--dash-text-dim)" }}>Analyse</span>
          </div>
        </div>

        <h1>Nouveau dossier</h1>
        <p className="new-dossier-sub">Informations de la société et pitch deck.</p>

        <NewCompanyForm />
      </div>
    </div>
  );
}
