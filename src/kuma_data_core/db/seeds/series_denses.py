"""Séries journalières denses : fichiers Parquet versionnés et chargement (ADR-0017).

Un fichier par contrat et par lot sous ``seeds/donnees/denses/``. Une source
maillée sert la même série à toutes les localités d'un pixel (NASA POWER : 33
séries de rayonnement distinctes pour 351 communes) : le fichier ne porte
chaque série distincte qu'une fois, sous le code de sa première localité dans
l'ordre alphabétique (la représentante). Trois colonnes, triées par
représentante puis par jour :

- ``localite_code`` (dictionnaire) ;
- ``jour`` (date) ;
- ``valeur_e4`` (entier 32 bits, valeur en dix-millièmes, absente (NULL) si la
  valeur manque) : les valeurs restent exactes à 4 décimales, comme dans les
  CSV de ``series_csv``, et se compressent bien (codage par différences, puis
  zstd).

Métadonnées du fichier, en JSON :

- ``kuma.localites`` : représentante de chaque localité du lot ;
- ``kuma.points`` : latitude et longitude interrogées pour chaque localité ;
- ``kuma.source`` : service, version et date de consultation ;
- ``kuma.ecartees`` : valeurs servies hors des bornes du contrat et écartées
  (localité, jour, valeur servie), toutes admises par le contrat.

Une valeur manque quand la source n'en sert pas ou qu'elle est écartée ; le
jour n'a alors pas de valeur en base. L'écriture valide le contrat (localités
connues, chaque jour de la période une fois, bornes, écarts admis), puis relit
le fichier et le compare à son contenu avant de le mettre en place ; elle est
déterministe à version de pyarrow égale. Le chargement, appelé par les
migrations, insère une série par localité (``stockage = 'dense'``) et ne verse
dans ``mesures_journalieres_denses``, par ``COPY`` et sans réseau, que les
valeurs des représentantes, une ligne par année : les autres séries désignent
la série de leur représentante dans ``serie_porteuse_id``.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import sqlalchemy as sa

from kuma_data_core.db.seeds.series_csv import DOSSIER_DONNEES, NOMS_LOCALITES, ContratSerie

DOSSIER_DENSES: Path = DOSSIER_DONNEES / "denses"
ECHELLE: int = 10_000
SCHEMA: pa.Schema = pa.schema(
    [
        ("localite_code", pa.dictionary(pa.int16(), pa.string())),
        ("jour", pa.date32()),
        ("valeur_e4", pa.int32()),
    ]
)
CLE_LOCALITES: bytes = b"kuma.localites"
CLE_POINTS: bytes = b"kuma.points"
CLE_SOURCE: bytes = b"kuma.source"
CLE_ECARTEES: bytes = b"kuma.ecartees"
CHAMPS_SOURCE: tuple[str, ...] = ("service", "version", "consultation")
_EPOQUE: date = date(1970, 1, 1)
# Écart toléré entre un point du fichier et la localité en base, en degrés.
_TOLERANCE_POINT: float = 1e-6


def nom_fichier_dense(contrat: ContratSerie, lot: str) -> str:
    return f"{contrat.prefixe_code}_{lot}.parquet"


def dans_les_bornes(contrat: ContratSerie, valeur: float) -> bool:
    """Borne basse incluse si le contrat en fixe une, sinon valeur strictement positive."""
    # Comparaisons positives : une valeur NaN échoue et se trouve refusée.
    basse = valeur > 0.0 if contrat.borne_min is None else valeur >= contrat.borne_min
    return basse and valeur <= contrat.borne_max


@dataclass(frozen=True)
class SeriesDenses:
    """Contenu validé d'un fichier dense."""

    representantes: dict[str, str]  # localité -> représentante, toutes les localités du lot
    points: dict[str, tuple[float, float]]  # localité -> (latitude, longitude) interrogées
    source: dict[str, str]  # service, version, consultation
    ecartees: list[tuple[str, date, float]]  # (localité, jour, valeur servie)
    debut: date
    valeurs: dict[str, np.ndarray]  # représentante -> float64 (un par jour), NaN si absente

    @property
    def codes(self) -> list[str]:
        return sorted(self.representantes)

    def valeurs_de(self, code: str) -> np.ndarray:
        return self.valeurs[self.representantes[code]]

    def jours_absents(self, code: str) -> list[date]:
        """Jours de la période sans valeur pour une localité, écartées comprises."""
        return [
            self.debut + timedelta(days=int(k))
            for k in np.flatnonzero(np.isnan(self.valeurs_de(code)))
        ]

    def ecartees_de(self, code: str) -> list[tuple[date, float]]:
        return [(jour, valeur) for c, jour, valeur in self.ecartees if c == code]

    @property
    def nb_mesures(self) -> int:
        """Valeurs présentes, toutes localités comprises."""
        return sum(int((~np.isnan(self.valeurs_de(c))).sum()) for c in self.representantes)


def _jour_numero(jour: date) -> int:
    return (jour - _EPOQUE).days


def _verifier(contrat: ContratSerie, nom: str, denses: SeriesDenses) -> None:
    """Lève ``ValueError`` si le contenu viole le contrat."""
    codes = set(denses.representantes)
    inconnues = sorted(c for c in codes if c not in NOMS_LOCALITES)
    if inconnues:
        raise ValueError(f"{nom} : localités inconnues {inconnues[:3]!r}.")
    for code, rep in denses.representantes.items():
        if rep not in denses.valeurs or rep > code or denses.representantes.get(rep) != rep:
            raise ValueError(f"{nom} : représentante {rep!r} incohérente pour {code!r}.")
    if set(denses.valeurs) != set(denses.representantes.values()):
        raise ValueError(f"{nom} : séries sans localité.")
    if set(denses.points) != codes:
        raise ValueError(f"{nom} : points interrogés et localités ne concordent pas.")
    if set(denses.source) != set(CHAMPS_SOURCE):
        raise ValueError(f"{nom} : source décrite par {sorted(denses.source)!r}.")
    try:
        date.fromisoformat(denses.source["consultation"])
    except ValueError:
        raise ValueError(
            f"{nom} : date de consultation {denses.source['consultation']!r} illisible."
        ) from None
    if denses.debut != date(contrat.annee_debut, 1, 1):
        raise ValueError(f"{nom} : début {denses.debut.isoformat()} hors du contrat.")
    for rep, valeurs in denses.valeurs.items():
        if valeurs.shape != (contrat.nb_jours,):
            raise ValueError(
                f"{nom} : {rep} porte {valeurs.size} jours, {contrat.nb_jours} attendus."
            )
        presentes = valeurs[~np.isnan(valeurs)]
        if not presentes.size:
            raise ValueError(f"{nom} : série de {rep} sans aucune valeur.")
        basse = presentes > 0.0 if contrat.borne_min is None else presentes >= contrat.borne_min
        if not bool(np.all(basse & (presentes <= contrat.borne_max))):
            raise ValueError(f"{nom} : valeurs hors bornes pour {rep}.")
    distinctes = {v.tobytes() for v in denses.valeurs.values()}
    if len(distinctes) != len(denses.valeurs):
        raise ValueError(f"{nom} : séries identiques sous deux représentantes.")
    ecartees = {(code, jour.isoformat()) for code, jour, _ in denses.ecartees}
    admis = {(c, j) for c, j in contrat.ecarts_admis if c in codes}
    if len(ecartees) != len(denses.ecartees) or ecartees != admis:
        raise ValueError(
            f"{nom} : valeurs écartées {sorted(ecartees)!r}, {sorted(admis)!r} admises."
        )
    for code, jour, valeur in denses.ecartees:
        i = (jour - denses.debut).days
        if dans_les_bornes(contrat, valeur) or not np.isnan(denses.valeurs_de(code)[i]):
            raise ValueError(f"{nom} : écart incohérent pour {code} le {jour.isoformat()}.")


def ecrire_series_denses(
    contrat: ContratSerie,
    lot: str,
    series: list[tuple[str, float, float, list[tuple[date, float | None]]]],
    source: dict[str, str],
) -> Path:
    """Écrit des séries ``(localite_code, latitude, longitude, [(jour, valeur)])`` en Parquet.

    Chaque localité porte un jour par jour de la période ; ``None`` marque une
    valeur que la source ne sert pas. Une valeur hors des bornes du contrat est
    écartée si le contrat l'admet (``ecarts_admis``) et arrête l'écriture
    sinon. Les séries identiques ne sont écrites qu'une fois. Le contenu est
    validé avant écriture, puis relu et comparé.
    """
    nom = nom_fichier_dense(contrat, lot)
    debut = date(contrat.annee_debut, 1, 1)
    attendus = np.arange(contrat.nb_jours) + _jour_numero(debut)
    par_code: dict[str, np.ndarray] = {}
    points: dict[str, tuple[float, float]] = {}
    ecartees: list[tuple[str, date, float]] = []
    for code, latitude, longitude, mesures in series:
        if code in par_code:
            raise ValueError(f"{nom} : localité {code!r} en double.")
        mesures = sorted(mesures, key=lambda m: m[0])
        if not np.array_equal([_jour_numero(j) for j, _ in mesures], attendus):
            raise ValueError(f"{nom} : jours manquants, en double ou hors période pour {code}.")
        valeurs = []
        for jour, valeur in mesures:
            if valeur is None:
                valeurs.append(np.nan)
            elif dans_les_bornes(contrat, valeur):
                valeurs.append(round(valeur * ECHELLE) / ECHELLE)
            elif (code, jour.isoformat()) in contrat.ecarts_admis and np.isfinite(valeur):
                valeurs.append(np.nan)
                ecartees.append((code, jour, round(valeur, 4)))
            else:
                raise ValueError(
                    f"{nom} : valeur hors bornes pour {code} le {jour.isoformat()} "
                    f"({valeur!r}), écart non admis par le contrat."
                )
        par_code[code] = np.array(valeurs, dtype=np.float64)
        points[code] = (float(latitude), float(longitude))
    representantes: dict[str, str] = {}
    valeurs_par_rep: dict[str, np.ndarray] = {}
    vues: dict[bytes, str] = {}
    for code in sorted(par_code):
        rep = vues.setdefault(par_code[code].tobytes(), code)
        representantes[code] = rep
        if rep == code:
            valeurs_par_rep[code] = par_code[code]
    denses = SeriesDenses(
        representantes=representantes,
        points={c: points[c] for c in sorted(points)},
        source=dict(source),
        ecartees=sorted(ecartees),
        debut=debut,
        valeurs=valeurs_par_rep,
    )
    _verifier(contrat, nom, denses)

    reps = sorted(valeurs_par_rep)
    e4_tout = np.concatenate([valeurs_par_rep[r] for r in reps]) * ECHELLE
    absentes = np.isnan(e4_tout)
    if np.nanmax(np.abs(e4_tout), initial=0.0) > np.iinfo(np.int32).max:
        raise ValueError(f"{nom} : valeur hors de l'entier 32 bits.")
    metadonnees = {
        CLE_LOCALITES: denses.representantes,
        CLE_POINTS: {c: list(p) for c, p in denses.points.items()},
        CLE_SOURCE: {k: denses.source[k] for k in CHAMPS_SOURCE},
        CLE_ECARTEES: [[c, j.isoformat(), v] for c, j, v in denses.ecartees],
    }
    table = pa.table(
        {
            "localite_code": pa.DictionaryArray.from_arrays(
                pa.array(np.repeat(np.arange(len(reps), dtype=np.int16), contrat.nb_jours)),
                pa.array(reps, pa.string()),
            ),
            "jour": pa.array(np.tile(attendus, len(reps)).astype(np.int32)).cast(pa.date32()),
            "valeur_e4": pa.array(
                np.where(absentes, 0, np.rint(e4_tout)).astype(np.int32), mask=absentes
            ),
        },
        schema=SCHEMA.with_metadata(
            {
                k: json.dumps(v, ensure_ascii=False, separators=(",", ":"))
                for k, v in metadonnees.items()
            }
        ),
    )
    DOSSIER_DENSES.mkdir(parents=True, exist_ok=True)
    cible = DOSSIER_DENSES / nom
    with tempfile.NamedTemporaryFile(dir=DOSSIER_DENSES, suffix=".part", delete=False) as tmp:
        provisoire = Path(tmp.name)
    try:
        pq.write_table(
            table,
            provisoire,
            compression="zstd",
            compression_level=9,
            use_dictionary=["localite_code"],
            column_encoding={"jour": "DELTA_BINARY_PACKED", "valeur_e4": "DELTA_BINARY_PACKED"},
            row_group_size=1 << 20,
            write_statistics=False,
        )
        relu = _lire(contrat, provisoire, nom)
        if relu.representantes != denses.representantes or any(
            not np.array_equal(relu.valeurs[r], denses.valeurs[r], equal_nan=True) for r in reps
        ):
            raise ValueError(f"{nom} : le fichier relu diffère du contenu écrit.")
        os.chmod(provisoire, 0o644)
        os.replace(provisoire, cible)
    finally:
        provisoire.unlink(missing_ok=True)
    return cible


def _metadonnee(meta: dict[bytes, bytes], cle: bytes) -> Any:
    if cle not in meta:
        raise ValueError(f"métadonnée {cle.decode()} absente")
    return json.loads(meta[cle])


def _lire(contrat: ContratSerie, chemin: Path, nom: str) -> SeriesDenses:
    table = pq.read_table(chemin)
    if not table.schema.remove_metadata().equals(SCHEMA):
        raise ValueError(f"{nom} : schéma {table.schema.remove_metadata()!r}, {SCHEMA!r} attendu.")
    meta = table.schema.metadata or {}
    try:
        representantes = {str(c): str(r) for c, r in _metadonnee(meta, CLE_LOCALITES).items()}
        points = {
            str(c): (float(p[0]), float(p[1])) for c, p in _metadonnee(meta, CLE_POINTS).items()
        }
        source = {str(k): str(v) for k, v in _metadonnee(meta, CLE_SOURCE).items()}
        ecartees = [
            (str(c), date.fromisoformat(j), float(v)) for c, j, v in _metadonnee(meta, CLE_ECARTEES)
        ]
    except (ValueError, TypeError, AttributeError, IndexError) as erreur:
        raise ValueError(f"{nom} : métadonnées illisibles ({erreur}).") from None
    codes_ligne = table.column("localite_code").combine_chunks().dictionary_decode()
    codes_ligne = codes_ligne.to_numpy(zero_copy_only=False)
    jours = table.column("jour").cast(pa.int32()).to_numpy()
    colonne = table.column("valeur_e4").combine_chunks()
    e4 = colonne.to_numpy(zero_copy_only=False).astype(np.float64)
    n = contrat.nb_jours
    if not codes_ligne.size or codes_ligne.size % n:
        raise ValueError(f"{nom} : {codes_ligne.size} lignes, pas un multiple de {n}.")
    blocs = codes_ligne.reshape(-1, n)
    if not bool(np.all(blocs == blocs[:, :1])):
        raise ValueError(f"{nom} : localités mêlées dans un bloc de {n} jours.")
    reps = [str(c) for c in blocs[:, 0]]
    if reps != sorted(set(reps)):
        raise ValueError(f"{nom} : représentantes non triées ou en double.")
    debut = date(contrat.annee_debut, 1, 1)
    attendus = np.arange(n) + _jour_numero(debut)
    if not np.array_equal(jours.reshape(-1, n), np.broadcast_to(attendus, (len(reps), n))):
        raise ValueError(f"{nom} : jours manquants, en double ou hors de la période.")
    valeurs = (e4 / ECHELLE).reshape(-1, n)
    denses = SeriesDenses(
        representantes=representantes,
        points=points,
        source=source,
        ecartees=ecartees,
        debut=debut,
        valeurs={rep: valeurs[i] for i, rep in enumerate(reps)},
    )
    _verifier(contrat, nom, denses)
    return denses


def lire_series_denses(contrat: ContratSerie, lot: str) -> SeriesDenses:
    """Relit et valide un fichier dense ; ``ValueError`` s'il viole le contrat."""
    nom = nom_fichier_dense(contrat, lot)
    return _lire(contrat, DOSSIER_DENSES / nom, nom)


MOIS: tuple[str, ...] = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)


def date_en_clair(jour: date) -> str:
    """Date écrite en français, ex. « 2 décembre 2025 », « 1er mars 2020 »."""
    quantieme = "1er" if jour.day == 1 else str(jour.day)
    return f"{quantieme} {MOIS[jour.month - 1]} {jour.year}"


def _nombre(valeur: float) -> str:
    return f"{valeur:g}".replace(".", ",")


def _jours(jours: list[date]) -> str:
    liste = ", ".join(date_en_clair(j) for j in jours[:5])
    return liste + (f" et {len(jours) - 5} autres jours" if len(jours) > 5 else "")


def _lignes_annuelles(
    serie_id: int, niveau: str, debut: date, valeurs: np.ndarray
) -> list[tuple[int, int, str, list[int | None]]]:
    """Une ligne par année : valeurs en dix-millièmes, ``None`` pour un jour sans valeur."""
    e4 = np.rint(valeurs * ECHELLE)
    lignes = []
    k = 0
    for annee in range(debut.year, debut.year + 400):
        if k >= e4.size:
            break
        n = (date(annee + 1, 1, 1) - date(annee, 1, 1)).days
        bloc = e4[k : k + n]
        absents = np.isnan(bloc)
        if absents.any():
            liste: list[int | None] = [
                None if a else int(v) for v, a in zip(bloc.tolist(), absents.tolist(), strict=True)
            ]
        else:
            liste = bloc.astype(np.int64).tolist()
        lignes.append((serie_id, annee, niveau, liste))
        k += n
    return lignes


def charger_series_denses(
    bind: sa.Connection,
    contrat: ContratSerie,
    lot: str,
    localites: dict[str, int],
    note: Callable[[str], str],
    unite: str,
) -> tuple[int, int, int]:
    """Insère les séries d'un fichier dense et verse leurs valeurs ; renvoie (séries, lignes, valeurs).

    ``localites`` associe chaque code de localité attendu à son id ; le fichier
    doit couvrir exactement ces localités, aux coordonnées qu'elles ont en
    base. ``note`` donne la note publique d'une localité ; le chargement y
    ajoute les valeurs écartées (``unite`` en suffixe) et les jours que la
    source ne sert pas. Les séries des représentantes sont insérées d'abord et
    portent les lignes, une par année, versées par ``COPY`` ; les autres
    pointent vers elles par ``serie_porteuse_id``.
    """
    nom = nom_fichier_dense(contrat, lot)
    denses = lire_series_denses(contrat, lot)
    if denses.codes != sorted(localites):
        raise ValueError(f"{nom} ne couvre pas exactement le lot.")
    for row in bind.execute(
        sa.text("SELECT code, latitude, longitude FROM localites WHERE code = ANY(:c)"),
        {"c": denses.codes},
    ).all():
        lat, lon = denses.points[row.code]
        if max(abs(lat - float(row.latitude)), abs(lon - float(row.longitude))) > _TOLERANCE_POINT:
            raise ValueError(
                f"{nom} : {row.code} interrogée en ({lat}, {lon}), ailleurs qu'en base."
            )

    def note_complete(code: str) -> str:
        texte = note(code)
        ecartees = denses.ecartees_de(code)
        for jour, valeur in ecartees:
            texte += (
                f" Le {date_en_clair(jour)}, la source sert {_nombre(valeur)} {unite}, au-delà de "
                f"la borne de plausibilité du contrat ({_nombre(contrat.borne_max)} {unite}) : "
                "valeur écartée, jour sans valeur."
            )
        sans_source = sorted(set(denses.jours_absents(code)) - {j for j, _ in ecartees})
        if sans_source:
            texte += f" Sans valeur servie par la source : {_jours(sans_source)}."
        return texte

    series = sa.table(
        "series_metadonnees",
        sa.column("code", sa.String),
        sa.column("libelle", sa.Text),
        sa.column("localite_id", sa.BigInteger),
        sa.column("grandeur_code", sa.String),
        sa.column("source_id", sa.BigInteger),
        sa.column("periode_debut", sa.Date),
        sa.column("periode_fin", sa.Date),
        sa.column("methode_collecte", sa.String),
        sa.column("granularite", sa.String),
        sa.column("stockage", sa.String),
        sa.column("serie_porteuse_id", sa.BigInteger),
        sa.column("note_publique", sa.Text),
    )
    reps = sorted(denses.valeurs)
    ids: dict[str, int] = {}
    for groupe in (reps, [c for c in denses.codes if denses.representantes[c] != c]):
        if not groupe:
            continue
        bind.execute(
            series.insert(),
            [
                {
                    "code": contrat.code_serie(code),
                    "libelle": contrat.libelle_serie(code),
                    "localite_id": localites[code],
                    "grandeur_code": contrat.grandeur_code,
                    "source_id": contrat.source_id,
                    "periode_debut": contrat.periode_debut,
                    "periode_fin": contrat.periode_fin,
                    "methode_collecte": contrat.methode_collecte,
                    "granularite": "journalier",
                    "stockage": "dense",
                    "serie_porteuse_id": ids.get(denses.representantes[code]),
                    "note_publique": note_complete(code),
                }
                for code in groupe
            ],
        )
        par_code = {contrat.code_serie(c): c for c in groupe}
        ids |= {
            par_code[row.code]: int(row.id)
            for row in bind.execute(
                sa.text("SELECT code, id FROM series_metadonnees WHERE code = ANY(:c)"),
                {"c": list(par_code)},
            ).all()
        }
    lignes = [
        ligne
        for rep in reps
        for ligne in _lignes_annuelles(
            ids[rep], contrat.niveau_confiance, denses.debut, denses.valeurs[rep]
        )
    ]
    copie = (
        "COPY mesures_journalieres_denses "
        "(serie_id, annee, niveau_confiance_derive, valeurs_e4) FROM STDIN"
    )
    pilote = bind.connection.driver_connection
    with pilote.cursor() as curseur, curseur.copy(copie) as flux:  # type: ignore[union-attr]
        for ligne in lignes:
            flux.write_row(ligne)
    valeurs = sum(int((~np.isnan(denses.valeurs[r])).sum()) for r in reps)
    return len(denses.codes), len(lignes), valeurs
