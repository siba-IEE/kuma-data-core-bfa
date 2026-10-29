"""Endpoints `/api/v1/horaire/<localite>/<grandeur>` - passe-plat horaire.

Deux endpoints distincts :

- ``GET /v1/horaire/{localite}/{grandeur}`` : retourne les données
  horaires passe-plat pour une fenêtre temporelle donnée.
- ``GET /v1/horaire/{localite}/{grandeur}/disponibilite`` : retourne
  la plage temporelle disponible.

Architecture :

1. Validation Pydantic des paramètres (schéma
   :class:`api.v1.schemas.horaire.ParametresHoraire`).
2. Vérification de la localité contre le référentiel (code complet).
3. Appel client externe via
   :func:`external.nasa_power.fetch_hourly` (retry transverse inclus).
4. Conversion réponse amont -> format Kuma cohérent via
   :func:`services.horaire.convertir_valeurs_amont_en_resultats`
   (sentinelles ``-999.0`` -> ``None``, clés ``YYYYMMDDHH`` ->
   ``datetime``, unité cible dérivée).
5. Filtrage sur la plage temporelle demandée, sérialisation JSON ou
   CSV.

Authentification : Bearer existante via ``CleApiValidee``.

Les codes erreur et messages ne nomment pas la source amont. Une localité
pouvant porter plusieurs séries horaires de la même grandeur, le paramètre
et le champ de réponse ``source`` nomment la source de la série servie
(ADR-0023).

Mode calcul disponibilité v1 retenu : **B1 statique** (formule
``fin = mois_courant - 5 mois - 1 jour``). Choix justifié pour v1 par
la simplicité (0 appel externe) et la robustesse contre les variations
de politique amont restant à constater empiriquement. L'option B2
(scan empirique des sentinelles) peut être adoptée ultérieurement si
le besoin d'une borne dynamique précise est observé en production.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.api.codes_erreur import CodeErreur
from kuma_data_core.api.dependencies import CleApiValidee, parametres_requete
from kuma_data_core.api.erreurs import ExceptionKuma
from kuma_data_core.api.v1.schemas.horaire import (
    DATE_DEBUT_DISPONIBILITE,
    ParametresHoraire,
    PlageTemporelle,
    ReponseDisponibilite,
    ReponseHoraire,
    ResultatHoraire,
    SourceHoraire,
)
from kuma_data_core.core.config import get_settings
from kuma_data_core.db.session import obtenir_session
from kuma_data_core.exceptions import (
    NasaPowerHttpError,
    NasaPowerPayloadError,
    NasaPowerRateLimitError,
    NasaPowerTimeoutError,
)
from kuma_data_core.external.nasa_power import fetch_hourly
from kuma_data_core.services.horaire import (
    SOURCE_RELAIS,
    code_parametre_amont,
    convertir_valeurs_amont_en_resultats,
    filtrer_resultats_par_plage,
    relayable,
    unite_cible,
)
from kuma_data_core.services.localites import coordonnees_localite

routeur = APIRouter(prefix="/horaire", tags=["horaire-passe-plat"])


# === Resolution de la localite contre le referentiel ======================


def _resoudre_localite(session: Session, localite: str) -> str:
    """Vérifie le code de localité du chemin contre le référentiel.

    Code complet de la table ``localites`` (``bfa_com_ouagadougou`` par
    exemple). Localité inconnue ou inactive : 404 ``RESSOURCE_LOCALITE_INCONNUE``.
    """
    existe = session.execute(
        text("SELECT 1 FROM localites WHERE code = :code AND actif = TRUE"),
        {"code": localite},
    ).first()
    if existe is None:
        raise ExceptionKuma(
            code=CodeErreur.RESSOURCE_LOCALITE_INCONNUE,
            message=f"Localite '{localite}' introuvable dans le referentiel.",
            statut_http=status.HTTP_404_NOT_FOUND,
        )
    return localite


# === Mois de latence NRT (option B1 disponibilité) ========================

_LATENCE_NRT_MOIS: int = 5
"""Latence NRT amont observée empiriquement 5 mois.

Utilisée par la formule B1 statique :
``fin_disponible = mois_courant - 5 mois - 1 jour``.
"""


# === Helpers internes =====================================================


def _calculer_plage_disponible(aujourdhui: date | None = None) -> PlageTemporelle:
    """Calcule la plage disponible passe-plat selon la formule B1 statique.

    Returns:
        ``PlageTemporelle`` avec ``debut = 2001-01-01`` (borne historique)
        et ``fin = aujourd_hui - 5 mois - 1 jour``.
    """
    reference = aujourdhui if aujourdhui is not None else date.today()
    # Soustraction "5 mois" approximée à 5 * 30 jours pour robustesse
    # (précision ~jours-week ; option B2 cachée adopterait scan précis).
    fin = reference - timedelta(days=_LATENCE_NRT_MOIS * 30 + 1)
    return PlageTemporelle(debut=DATE_DEBUT_DISPONIBILITE, fin=fin)


def _serialiser_csv(resultats: list[ResultatHoraire]) -> str:
    """Sérialise une liste de ResultatHoraire en CSV."""
    buffer = io.StringIO()
    w = csv.writer(buffer)
    w.writerow(["instant", "valeur", "unite", "statut_editorial"])
    for r in resultats:
        valeur_str = "" if r.valeur is None else str(r.valeur)
        w.writerow([r.instant.isoformat(), valeur_str, r.unite, r.statut_editorial])
    return buffer.getvalue()


def _gerer_erreur_amont(exc: Exception) -> None:
    """Mappe les exceptions du client externe vers ExceptionKuma 503.

    Principe « Kuma assume » : le message ne mentionne pas la source
    amont. Le consommateur reçoit un message générique « service
    passe-plat horaire temporairement indisponible » avec le code
    ``PASSE_PLAT_INDISPONIBLE``.
    """
    if isinstance(
        exc,
        NasaPowerTimeoutError
        | NasaPowerRateLimitError
        | NasaPowerHttpError
        | NasaPowerPayloadError,
    ):
        raise ExceptionKuma(
            code=CodeErreur.PASSE_PLAT_INDISPONIBLE,
            message="Le service passe-plat horaire est temporairement indisponible.",
            statut_http=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    raise exc


# === Lever passe_plat : service du stocké validé =========


def _chercher_serie_horaire_stockee(
    session: Session, localite_code_complet: str, grandeur: str, source: str | None = None
) -> tuple[int, date, date, str] | None:
    """Cherche la série horaire stockée au catalogue pour (localité, grandeur).

    ``source`` restreint la recherche aux séries de cette source (ADR-0023) ;
    sans elle, la série de la source du relais l'emporte (``SOURCE_RELAIS``),
    puis la plus ancienne.

    Renvoie ``(serie_id, periode_debut, periode_fin, source)`` si une série horaire
    active **portant des mesures stockées** existe pour ce couple, ``None``
    sinon. La jointure sur ``localites.code`` résout le couple
    indépendamment du nommage de la série.

    La clause ``EXISTS`` écarte les séries « coquilles » (métadonnées
    actives sans aucune ligne courante, la leur ou celle de leur porteuse,
    ADR-0026) : retenue, une coquille dont la période couvre la fenêtre
    demandée ferait servir 200 avec zéro résultat. Le ``ORDER BY`` rend la
    sélection déterministe si plusieurs séries portent des mesures.
    """
    row = session.execute(
        text(
            """
            SELECT sm.id, sm.periode_debut, sm.periode_fin, s.code AS source
            FROM series_metadonnees sm
            JOIN localites l ON l.id = sm.localite_id
            JOIN sources s ON s.id = sm.source_id
            WHERE l.code = :localite
              AND sm.grandeur_code = :grandeur
              AND sm.granularite = 'horaire'
              AND sm.actif = TRUE
              AND (CAST(:source AS text) IS NULL OR s.code = :source)
              AND EXISTS (
                  SELECT 1 FROM v_mesures_horaires m
                  WHERE m.serie_id = sm.id
              )
            ORDER BY (s.code = :relais) DESC, sm.id
            LIMIT 1
            """
        ),
        {
            "localite": localite_code_complet,
            "grandeur": grandeur,
            "source": source,
            "relais": SOURCE_RELAIS,
        },
    ).first()
    if row is None or row.periode_fin is None:
        return None
    return int(row.id), row.periode_debut, row.periode_fin, str(row.source)


def _lire_horaire_validee(
    session: Session,
    serie_id: int,
    grandeur: str,
    periode_debut: date,
    periode_fin: date,
) -> list[ResultatHoraire]:
    """Lit les points horaires ``valide_auto`` d'une série sur la plage.

    Les lignes rejetées par le QC (statut ``brut``) sont exclues. Instant
    renvoyé en UTC naïf, cohérent avec le passe-plat. Lit la vue
    ``v_mesures_horaires`` : une série qui lit une porteuse rend les mesures
    de sa porteuse (ADR-0026).
    """
    rows = session.execute(
        text(
            """
            SELECT instant_mesure, valeur
            FROM v_mesures_horaires
            WHERE serie_id = :serie_id
              AND statut IN ('valide_auto', 'valide_humain', 'publie')
              AND (instant_mesure AT TIME ZONE 'UTC')::date >= :debut
              AND (instant_mesure AT TIME ZONE 'UTC')::date <= :fin
            ORDER BY instant_mesure
            """
        ),
        {"serie_id": serie_id, "debut": periode_debut, "fin": periode_fin},
    ).all()
    unite = unite_cible(grandeur)
    return [
        ResultatHoraire(
            instant=r.instant_mesure.astimezone(UTC).replace(tzinfo=None),
            valeur=float(r.valeur),
            unite=unite,
            statut_editorial="valide_auto",
        )
        for r in rows
    ]


def _repondre_horaire(
    params: ParametresHoraire, resultats: list[ResultatHoraire], source: str
) -> Response:
    """Sérialise une liste de ResultatHoraire en JSON (défaut) ou CSV."""
    if params.format_sortie == "csv":
        return Response(content=_serialiser_csv(resultats), media_type="text/csv")
    reponse = ReponseHoraire(
        localite=params.localite,
        grandeur=params.grandeur,
        source=source,
        periode_demandee=PlageTemporelle(debut=params.periode_debut, fin=params.periode_fin),
        resultats=resultats,
    )
    return JSONResponse(content=reponse.model_dump(mode="json"))


# === Endpoint data ========================================================


@routeur.get(
    "/{localite}/{grandeur}",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="Donnees horaires sur une fenetre temporelle (stocke valide ou relais)",
)
def grandeur_horaire(
    params: Annotated[ParametresHoraire, Depends(parametres_requete(ParametresHoraire))],
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
) -> Response:
    """Retourne les valeurs horaires d'une localité sur une plage temporelle.

    Une série stockée qui couvre la plage sert ses heures validées
    (``valide_auto``), les siennes ou celles de la porteuse de sa maille
    (ADR-0026). Sinon, la requête est relayée vers le service amont, puis
    convertie au format Kuma cohérent (instant ISO 8601, valeur ou ``null``
    si sentinelle, unité cible, statut éditorial ``passe_plat_non_valide``).

    Pré-validation : la fenêtre demandée doit être incluse dans la
    plage disponible (option B1 statique). Sinon : 400
    ``PLAGE_TEMPORELLE_NON_DISPONIBLE`` avec détails enrichis.

    Erreurs :

    - 401 ``AUTH_HEADER_MANQUANT`` / ``AUTH_CLE_INVALIDE`` (auth Bearer).
    - 422 ``VALIDATION_VALEUR_INVALIDE`` (paramètre Pydantic hors plage).
    - 400 ``PLAGE_TEMPORELLE_NON_DISPONIBLE`` (plage demandée hors
      disponibilité ; ou, en profil édition figée ADR-0003 D6, plage
      non couverte par le stocké - aucun relais amont n'est tenté).
    - 503 ``PASSE_PLAT_INDISPONIBLE`` (service amont indisponible
      après retry).
    """
    plage_disponible = _calculer_plage_disponible()
    if params.periode_debut < plage_disponible.debut or params.periode_fin > plage_disponible.fin:
        raise ExceptionKuma(
            code=CodeErreur.PLAGE_TEMPORELLE_NON_DISPONIBLE,
            message="La plage demandee n'est pas disponible.",
            statut_http=status.HTTP_400_BAD_REQUEST,
            details={
                "plage_demandee": f"{params.periode_debut} / {params.periode_fin}",
                "plage_disponible": f"{plage_disponible.debut} / {plage_disponible.fin}",
            },
        )

    localite_complet = _resoudre_localite(session, params.localite)

    # Lever passe_plat : si une série horaire stockée couvre la plage
    # demandée, servir la donnée validée (statut valide_auto) au lieu de
    # relayer la source amont non validée.
    serie_stockee = _chercher_serie_horaire_stockee(
        session, localite_complet, params.grandeur, params.source
    )
    if serie_stockee is not None:
        serie_id, periode_debut_serie, periode_fin_serie, source_serie = serie_stockee
        if periode_debut_serie <= params.periode_debut and params.periode_fin <= periode_fin_serie:
            resultats_stockes = _lire_horaire_validee(
                session, serie_id, params.grandeur, params.periode_debut, params.periode_fin
            )
            return _repondre_horaire(params, resultats_stockes, source_serie)

    # Une source autre que le relais, ou une grandeur sans relais, ne se sert
    # que depuis le stocké (ADR-0023).
    if params.source not in (None, SOURCE_RELAIS) or not relayable(params.grandeur):
        details = {"plage_demandee": f"{params.periode_debut} / {params.periode_fin}"}
        if serie_stockee is not None:
            details["plage_disponible"] = f"{serie_stockee[1]} / {serie_stockee[2]}"
            message = "La plage demandee n'est pas couverte par la serie horaire stockee."
        elif params.source is None:
            message = "Aucune serie horaire stockee pour cette localite et cette grandeur."
        else:
            message = "Aucune serie horaire stockee pour cette localite, grandeur et source."
        raise ExceptionKuma(
            code=CodeErreur.PLAGE_TEMPORELLE_NON_DISPONIBLE,
            message=message,
            statut_http=status.HTTP_400_BAD_REQUEST,
            details=details,
        )

    # Profil édition figée (ADR-0003, D6) : jamais de relais amont. Une
    # plage non couverte par le stocké est indisponible, point - zéro
    # dépendance sortante sur le serveur public.
    if get_settings().edition_figee:
        raise ExceptionKuma(
            code=CodeErreur.PLAGE_TEMPORELLE_NON_DISPONIBLE,
            message=(
                "La plage demandee n'est pas couverte par les donnees stockees de cette edition."
            ),
            statut_http=status.HTTP_400_BAD_REQUEST,
            details={
                "plage_demandee": f"{params.periode_debut} / {params.periode_fin}",
                "raison": "edition_figee_sans_relais_temps_reel",
            },
        )

    # Repli passe-plat (relais NASA POWER, non validé éditorialement).
    latitude, longitude = coordonnees_localite(localite_complet)
    code_amont = code_parametre_amont(params.grandeur)

    try:
        reponse_amont = fetch_hourly(
            latitude=latitude,
            longitude=longitude,
            parameters=[code_amont],
            start=params.periode_debut,
            end=params.periode_fin,
        )
    except Exception as exc:
        _gerer_erreur_amont(exc)
        raise  # unreachable, _gerer_erreur_amont raise toujours

    valeurs_par_cle = reponse_amont.properties.parameter.get(code_amont, {})
    resultats_bruts = convertir_valeurs_amont_en_resultats(
        valeurs_par_cle=valeurs_par_cle,
        grandeur=params.grandeur,
    )
    resultats = filtrer_resultats_par_plage(
        resultats=resultats_bruts,
        periode_debut=params.periode_debut,
        periode_fin=params.periode_fin,
    )
    return _repondre_horaire(params, resultats, SOURCE_RELAIS)


# === Endpoint disponibilité ===============================================


@routeur.get(
    "/{localite}/{grandeur}/disponibilite",
    response_model=ReponseDisponibilite,
    status_code=status.HTTP_200_OK,
    summary="Plage temporelle disponible pour le passe-plat horaire",
)
def disponibilite_horaire(
    localite: str,
    grandeur: str,
    _cle: CleApiValidee,
    session: Annotated[Session, Depends(obtenir_session)],
    source: Annotated[
        SourceHoraire | None,
        Query(
            description=(
                "Source de la serie horaire (ADR-0023). Par defaut, la serie que sert "
                "/v1/horaire sans source."
            )
        ),
    ] = None,
) -> ReponseDisponibilite:
    """Retourne la plage temporelle disponible pour (localite, grandeur, source).

    Même choix de série que ``/v1/horaire`` (ADR-0023). Pour la source du
    relais et une grandeur qu'il sert, hors édition figée, la plage est celle
    du relais : début à la borne historique (``2001-01-01``), fin calculée par
    la formule statique B1 (``aujourd'hui - 5 mois - 1 jour``), latence de la
    source amont ; le couple ``(localite, grandeur)`` n'est alors pas vérifié.

    Sinon, la plage est celle de la série stockée : celle de la source
    demandée, ou, sans source, celle de la source du relais si elle existe,
    puis la plus ancienne (CAMS Radiation pour ``ghi_ciel_clair``). Elle est
    recoupée avec la fenêtre du relais, que ``/v1/horaire`` impose à toute
    requête. Sans série stockée, ou si le recoupement est vide : 404
    ``RESSOURCE_SERIE_INCONNUE``.
    """
    fenetre = _calculer_plage_disponible()
    if source in (None, SOURCE_RELAIS) and relayable(grandeur) and not get_settings().edition_figee:
        return ReponseDisponibilite(
            localite=localite,
            grandeur=grandeur,
            source=SOURCE_RELAIS,
            plage_disponible=fenetre,
        )
    serie = _chercher_serie_horaire_stockee(
        session, _resoudre_localite(session, localite), grandeur, source
    )
    if serie is None:
        raise ExceptionKuma(
            code=CodeErreur.RESSOURCE_SERIE_INCONNUE,
            message=(
                "Aucune serie horaire stockee pour cette localite et cette grandeur."
                if source is None
                else "Aucune serie horaire stockee pour cette localite, grandeur et source."
            ),
            statut_http=status.HTTP_404_NOT_FOUND,
        )
    _, debut_serie, fin_serie, source_serie = serie
    debut = max(debut_serie, fenetre.debut)
    fin = min(fin_serie, fenetre.fin)
    if fin < debut:
        raise ExceptionKuma(
            code=CodeErreur.RESSOURCE_SERIE_INCONNUE,
            message="La serie horaire stockee ne recoupe pas la plage servie par /v1/horaire.",
            statut_http=status.HTTP_404_NOT_FOUND,
            details={"plage_serie": f"{debut_serie} / {fin_serie}"},
        )
    return ReponseDisponibilite(
        localite=localite,
        grandeur=grandeur,
        source=source_serie,
        plage_disponible=PlageTemporelle(debut=debut, fin=fin),
        statut_editorial="valide_auto",
    )
