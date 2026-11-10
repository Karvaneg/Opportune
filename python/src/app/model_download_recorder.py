"""Note un modèle qu'Opportune vient de télécharger (OPP-251, OPP-252).

Appelé par :class:`app.llm_setup_service.LLMSetupService` après un téléchargement réussi.
Assemble ce que :class:`app.model_origin.ModelOriginStore` doit retenir : le nom du modèle avec
son tag, le dossier de modèles donné par la coquille de bureau, et l'empreinte de la copie lue
dans l'inventaire d'Ollama.
"""

from __future__ import annotations

from typing import Callable, Mapping

from app.model_origin import ModelOriginStore, models_dir_from_env
from app.ollama_provision import OllamaUnreachable, model_modified_at, model_with_tag


def make_download_recorder(
    store: ModelOriginStore,
    *,
    host: str,
    environ: Mapping[str, str] | None = None,
    modified_at: Callable[..., str | None] = model_modified_at,
) -> Callable[[str], None]:
    """Fabrique le rappel ``on_downloaded(model)`` du service de mise en route."""

    def record(model: str) -> None:
        tagged = model_with_tag(model)
        try:
            fingerprint = modified_at(tagged, host=host) or None
        except OllamaUnreachable:
            # Sans empreinte, cette copie ne sera jamais supprimée à travers l'Ollama de la
            # personne : c'est le choix sans risque.
            fingerprint = None
        store.mark_downloaded(tagged, models_dir_from_env(environ), fingerprint)

    return record
