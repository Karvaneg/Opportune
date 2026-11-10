//! Décisions de démarrage d'Ollama (OPP-251), en fonctions **pures**.
//!
//! Objectif : ne pas surcharger la machine. Si la personne a déjà un Ollama utilisable, on le
//! réutilise ; si elle a déjà le modèle sur son disque, on ne le retélécharge pas. Ce module ne
//! fait ni réseau ni lecture de disque : `main.rs` sonde les adresses et les dossiers, puis
//! passe ce qu'il a observé aux fonctions d'ici, qui décident. Elles se testent donc seules.

use std::path::PathBuf;

/// Adresse par défaut d'Ollama (défaut du back : `app.llm.DEFAULT_OLLAMA_HOST`).
pub const DEFAULT_ADDR: &str = "127.0.0.1:11434";

/// Port d'écoute par défaut d'Ollama, sous-entendu quand `OLLAMA_HOST` n'en donne pas.
const DEFAULT_PORT: u16 = 11434;

/// Modèle par défaut du back (`app.llm.DEFAULT_MODEL`), surchargé par `OLLAMA_MODEL`.
pub const DEFAULT_MODEL: &str = "ministral-3:3b";

/// Version minimale d'Ollama exigée par `ministral-3` (cf. ollama.com/library/ministral-3).
/// En dessous, l'analyse des offres échoue : on ne réutilise pas cet Ollama.
pub const MIN_VERSION: Version = (0, 13, 1);

/// Version d'Ollama : (majeure, mineure, correctif). Les tuples se comparent dans cet ordre.
pub type Version = (u32, u32, u32);

/// Ce qu'on a observé en sondant une adresse.
#[derive(Debug, Clone, PartialEq)]
pub enum Probe {
    /// Rien n'écoute à cette adresse (ou elle est injoignable).
    Absent,
    /// Un service écoute, mais ce n'est pas Ollama.
    NotOllama,
    /// Un Ollama répond, avec sa version.
    Ollama(Version),
}

/// Ce que l'app doit faire au démarrage.
#[derive(Debug, Clone, PartialEq)]
pub enum Decision {
    /// Réutiliser l'Ollama qui répond à cette adresse, sans lancer le nôtre.
    Reuse(String),
    /// Lancer l'Ollama embarqué. `default_port_free` dit si `DEFAULT_ADDR` est libre ; sinon
    /// il faut lui choisir un autre port.
    Embedded { default_port_free: bool },
}

/// Transforme une valeur d'`OLLAMA_HOST` en adresse `hôte:port` joignable par un client.
///
/// `OLLAMA_HOST` suit la convention d'Ollama : scheme et port facultatifs, et souvent une
/// adresse de bind (`0.0.0.0`) qu'un client ne peut pas viser telle quelle. Rend `None` pour une
/// valeur vide ou en `https` (la sonde de `main.rs` parle HTTP en clair uniquement).
pub fn client_addr(raw: &str) -> Option<String> {
    let trimmed = raw.trim();
    if trimmed.is_empty() || trimmed.starts_with("https://") {
        return None;
    }
    let without_scheme = trimmed.strip_prefix("http://").unwrap_or(trimmed);
    // On ne garde que `hôte[:port]` : un éventuel chemin (`/`, `/api`) est ignoré.
    let authority = without_scheme.split('/').next().unwrap_or("");

    let (host, port) = split_host_port(authority);
    let host = match host {
        // Adresses de bind « toutes interfaces » ou hôte omis (`:11435`) : le client vise la
        // boucle locale.
        "" | "0.0.0.0" | "::" | "[::]" => "127.0.0.1".to_string(),
        // IPv6 nue : les crochets sont obligatoires devant un port.
        h if h.contains(':') && !h.starts_with('[') => format!("[{h}]"),
        h => h.to_string(),
    };
    Some(format!("{host}:{}", port.unwrap_or(DEFAULT_PORT)))
}

/// Sépare `hôte[:port]`. Gère l'IPv6 entre crochets (`[::1]:11434`) et l'IPv6 nue (`::1`), où
/// les deux-points font partie de l'adresse et non d'un port.
fn split_host_port(authority: &str) -> (&str, Option<u16>) {
    if let Some(end) = authority.find(']') {
        let host = &authority[..=end];
        let port = authority[end + 1..].strip_prefix(':').and_then(|p| p.parse().ok());
        return (host, port);
    }
    if authority.matches(':').count() == 1 {
        let (host, port) = authority.split_once(':').unwrap_or((authority, ""));
        return (host, port.parse().ok());
    }
    (authority, None)
}

/// Adresses à sonder, dans l'ordre de préférence : celle de l'`OLLAMA_HOST` de la personne
/// (son Ollama peut écouter sur un autre port), puis l'adresse par défaut. Sans doublon.
pub fn candidate_addrs(user_ollama_host: Option<&str>) -> Vec<String> {
    let mut addrs: Vec<String> = Vec::new();
    if let Some(addr) = user_ollama_host.and_then(client_addr) {
        addrs.push(addr);
    }
    if !addrs.iter().any(|a| a == DEFAULT_ADDR) {
        addrs.push(DEFAULT_ADDR.to_string());
    }
    addrs
}

/// Corps d'une réponse HTTP brute (ce qui suit la ligne vide après les en-têtes).
pub fn http_body(response: &str) -> Option<&str> {
    response.split_once("\r\n\r\n").map(|(_, body)| body)
}

/// Lit la version dans le **corps** de la réponse de `/api/version` (`{"version":"0.13.1"}`).
///
/// Un suffixe de pré-version (`0.13.1-rc1`) est ignoré. Rend `None` si le corps n'est pas un
/// objet JSON, ou si le champ est absent ou illisible : l'appelant considère alors que le
/// service n'est pas un Ollama.
pub fn parse_version(body: &str) -> Option<Version> {
    if !body.trim_start().starts_with('{') {
        return None;
    }
    let after_key = body.split("\"version\"").nth(1)?;
    let value = after_key.split('"').nth(1)?;

    let mut numbers = value.split('.').map(|part| {
        let digits: String = part.chars().take_while(|c| c.is_ascii_digit()).collect();
        digits.parse::<u32>().ok()
    });
    let major = numbers.next()??;
    let minor = numbers.next()??;
    let patch = numbers.next().flatten().unwrap_or(0);
    Some((major, minor, patch))
}

/// Vrai si cette version d'Ollama sait faire tourner le modèle (`>= MIN_VERSION`).
pub fn version_is_supported(version: Version) -> bool {
    version >= MIN_VERSION
}

/// Nom du modèle avec son tag : Ollama sous-entend `:latest` quand il n'y en a pas.
pub fn model_with_tag(model: &str) -> String {
    match model.rsplit_once(':') {
        // Un `:` suivi d'un `/` appartient au registre (`hôte:port/nom`), pas à un tag.
        Some((_, tag)) if !tag.contains('/') => model.to_string(),
        _ => format!("{model}:latest"),
    }
}

/// Vrai si le corps de la réponse de `/api/tags` (inventaire d'un Ollama) cite ce modèle.
/// Ollama liste toujours les noms avec leur tag : on compare donc le nom complété.
pub fn tags_list_model(body: &str, model: &str) -> bool {
    body.contains(&format!("\"{}\"", model_with_tag(model)))
}

/// Décide quoi faire à partir des sondes, données dans l'ordre de préférence.
///
/// On réutilise le premier Ollama de version suffisante. Exception : si l'app a **déjà
/// téléchargé le modèle dans son propre dossier** (`app_has_model`), on ne réutilise un Ollama
/// que s'il a lui aussi le modèle (`ollama_has_model`, interrogé seulement dans ce cas). Sinon
/// il faudrait retélécharger ~3 Go dans cet Ollama, alors que le nôtre les a déjà.
///
/// Sans Ollama réutilisable (aucun, trop ancien, port tenu par un autre service), on lance
/// l'Ollama embarqué, sur le port par défaut s'il est libre.
pub fn decide(
    probes: &[(String, Probe)],
    app_has_model: bool,
    ollama_has_model: impl Fn(&str) -> bool,
) -> Decision {
    for (addr, probe) in probes {
        if let Probe::Ollama(version) = probe {
            if version_is_supported(*version) && (!app_has_model || ollama_has_model(addr)) {
                return Decision::Reuse(addr.clone());
            }
        }
    }
    let default_port_free = probes
        .iter()
        .any(|(addr, probe)| addr == DEFAULT_ADDR && *probe == Probe::Absent);
    Decision::Embedded { default_port_free }
}

/// Chemin du manifeste d'un modèle, relatif au dossier de modèles d'Ollama.
///
/// Ollama range un modèle `[registre/][espace/]nom[:tag]` sous
/// `manifests/<registre>/<espace>/<nom>/<tag>`, avec pour défauts `registry.ollama.ai`,
/// `library` et `latest`. La présence de ce fichier indique que le modèle est déjà téléchargé.
pub fn manifest_relative_path(model: &str) -> PathBuf {
    let tagged = model_with_tag(model);
    let (name, tag) = tagged.rsplit_once(':').unwrap_or((model, "latest"));
    let parts: Vec<&str> = name.split('/').collect();
    let (registry, namespace, short_name) = match parts.as_slice() {
        [short_name] => ("registry.ollama.ai", "library", *short_name),
        [namespace, short_name] => ("registry.ollama.ai", *namespace, *short_name),
        [registry, namespace, short_name, ..] => (*registry, *namespace, *short_name),
        [] => ("registry.ollama.ai", "library", name),
    };
    ["manifests", registry, namespace, short_name, tag].iter().collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn probes(list: &[(&str, Probe)]) -> Vec<(String, Probe)> {
        list.iter().map(|(addr, probe)| (addr.to_string(), probe.clone())).collect()
    }

    #[test]
    fn client_addr_replaces_bind_address_and_adds_default_port() {
        let bind_address = "0.0.0.0";

        assert_eq!(client_addr(bind_address), Some("127.0.0.1:11434".to_string()));
    }

    #[test]
    fn client_addr_keeps_custom_port() {
        let bind_address_with_port = "0.0.0.0:11500";

        assert_eq!(client_addr(bind_address_with_port), Some("127.0.0.1:11500".to_string()));
    }

    #[test]
    fn client_addr_strips_http_scheme_and_path() {
        let url = "http://localhost:11500/";

        assert_eq!(client_addr(url), Some("localhost:11500".to_string()));
    }

    #[test]
    fn client_addr_handles_port_only() {
        let port_only = ":11500";

        assert_eq!(client_addr(port_only), Some("127.0.0.1:11500".to_string()));
    }

    #[test]
    fn client_addr_handles_ipv6() {
        let bracketed = "[::1]:11500";
        let bare = "::1";

        assert_eq!(client_addr(bracketed), Some("[::1]:11500".to_string()));
        assert_eq!(client_addr(bare), Some("[::1]:11434".to_string()));
    }

    #[test]
    fn client_addr_rejects_empty_and_https() {
        let empty = "  ";
        let https_url = "https://ollama.example.com";

        assert_eq!(client_addr(empty), None);
        assert_eq!(client_addr(https_url), None);
    }

    #[test]
    fn candidate_addrs_puts_user_host_before_default() {
        let user_ollama_host = Some("127.0.0.1:11500");

        assert_eq!(
            candidate_addrs(user_ollama_host),
            vec!["127.0.0.1:11500".to_string(), DEFAULT_ADDR.to_string()]
        );
    }

    #[test]
    fn candidate_addrs_has_no_duplicate_when_user_host_is_default() {
        let user_ollama_host = Some("0.0.0.0");

        assert_eq!(candidate_addrs(user_ollama_host), vec![DEFAULT_ADDR.to_string()]);
    }

    #[test]
    fn candidate_addrs_without_user_host_is_default_only() {
        let no_user_host = None;

        assert_eq!(candidate_addrs(no_user_host), vec![DEFAULT_ADDR.to_string()]);
    }

    #[test]
    fn http_body_is_what_follows_the_headers() {
        let response = "HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n{\"version\":\"0.13.1\"}";

        assert_eq!(http_body(response), Some("{\"version\":\"0.13.1\"}"));
    }

    #[test]
    fn http_body_is_none_without_header_separator() {
        let not_http = "SSH-2.0-OpenSSH_9.6\r\n";

        assert_eq!(http_body(not_http), None);
    }

    #[test]
    fn parse_version_reads_version_from_body() {
        let body = "{\"version\":\"0.13.1\"}";

        assert_eq!(parse_version(body), Some((0, 13, 1)));
    }

    #[test]
    fn parse_version_ignores_prerelease_suffix() {
        let body = "{\"version\": \"0.13.1-rc1\"}";

        assert_eq!(parse_version(body), Some((0, 13, 1)));
    }

    #[test]
    fn parse_version_is_none_when_missing_or_unreadable() {
        let without_version = "{\"status\":\"ok\"}";
        let unreadable_version = "{\"version\":\"dev\"}";
        let not_a_json_object = "<html>\"version\":\"1.2.0\"</html>";

        assert_eq!(parse_version(without_version), None);
        assert_eq!(parse_version(unreadable_version), None);
        assert_eq!(parse_version(not_a_json_object), None);
    }

    #[test]
    fn version_is_supported_from_minimum_upwards() {
        let minimum = (0, 13, 1);
        let newer = (0, 40, 13);
        let older = (0, 13, 0);
        let much_older = (0, 5, 0);

        assert!(version_is_supported(minimum));
        assert!(version_is_supported(newer));
        assert!(!version_is_supported(older));
        assert!(!version_is_supported(much_older));
    }

    #[test]
    fn model_with_tag_adds_latest_only_when_tag_is_missing() {
        let model_without_tag = "ministral-3";
        let model_with_explicit_tag = "ministral-3:3b";
        let registry_with_port_and_no_tag = "registry.local:5000/team/custom";

        assert_eq!(model_with_tag(model_without_tag), "ministral-3:latest");
        assert_eq!(model_with_tag(model_with_explicit_tag), "ministral-3:3b");
        assert_eq!(
            model_with_tag(registry_with_port_and_no_tag),
            "registry.local:5000/team/custom:latest"
        );
    }

    #[test]
    fn tags_list_model_finds_exact_model_name() {
        let tags_body = "{\"models\":[{\"name\":\"ministral-3:3b\",\"model\":\"ministral-3:3b\"}]}";

        assert!(tags_list_model(tags_body, "ministral-3:3b"));
    }

    #[test]
    fn tags_list_model_matches_untagged_model_with_latest() {
        let tags_body = "{\"models\":[{\"name\":\"ministral-3:latest\"}]}";

        assert!(tags_list_model(tags_body, "ministral-3"));
    }

    #[test]
    fn tags_list_model_rejects_other_tag_and_longer_name() {
        let tags_body = "{\"models\":[{\"name\":\"ministral-3:8b\"},{\"name\":\"ministral-3:3b-q4\"}]}";

        assert!(!tags_list_model(tags_body, "ministral-3:3b"));
    }

    #[test]
    fn decide_reuses_recent_ollama_on_default_port() {
        let recent_ollama_on_default = probes(&[(DEFAULT_ADDR, Probe::Ollama((0, 20, 0)))]);

        assert_eq!(
            decide(&recent_ollama_on_default, false, |_| false),
            Decision::Reuse(DEFAULT_ADDR.to_string())
        );
    }

    #[test]
    fn decide_reuses_ollama_on_user_port_first() {
        let ollama_on_user_port = probes(&[
            ("127.0.0.1:11500", Probe::Ollama((0, 20, 0))),
            (DEFAULT_ADDR, Probe::Absent),
        ]);

        assert_eq!(
            decide(&ollama_on_user_port, false, |_| false),
            Decision::Reuse("127.0.0.1:11500".to_string())
        );
    }

    #[test]
    fn decide_launches_embedded_on_default_port_when_nothing_listens() {
        let nothing_listening = probes(&[(DEFAULT_ADDR, Probe::Absent)]);

        assert_eq!(
            decide(&nothing_listening, false, |_| false),
            Decision::Embedded { default_port_free: true }
        );
    }

    #[test]
    fn decide_launches_embedded_on_other_port_when_default_is_taken_by_another_service() {
        let other_service_on_default = probes(&[(DEFAULT_ADDR, Probe::NotOllama)]);

        assert_eq!(
            decide(&other_service_on_default, false, |_| false),
            Decision::Embedded { default_port_free: false }
        );
    }

    #[test]
    fn decide_launches_embedded_on_other_port_when_ollama_is_too_old() {
        let old_ollama_on_default = probes(&[(DEFAULT_ADDR, Probe::Ollama((0, 5, 0)))]);

        assert_eq!(
            decide(&old_ollama_on_default, false, |_| true),
            Decision::Embedded { default_port_free: false }
        );
    }

    #[test]
    fn decide_keeps_embedded_when_app_has_model_and_running_ollama_does_not() {
        let recent_ollama_without_model = probes(&[(DEFAULT_ADDR, Probe::Ollama((0, 20, 0)))]);
        let app_has_model = true;

        assert_eq!(
            decide(&recent_ollama_without_model, app_has_model, |_| false),
            Decision::Embedded { default_port_free: false }
        );
    }

    #[test]
    fn decide_reuses_ollama_when_both_app_and_ollama_have_model() {
        let recent_ollama_with_model = probes(&[(DEFAULT_ADDR, Probe::Ollama((0, 20, 0)))]);
        let app_has_model = true;

        assert_eq!(
            decide(&recent_ollama_with_model, app_has_model, |_| true),
            Decision::Reuse(DEFAULT_ADDR.to_string())
        );
    }

    #[test]
    fn manifest_relative_path_for_library_model_with_tag() {
        let model = "ministral-3:3b";

        assert_eq!(
            manifest_relative_path(model),
            PathBuf::from("manifests/registry.ollama.ai/library/ministral-3/3b")
        );
    }

    #[test]
    fn manifest_relative_path_defaults_to_latest_tag() {
        let model_without_tag = "llama3";

        assert_eq!(
            manifest_relative_path(model_without_tag),
            PathBuf::from("manifests/registry.ollama.ai/library/llama3/latest")
        );
    }

    #[test]
    fn manifest_relative_path_agrees_with_model_with_tag() {
        let model_without_tag = "ministral-3";

        assert!(manifest_relative_path(model_without_tag).ends_with("ministral-3/latest"));
    }

    #[test]
    fn manifest_relative_path_keeps_namespace_and_registry() {
        let namespaced_model = "marie/custom:v1";
        let model_on_private_registry = "registry.local:5000/team/custom:v1";

        assert_eq!(
            manifest_relative_path(namespaced_model),
            PathBuf::from("manifests/registry.ollama.ai/marie/custom/v1")
        );
        assert_eq!(
            manifest_relative_path(model_on_private_registry),
            PathBuf::from("manifests/registry.local:5000/team/custom/v1")
        );
    }
}
