"""
Pappers.fr client - French company registry data (SIREN/SIREF, legal
structure, dirigeants/officers, incorporation date, filings).

This is the primary Tier-1 source for the Founders/Background-check
module (spec section 17) for French entities. It is explicitly scoped to
France; non-French companies will need a different provider in the
roadmap (see README "Known limitations").

MOCK MODE: without PAPPERS_API_KEY, methods return an empty/"not found"
payload tagged mode="mock" - the founders module must render this as
"unable to independently verify," never as "no red flags found."
"""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from app.config import get_settings

settings = get_settings()

BASE_URL = "https://api.pappers.fr/v2"


@dataclass
class Dirigeant:
    nom: str
    prenom: str | None
    qualite: str | None  # e.g. "Président", "Directeur général"
    date_naissance: str | None = None
    autres_mandats: list[dict] = field(default_factory=list)


@dataclass
class CompanyRecord:
    mode: str  # "live" | "mock"
    found: bool
    siren: str | None = None
    denomination: str | None = None
    date_creation: str | None = None
    forme_juridique: str | None = None
    adresse: str | None = None
    dirigeants: list[Dirigeant] = field(default_factory=list)
    procedures_collectives: list[dict] = field(default_factory=list)  # bankruptcy/insolvency proceedings
    raw: dict | None = None


class PappersClient:
    @property
    def mode(self) -> str:
        return "live" if settings.pappers_available else "mock"

    def search_company(self, name: str) -> CompanyRecord:
        if not settings.pappers_available:
            return CompanyRecord(mode="mock", found=False)

        try:
            with httpx.Client(timeout=20) as client:
                resp = client.get(
                    f"{BASE_URL}/recherche",
                    params={"api_token": settings.pappers_api_key, "q": name, "par_page": 1},
                )
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError):
            return CompanyRecord(mode="live", found=False)

        results = data.get("resultats", [])
        if not results:
            return CompanyRecord(mode="live", found=False)

        top = results[0]
        siren = top.get("siren")
        if not siren:
            return CompanyRecord(mode="live", found=False, raw=top)

        return self.get_company(siren)

    def get_company(self, siren: str) -> CompanyRecord:
        if not settings.pappers_available:
            return CompanyRecord(mode="mock", found=False, siren=siren)

        try:
            with httpx.Client(timeout=20) as client:
                resp = client.get(
                    f"{BASE_URL}/entreprise",
                    params={"api_token": settings.pappers_api_key, "siren": siren},
                )
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError):
            return CompanyRecord(mode="live", found=False, siren=siren)

        dirigeants = [
            Dirigeant(
                nom=d.get("nom", ""),
                prenom=d.get("prenom"),
                qualite=d.get("qualite"),
                date_naissance=d.get("date_de_naissance"),
                autres_mandats=d.get("autres_mandats", []) or [],
            )
            for d in data.get("representants", []) or []
        ]

        return CompanyRecord(
            mode="live",
            found=True,
            siren=data.get("siren"),
            denomination=data.get("nom_entreprise") or data.get("denomination"),
            date_creation=data.get("date_creation"),
            forme_juridique=data.get("forme_juridique"),
            adresse=data.get("siege", {}).get("adresse_ligne_1") if data.get("siege") else None,
            dirigeants=dirigeants,
            procedures_collectives=data.get("procedures_collectives", []) or [],
            raw=data,
        )


_pappers_singleton: PappersClient | None = None


def get_pappers_client() -> PappersClient:
    global _pappers_singleton
    if _pappers_singleton is None:
        _pappers_singleton = PappersClient()
    return _pappers_singleton
