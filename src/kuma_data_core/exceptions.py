"""Hiérarchie d'exceptions transverses de Kuma Data Core.

Regroupe les exceptions du client NASA POWER et les exceptions
éditoriales : ``TransitionEditorialeRefusee``, ``NiveauConfianceInvalide``,
``JustificationRequise``.

Convention : la hiérarchie expose une racine ``KumaError`` pour
permettre aux callers de catch un seul type s'ils ne souhaitent pas
discriminer. Chaque domaine fonctionnel a sa propre sous-racine
(``NasaPowerError`` pour le client API externe ; ``EditorialeError``
pour les workflows éditoriaux côté service).
"""

from __future__ import annotations


class KumaError(Exception):
    """Racine de la hiérarchie d'exceptions Kuma Data Core."""


class NasaPowerError(KumaError):
    """Racine des erreurs du client NASA POWER (`external.nasa_power`)."""


class NasaPowerHttpError(NasaPowerError):
    """Réponse HTTP non-2xx de l'API NASA POWER.

    Attributs :
        status_code : code HTTP retourné par NASA POWER.
        url : URL complète de la requête (paramètres compris).
        body : extrait du corps de la réponse (tronqué à 2000 caractères).
    """

    def __init__(self, status_code: int, url: str, body: str) -> None:
        self.status_code: int = status_code
        self.url: str = url
        self.body: str = body[:2000]
        super().__init__(
            f"NASA POWER a retourné HTTP {status_code} pour {url}. Extrait corps : {self.body!r}"
        )


class NasaPowerRateLimitError(NasaPowerHttpError):
    """HTTP 429 Too Many Requests reçu de NASA POWER.

    Sous-type de ``NasaPowerHttpError`` pour permettre aux callers
    d'implémenter une stratégie de retry spécifique au rate limiting.
    """


class NasaPowerPayloadError(NasaPowerError):
    """Le payload JSON reçu de NASA POWER ne respecte pas le schéma attendu.

    Levée lors d'une erreur de parsing JSON ou de validation pydantic
    contre les schémas ``NasaPowerResponse``. Le corps brut est attaché
    pour faciliter le diagnostic en spike.
    """

    def __init__(self, message: str, url: str, body: str) -> None:
        self.url: str = url
        self.body: str = body[:2000]
        super().__init__(f"{message} (url={url!r}, extrait corps={self.body!r})")


class NasaPowerTimeoutError(NasaPowerError):
    """Échec persistant de communication réseau avec NASA POWER après épuisement du retry.

    Couvre les timeouts (``httpx.TimeoutException``) et les disconnects
    serveur (``httpx.RemoteProtocolError``) au-delà du nombre de
    retries configurés (cf. ``external/_http_retry.py``). Expose
    ``url`` et ``timeout_seconds`` pour le diagnostic.
    """

    def __init__(self, url: str, timeout_seconds: float) -> None:
        self.url: str = url
        self.timeout_seconds: float = timeout_seconds
        super().__init__(f"Timeout NASA POWER après {timeout_seconds}s pour {url}")


# ===========================================================================
# Exceptions éditoriales
# ===========================================================================


class EditorialeError(KumaError):
    """Racine des erreurs des workflows éditoriaux Kuma.

    Les sous-types couvrent la machine d'état du statut éditorial
    (cf. ``kuma_data_core.editorial.statuts``) ainsi que la validation et
    l'override des niveaux de confiance A/B/C
    (cf. ``kuma_data_core.editorial.niveaux_confiance``).
    """


class TransitionEditorialeRefusee(EditorialeError):  # noqa: N818
    """Transition de statut éditorial rejetée par la machine d'état.

    Levée par ``kuma_data_core.editorial.statuts.transition_statut`` quand
    la paire ``(statut_courant, nouveau_statut)`` ne figure pas dans la
    matrice autorisée.

    Attributs :
        statut_courant : statut actuel de la ligne avant transition.
        nouveau_statut : statut cible refusé.
    """

    def __init__(self, statut_courant: str, nouveau_statut: str) -> None:
        self.statut_courant: str = statut_courant
        self.nouveau_statut: str = nouveau_statut
        super().__init__(
            f"Transition éditoriale refusée : "
            f"{statut_courant!r} -> {nouveau_statut!r} "
            f"n'est pas une transition autorisée (kuma_data_core.editorial.statuts)."
        )


class NiveauConfianceInvalide(EditorialeError):  # noqa: N818
    """Valeur de niveau de confiance hors du référentiel A/B/C.

    Levée par les fonctions de
    ``kuma_data_core.editorial.niveaux_confiance`` quand un caller
    fournit une valeur hors de ``NIVEAUX_CONFIANCE_AUTORISES``.
    """

    def __init__(self, valeur_recue: str) -> None:
        self.valeur_recue: str = valeur_recue
        super().__init__(
            f"Niveau de confiance invalide : {valeur_recue!r}. Valeurs autorisées : 'A', 'B', 'C'."
        )


class JustificationRequise(EditorialeError):  # noqa: N818
    """Justification éditoriale manquante là où elle est requise.

    Levée typiquement par ``overrider_niveau_confiance`` quand le caller
    appose un override sur le niveau de confiance sans fournir de
    justification dans ``commentaire_editorial``.
    """

    def __init__(self, operation: str) -> None:
        self.operation: str = operation
        super().__init__(f"Justification éditoriale requise pour l'opération {operation!r}.")
