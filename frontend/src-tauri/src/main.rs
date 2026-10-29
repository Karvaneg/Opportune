// Empêche l'ouverture d'une console Windows en plus de la fenêtre (release).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

//! Coquille desktop d'Opportune (OPP-192, étendue OPP-194).
//!
//! Tauri ne porte aucune logique métier : il lance **deux sidecars**, attend qu'ils
//! répondent, ouvre une fenêtre sur le front servi par l'API, puis **arrête les sidecars**
//! à la sortie. Front et données viennent du même origin (l'API) : aucun CORS.
//!
//! - **Ollama** (OPP-194) : le moteur LLM local, servi sur `127.0.0.1:11434`. On l'embarque
//!   en version CPU seule (cf. `sync-ollama.sh`) et on le démarre en tâche de fond. Si un
//!   Ollama tourne déjà sur ce port (machine de dev, utilisateur qui en a un), on le réutilise
//!   au lieu d'en lancer un second. Le téléchargement du modèle reste géré côté front/API
//!   (flux OPP-193, `/system/llm/*`).
//! - **API** (`opportune-api`, OPP-190) : sert le front compilé (OPP-191) sur `127.0.0.1:8000`.
//!
//! Arrêt des sidecars — le point délicat. Le binaire API est un onefile PyInstaller : il tourne
//! en **deux** processus (un bootloader + le vrai process Python, petit-fils, qui tient le port).
//! Tuer le seul bootloader laisserait le process Python orphelin à retenir `8000`, et le
//! lancement suivant échouerait. On lance donc **chaque** sidecar dans son **propre groupe de
//! processus** (`setsid`) et on tue le **groupe entier** à la sortie.

use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use tauri::path::BaseDirectory;
use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};

/// Port d'écoute du sidecar (front + API), depuis `OPPORTUNE_API_PORT` (défaut 8000). La **même**
/// variable pilote le port côté Python (`api.server.resolve_api_port`) ; le sidecar en hérite via
/// l'environnement de ce process, donc un port occupé se règle à un seul endroit pour toute l'app.
fn api_port() -> u16 {
    std::env::var("OPPORTUNE_API_PORT")
        .ok()
        .and_then(|raw| raw.trim().parse::<u16>().ok())
        .filter(|&port| port != 0)
        .unwrap_or(8000)
}

/// Adresse TCP où sonder la disponibilité du sidecar (`127.0.0.1:<port>`).
fn api_addr() -> String {
    format!("127.0.0.1:{}", api_port())
}

/// URL chargée dans la fenêtre une fois le sidecar prêt (`http://127.0.0.1:<port>/`).
fn api_url() -> String {
    format!("http://127.0.0.1:{}/", api_port())
}

/// Hôte/port où Ollama écoute (défaut du back : `app.llm.DEFAULT_OLLAMA_HOST`).
const OLLAMA_ADDR: &str = "127.0.0.1:11434";

/// Sidecars **globaux**, atteignables depuis les trois chemins d'arrêt : fermeture de fenêtre
/// (`RunEvent::ExitRequested`), signal (SIGINT/SIGTERM via `ctrlc`) et filet de fin de `main`.
/// `take()`/drain garantit qu'un seul chemin les emporte.
static CHILDREN: OnceLock<Mutex<Vec<Child>>> = OnceLock::new();

fn children() -> &'static Mutex<Vec<Child>> {
    CHILDREN.get_or_init(|| Mutex::new(Vec::new()))
}

/// Enregistre un sidecar lancé pour qu'il soit arrêté avec l'app.
fn register_child(child: Child) {
    children().lock().unwrap().push(child);
}

/// Chemin du binaire API : à côté de l'exécutable courant. Tauri y copie l'`externalBin`
/// (sans le suffixe de triple) aussi bien en dev (`target/debug/`) qu'une fois empaqueté.
fn api_path() -> PathBuf {
    let mut path = std::env::current_exe().expect("exécutable courant introuvable");
    path.pop();
    path.push(if cfg!(windows) { "opportune-api.exe" } else { "opportune-api" });
    path
}

/// Localise l'arbre Ollama embarqué et renvoie `(binaire, dossier des runners)`.
///
/// On essaie dans l'ordre : surcharge explicite, dossier de ressources de l'app empaquetée,
/// puis emplacements de dev. Pour chaque arbre candidat, on reconnaît **deux dispositions** du
/// binaire : `<arbre>/bin/ollama` (release Linux, cf. `sync-ollama.sh`) et `<arbre>/ollama.exe`
/// à la racine (archive Windows officielle). Dans les deux cas les runners sont sous
/// `<arbre>/lib/ollama` — le dossier est donc dérivé de l'arbre, jamais du binaire.
fn ollama_paths(app: &tauri::AppHandle) -> Option<(PathBuf, PathBuf)> {
    let exe_name = if cfg!(windows) { "ollama.exe" } else { "ollama" };

    let mut candidates: Vec<PathBuf> = Vec::new();

    // 1. Surcharge explicite (tests, dev avancé) : OPPORTUNE_OLLAMA_DIR pointe sur l'arbre.
    if let Ok(dir) = std::env::var("OPPORTUNE_OLLAMA_DIR") {
        candidates.push(PathBuf::from(dir));
    }
    // 2. App empaquetée : les ressources sont sous resource_dir()/ollama (cf. tauri.conf.json).
    if let Ok(res) = app.path().resolve("ollama", BaseDirectory::Resource) {
        candidates.push(res);
    }
    // 3. Dev : l'arbre déposé par sync-ollama.sh dans src-tauri/binaries/ollama. L'exe de dev est
    //    à src-tauri/target/<profil>/ ; binaries/ollama est donc deux niveaux au-dessus.
    if let Ok(mut exe) = std::env::current_exe() {
        exe.pop(); // target/<profil>/
        exe.pop(); // target/
        exe.pop(); // src-tauri/
        exe.push("binaries/ollama");
        candidates.push(exe);
    }

    for dir in candidates {
        // Linux : `<arbre>/bin/ollama` ; Windows (zip officiel) : `<arbre>/ollama.exe`.
        for bin in [dir.join("bin").join(exe_name), dir.join(exe_name)] {
            if bin.exists() {
                return Some((bin, dir.join("lib").join("ollama")));
            }
        }
    }
    None
}

/// Lance une commande comme sidecar. Sous Unix, dans un nouveau groupe de processus (`setsid`)
/// pour pouvoir tuer tout l'arbre (bootloader + process enfants) d'un seul signal au groupe.
fn spawn_in_group(mut command: Command) -> std::io::Result<Child> {
    #[cfg(unix)]
    unsafe {
        use std::os::unix::process::CommandExt;
        command.pre_exec(|| {
            // Nouveau groupe/session : le sidecar devient chef de groupe, pgid == pid.
            if libc::setsid() == -1 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }
    command.spawn()
}

/// Démarre Ollama en sidecar, sauf si un serveur répond déjà sur `OLLAMA_ADDR` (on le réutilise
/// alors). Quand on lance **notre** process, les modèles sont rangés dans le dossier de données
/// de l'app (`OLLAMA_MODELS`) : supprimés avec l'app, sans toucher au `~/.ollama` de l'utilisateur.
/// En revanche, si on **réutilise** un Ollama déjà en écoute, les modèles suivent la configuration
/// de *ce* serveur (typiquement son propre `~/.ollama`) : on ne contrôle pas son `OLLAMA_MODELS`.
/// Renvoie `Ok(true)` si on a bien lancé notre propre process (à arrêter à la sortie).
fn spawn_ollama(app: &tauri::AppHandle) -> std::io::Result<bool> {
    // Un Ollama déjà en écoute (dev, utilisateur équipé) : ne pas en lancer un second.
    if TcpStream::connect(OLLAMA_ADDR).is_ok() {
        return Ok(false);
    }

    let Some((bin, lib_dir)) = ollama_paths(app) else {
        // Pas d'arbre embarqué (sync-ollama.sh pas lancé en dev). On ne bloque pas le démarrage :
        // le front signalera l'absence de moteur via /system/llm/status (flux OPP-193).
        eprintln!("Ollama embarqué introuvable : moteur LLM indisponible (lance sync-ollama.sh).");
        return Ok(false);
    };

    let models_dir = app
        .path()
        .app_data_dir()
        .map(|d| d.join("ollama-models"))
        .unwrap_or_else(|_| PathBuf::from("ollama-models"));
    let _ = std::fs::create_dir_all(&models_dir);

    let mut command = Command::new(&bin);
    command.arg("serve");
    command.env("OLLAMA_HOST", OLLAMA_ADDR);
    command.env("OLLAMA_MODELS", &models_dir);
    // Où le binaire trouve ses runners : le `lib/ollama` voisin suffit (résolution relative à
    // l'exe), mais on le pose aussi explicitement pour les versions qui lisent cette variable.
    command.env("OLLAMA_LIBRARY_PATH", &lib_dir);

    let child = spawn_in_group(command)?;
    register_child(child);
    Ok(true)
}

/// Démarre l'API en sidecar (dans son propre groupe de processus).
///
/// On lui impose `OPPORTUNE_DATA_DIR` = dossier de données de l'app : les bases SQLite de l'API
/// vivent ainsi dans la **même** arborescence que les modèles Ollama (`OLLAMA_MODELS`), au lieu
/// du dossier par défaut de `app.paths`. Une seule arborescence à sauvegarder/supprimer.
fn spawn_api(app: &tauri::AppHandle) -> std::io::Result<()> {
    let mut command = Command::new(api_path());
    if let Ok(data_dir) = app.path().app_data_dir() {
        command.env("OPPORTUNE_DATA_DIR", &data_dir);
    }
    // On vise toujours l'Ollama local sur `OLLAMA_ADDR` (sidecar embarqué, ou instance déjà en
    // écoute sur ce port que `spawn_ollama` réutilise). Sans ça, l'API hériterait du `OLLAMA_HOST`
    // ambiant de l'utilisateur — souvent une adresse de bind (`0.0.0.0`, sans port) posée pour son
    // propre Ollama —, et taperait à côté du moteur de l'app. (Le back ajoute le `http://` manquant.)
    command.env("OLLAMA_HOST", OLLAMA_ADDR);
    let child = spawn_in_group(command)?;
    register_child(child);
    Ok(())
}

/// Arrête un sidecar. Sous Unix, SIGTERM au **groupe** entier (`kill(-pgid)`) : atteint le
/// bootloader ET les process enfants. Ailleurs, `kill` du process.
///
/// Après le SIGTERM, on laisse ~5 s au groupe pour s'arrêter proprement (flush SQLite, etc.),
/// puis on **force avec SIGKILL** : sinon un sidecar lent ou bloqué (requête LLM/scrape en cours
/// qui ignore SIGTERM) ferait pendre `wait()` indéfiniment et la fenêtre ne se fermerait jamais.
fn kill_child(mut child: Child) {
    #[cfg(unix)]
    {
        // Le sidecar est chef de son groupe (setsid), donc pgid == child.id().
        let pgid = child.id() as i32;
        unsafe {
            libc::kill(-pgid, libc::SIGTERM);
        }
        let deadline = Instant::now() + Duration::from_secs(5);
        loop {
            match child.try_wait() {
                Ok(Some(_)) => break, // le process s'est arrêté
                Ok(None) if Instant::now() >= deadline => {
                    unsafe {
                        libc::kill(-pgid, libc::SIGKILL);
                    }
                    let _ = child.wait();
                    break;
                }
                Ok(None) => std::thread::sleep(Duration::from_millis(100)),
                Err(_) => break,
            }
        }
    }
    #[cfg(not(unix))]
    {
        let _ = child.kill();
        let _ = child.wait();
    }
}

/// Arrête tous les sidecars encore en vie (idempotent). `drain` garantit qu'un seul chemin
/// d'arrêt les emporte, même si deux se déclenchent (fermeture + signal).
fn kill_all() {
    let drained: Vec<Child> = children().lock().unwrap().drain(..).collect();
    for child in drained {
        kill_child(child);
    }
}

/// Attend que l'adresse `addr` accepte une connexion TCP, jusqu'à `timeout`.
/// Vrai dès que le port répond ; faux si le délai expire (sidecar en panne).
fn wait_until_ready(addr: &str, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if TcpStream::connect(addr).is_ok() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    false
}

fn main() {
    // Arrêt par signal (kill, Ctrl+C) : on tue les sidecars avant de sortir, pour ne pas laisser
    // de process orphelin. La fermeture de fenêtre, elle, passe par ExitRequested plus bas.
    let _ = ctrlc::set_handler(|| {
        kill_all();
        std::process::exit(0);
    });

    tauri::Builder::default()
        .setup(|app| {
            let handle = app.handle().clone();

            // Ollama d'abord (ne bloque pas : juste le lancement du process). Le back ne se
            // connecte à Ollama qu'à la première requête LLM, donc pas besoin d'attendre qu'il
            // soit prêt pour démarrer l'API. La disponibilité du moteur est surveillée côté front
            // (LlmSetupGate, /system/llm/status — OPP-193).
            if let Err(e) = spawn_ollama(&handle) {
                eprintln!("Échec du démarrage d'Ollama : {e}");
            }

            // Message explicite si le binaire API est absent (sync-sidecar.sh pas lancé) : sans ça,
            // l'échec remonte en panic brute « échec de l'initialisation de Tauri ».
            spawn_api(&handle).map_err(|e| {
                format!("Impossible de lancer le service Opportune ({e}). Lance d'abord sync-sidecar.sh.")
            })?;

            // L'attente de disponibilité tourne dans un **thread de fond** : la bloquer ici gèlerait
            // la boucle d'événements (sur macOS l'app apparaîtrait « ne répond pas » jusqu'à 20 s).
            // On n'ouvre la fenêtre qu'une fois l'API prête — sinon la webview afficherait une
            // erreur de connexion avant qu'elle réponde. 20 s couvrent le premier démarrage
            // (création + seed des bases). En cas d'échec, on **tue les sidecars** avant de quitter,
            // pour ne pas laisser de process orphelin tenir un port (prochain lancement cassé).
            std::thread::spawn(move || {
                let ready = wait_until_ready(&api_addr(), Duration::from_secs(20));
                let ui = handle.clone();
                let _ = handle.run_on_main_thread(move || {
                    if !ready {
                        eprintln!("Le service Opportune n'a pas démarré dans le délai imparti.");
                        kill_all();
                        ui.exit(1);
                        return;
                    }
                    let opened = WebviewWindowBuilder::new(
                        &ui,
                        "main",
                        WebviewUrl::External(api_url().parse().unwrap()),
                    )
                    .title("Opportune")
                    .inner_size(1280.0, 800.0)
                    .min_inner_size(960.0, 640.0)
                    .build();
                    if opened.is_err() {
                        kill_all();
                        ui.exit(1);
                    }
                });
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("échec de l'initialisation de Tauri")
        .run(|_app_handle, event| {
            // Arrêt propre à la fermeture de la fenêtre (dernière fenêtre fermée).
            if let RunEvent::ExitRequested { .. } = event {
                kill_all();
            }
        });

    // Filet : si la boucle rend la main autrement, on s'assure que les sidecars sont arrêtés.
    kill_all();
}
