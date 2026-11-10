//! Décisions de la désinstallation depuis l'app (OPP-252), en fonctions **pures**.
//!
//! L'API écrit la demande de la personne dans un fichier du dossier de données
//! (`app.uninstall_service`). `main.rs` surveille ce fichier, arrête l'API et Ollama, supprime
//! ce qui est demandé puis lance le désinstalleur du système. Ce module ne touche ni au disque
//! ni aux process : il lit la demande, reconnaît le type d'installation et dit quoi supprimer.

use std::path::{Component, Path, PathBuf};

/// Fichier de demande écrit par l'API (`app.uninstall_service.REQUEST_FILENAME`).
pub const REQUEST_FILENAME: &str = "uninstall-request.json";

/// Sous-dossier du dossier de données où l'Ollama embarqué range ses modèles.
pub const APP_MODELS_DIRNAME: &str = "ollama-models";

/// Nom du paquet Linux (`.deb` et `.rpm`), tel que Tauri le dérive du nom du produit.
pub const LINUX_PACKAGE_NAME: &str = "opportune";

/// Fichier témoin, dans le dossier de données : l'Ollama embarqué a créé `~/.ollama` (il y range
/// sa clé), le dossier n'existait pas avant Opportune.
pub const CREATED_OLLAMA_HOME_MARKER: &str = "created-ollama-home";

/// Ce que la personne a choisi de supprimer.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct UninstallRequest {
    /// Supprimer le modèle rangé dans le dossier de l'app.
    pub remove_model: bool,
    /// Supprimer les données Opportune (bases, réglages).
    pub remove_data: bool,
}

/// Lit la demande écrite par l'API : `{"remove_model": true, "remove_data": false}`.
///
/// Rend `None` si l'un des deux choix manque ou n'est pas un booléen : une suppression étant
/// irréversible, on n'applique aucune valeur par défaut et on ignore la demande.
pub fn parse_request(content: &str) -> Option<UninstallRequest> {
    Some(UninstallRequest {
        remove_model: json_bool(content, "remove_model")?,
        remove_data: json_bool(content, "remove_data")?,
    })
}

/// Valeur d'un champ booléen dans un objet JSON à plat (pas d'objet imbriqué).
fn json_bool(content: &str, key: &str) -> Option<bool> {
    let after_key = content.split(&format!("\"{key}\"")).nth(1)?;
    let value = after_key.trim_start().strip_prefix(':')?.trim_start();
    if value.starts_with("true") {
        Some(true)
    } else if value.starts_with("false") {
        Some(false)
    } else {
        None
    }
}

/// Ce qu'on observe de l'installation en cours, pour en reconnaître le type.
#[derive(Debug, Clone, Default)]
pub struct InstallFacts {
    /// Système : `"linux"`, `"windows"` ou `"macos"` (`std::env::consts::OS`).
    pub os: String,
    /// Chemin de l'exécutable de l'app.
    pub exe: PathBuf,
    /// La variable `APPIMAGE` est définie (posée par le lanceur d'une AppImage).
    pub runs_from_appimage: bool,
    /// Un `uninstall.exe` existe à côté de l'exécutable (installeur NSIS, le `.exe`).
    pub nsis_uninstaller_present: bool,
    /// Le paquet `.deb` est enregistré auprès de dpkg.
    pub dpkg_knows_package: bool,
    /// La machine a une base de paquets RPM (Fedora, openSUSE, RHEL…).
    pub rpm_database_present: bool,
}

/// Type d'installation, transmis à l'API puis au front pour adapter la marche à suivre :
/// `appimage`, `deb`, `rpm`, `linux-other` (installée sous `/usr` par un autre moyen : paquet
/// d'une autre distribution, copie à la main), `windows-nsis`, `windows-msi`, `macos`, ou `dev`
/// (app lancée depuis les sources, rien à désinstaller).
pub fn install_kind(facts: &InstallFacts) -> &'static str {
    // Un exécutable sous un dossier `target` vient d'un build local (`cargo`, `tauri dev`).
    let built_locally = facts.exe.components().any(|c| c == Component::Normal("target".as_ref()));
    match facts.os.as_str() {
        "linux" if facts.runs_from_appimage => "appimage",
        "linux" if facts.exe.starts_with("/usr") => {
            if facts.dpkg_knows_package {
                "deb"
            } else if facts.rpm_database_present {
                "rpm"
            } else {
                "linux-other"
            }
        }
        "windows" if facts.nsis_uninstaller_present => "windows-nsis",
        "windows" if !built_locally => "windows-msi",
        "macos" if !built_locally => "macos",
        _ => "dev",
    }
}

/// Vrai si `dir` est bien un dossier propre à l'app : son dernier élément est l'identifiant de
/// l'app (`com.opportune.app`). Garde-fou avant toute suppression : on n'efface jamais un dossier
/// dont le chemin aurait été mal résolu (dossier personnel, racine).
pub fn is_app_dir(dir: &Path, identifier: &str) -> bool {
    !identifier.is_empty() && dir.file_name().is_some_and(|name| name == identifier)
}

/// Vrai si `~/.ollama` ne contient que ce qu'Ollama y crée à son premier démarrage : sa clé et
/// un dossier `cache` (`entry_names` : noms des éléments du dossier). C'est le signe que seul
/// l'Ollama embarqué s'en est servi : un Ollama installé par la personne y aurait ajouté des
/// modèles ou un historique.
pub fn ollama_home_holds_only_keys(entry_names: &[String]) -> bool {
    entry_names
        .iter()
        .all(|name| matches!(name.as_str(), "id_ed25519" | "id_ed25519.pub" | "cache"))
}

/// Parmi les éléments du dossier de données, ceux à supprimer pour « supprimer mes données ».
/// Le dossier des modèles est traité à part : il n'est gardé que si la personne a choisi de
/// conserver le modèle.
pub fn data_entries_to_delete(entries: Vec<PathBuf>, keep_models: bool) -> Vec<PathBuf> {
    entries
        .into_iter()
        .filter(|entry| {
            let is_models_dir = entry.file_name().is_some_and(|name| name == APP_MODELS_DIRNAME);
            !(keep_models && is_models_dir)
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn facts(os: &str, exe: &str) -> InstallFacts {
        InstallFacts { os: os.to_string(), exe: PathBuf::from(exe), ..InstallFacts::default() }
    }

    #[test]
    fn parse_request_reads_both_choices() {
        let request_written_by_api = "{\"remove_model\": true, \"remove_data\": false}";

        assert_eq!(
            parse_request(request_written_by_api),
            Some(UninstallRequest { remove_model: true, remove_data: false })
        );
    }

    #[test]
    fn parse_request_accepts_compact_json() {
        let compact_request = "{\"remove_data\":true,\"remove_model\":false}";

        assert_eq!(
            parse_request(compact_request),
            Some(UninstallRequest { remove_model: false, remove_data: true })
        );
    }

    #[test]
    fn parse_request_is_none_when_a_choice_is_missing() {
        let request_without_data_choice = "{\"remove_model\": true}";

        assert_eq!(parse_request(request_without_data_choice), None);
    }

    #[test]
    fn parse_request_is_none_when_a_choice_is_not_a_boolean() {
        let request_with_text_choice = "{\"remove_model\": \"true\", \"remove_data\": false}";
        let empty_file = "";

        assert_eq!(parse_request(request_with_text_choice), None);
        assert_eq!(parse_request(empty_file), None);
    }

    #[test]
    fn install_kind_is_appimage_when_launched_from_one() {
        let appimage_facts = InstallFacts {
            runs_from_appimage: true,
            ..facts("linux", "/tmp/.mount_OpportXyz/usr/bin/opportune")
        };

        assert_eq!(install_kind(&appimage_facts), "appimage");
    }

    #[test]
    fn install_kind_is_deb_when_dpkg_knows_the_package() {
        let deb_facts = InstallFacts { dpkg_knows_package: true, ..facts("linux", "/usr/bin/opportune") };

        assert_eq!(install_kind(&deb_facts), "deb");
    }

    #[test]
    fn install_kind_is_rpm_when_installed_under_usr_on_an_rpm_system() {
        let rpm_facts = InstallFacts { rpm_database_present: true, ..facts("linux", "/usr/bin/opportune") };

        assert_eq!(install_kind(&rpm_facts), "rpm");
    }

    #[test]
    fn install_kind_is_linux_other_under_usr_without_dpkg_nor_rpm() {
        let arch_or_manual_copy_facts = facts("linux", "/usr/bin/opportune");

        assert_eq!(install_kind(&arch_or_manual_copy_facts), "linux-other");
    }

    #[test]
    fn ollama_home_with_only_keys_was_used_by_embedded_ollama_alone() {
        let only_keys =
            vec!["id_ed25519".to_string(), "id_ed25519.pub".to_string(), "cache".to_string()];
        let empty_dir: Vec<String> = vec![];

        assert!(ollama_home_holds_only_keys(&only_keys));
        assert!(ollama_home_holds_only_keys(&empty_dir));
    }

    #[test]
    fn ollama_home_with_models_or_history_belongs_to_the_user() {
        let keys_and_models = vec!["id_ed25519".to_string(), "models".to_string()];
        let keys_and_history = vec!["id_ed25519.pub".to_string(), "history".to_string()];

        assert!(!ollama_home_holds_only_keys(&keys_and_models));
        assert!(!ollama_home_holds_only_keys(&keys_and_history));
    }

    #[test]
    fn install_kind_is_dev_for_a_local_linux_build() {
        let local_build_facts = facts("linux", "/home/marie/Opportune/frontend/src-tauri/target/debug/opportune");

        assert_eq!(install_kind(&local_build_facts), "dev");
    }

    #[test]
    fn install_kind_is_windows_nsis_when_its_uninstaller_is_present() {
        let nsis_facts = InstallFacts {
            nsis_uninstaller_present: true,
            ..facts("windows", "C:\\Users\\marie\\AppData\\Local\\Opportune\\opportune.exe")
        };

        assert_eq!(install_kind(&nsis_facts), "windows-nsis");
    }

    #[test]
    fn install_kind_is_windows_msi_when_installed_without_nsis_uninstaller() {
        let msi_facts = facts("windows", "/Program Files/Opportune/opportune.exe");

        assert_eq!(install_kind(&msi_facts), "windows-msi");
    }

    #[test]
    fn install_kind_is_dev_for_a_local_windows_build() {
        let local_build_facts = facts("windows", "/opportune-winbuild/frontend/src-tauri/target/release/opportune.exe");

        assert_eq!(install_kind(&local_build_facts), "dev");
    }

    #[test]
    fn is_app_dir_requires_the_app_identifier_as_last_component() {
        let app_data_dir = Path::new("/home/marie/.local/share/com.opportune.app");
        let home_dir = Path::new("/home/marie");
        let root = Path::new("/");

        assert!(is_app_dir(app_data_dir, "com.opportune.app"));
        assert!(!is_app_dir(home_dir, "com.opportune.app"));
        assert!(!is_app_dir(root, "com.opportune.app"));
        assert!(!is_app_dir(app_data_dir, ""));
    }

    #[test]
    fn data_entries_to_delete_keeps_models_when_asked() {
        let data_dir_entries = vec![
            PathBuf::from("/data/com.opportune.app/opportune.db"),
            PathBuf::from("/data/com.opportune.app/ollama-models"),
            PathBuf::from("/data/com.opportune.app/demo"),
        ];
        let keep_models = true;

        assert_eq!(
            data_entries_to_delete(data_dir_entries, keep_models),
            vec![
                PathBuf::from("/data/com.opportune.app/opportune.db"),
                PathBuf::from("/data/com.opportune.app/demo"),
            ]
        );
    }

    #[test]
    fn data_entries_to_delete_takes_everything_when_models_go_too() {
        let data_dir_entries = vec![
            PathBuf::from("/data/com.opportune.app/opportune.db"),
            PathBuf::from("/data/com.opportune.app/ollama-models"),
        ];
        let keep_models = false;

        assert_eq!(data_entries_to_delete(data_dir_entries.clone(), keep_models), data_dir_entries);
    }
}
