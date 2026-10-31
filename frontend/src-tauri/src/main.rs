// Empêche l'ouverture d'une console Windows en plus de la fenêtre (release).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

//! Coquille desktop d'Opportune (OPP-192).
//!
//! Tauri ne porte aucune logique métier : il lance le binaire API (`opportune-api`,
//! OPP-190) en **sidecar**, attend qu'il serve le front compilé (OPP-191) sur
//! `127.0.0.1:8000`, ouvre une fenêtre dessus, puis **arrête le sidecar** à la sortie.
//! Front et données viennent du même origin (le sidecar) : aucun CORS.
//!
//! Arrêt du sidecar — le point délicat. Le binaire API est un onefile PyInstaller :
//! il tourne en **deux** processus (un bootloader + le vrai process Python, petit-fils,
//! qui tient le port). Tuer le seul bootloader laisserait le process Python orphelin à
//! retenir `8000`, et le lancement suivant échouerait. On lance donc le sidecar dans son
//! **propre groupe de processus** (`setsid`) et on tue le **groupe entier** à la sortie.

use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use tauri::{RunEvent, WebviewUrl, WebviewWindowBuilder};

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

/// Poignée **globale** du sidecar, atteignable depuis les trois chemins d'arrêt : fermeture
/// de fenêtre (`RunEvent::ExitRequested`), signal (SIGINT/SIGTERM via `ctrlc`) et filet de fin
/// de `main`. `take()` garantit qu'un seul l'emporte.
static SIDECAR: OnceLock<Mutex<Option<Child>>> = OnceLock::new();

fn sidecar_slot() -> &'static Mutex<Option<Child>> {
    SIDECAR.get_or_init(|| Mutex::new(None))
}

/// Chemin du binaire sidecar : à côté de l'exécutable courant. Tauri y copie l'`externalBin`
/// (sans le suffixe de triple) aussi bien en dev (`target/debug/`) qu'une fois empaqueté.
fn sidecar_path() -> PathBuf {
    let mut path = std::env::current_exe().expect("exécutable courant introuvable");
    path.pop();
    path.push(if cfg!(windows) { "opportune-api.exe" } else { "opportune-api" });
    path
}

/// Lance le sidecar. Sous Unix, dans un nouveau groupe de processus (`setsid`) pour pouvoir
/// tuer tout l'arbre (bootloader + process Python) d'un seul signal au groupe.
fn spawn_sidecar() -> std::io::Result<Child> {
    let mut command = Command::new(sidecar_path());
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

/// Arrête le sidecar s'il tourne encore (idempotent). Sous Unix, SIGTERM au **groupe** entier
/// (`kill(-pgid)`) : atteint le bootloader ET le process Python. Ailleurs, `kill` du process.
///
/// Après le SIGTERM, on laisse ~5 s au groupe pour s'arrêter proprement (flush SQLite, etc.),
/// puis on **force avec SIGKILL** : sinon un sidecar lent ou bloqué (requête LLM/scrape en cours
/// qui ignore SIGTERM) ferait pendre `wait()` indéfiniment et la fenêtre ne se fermerait jamais.
fn kill_sidecar() {
    if let Some(mut child) = sidecar_slot().lock().unwrap().take() {
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
                    Ok(Some(_)) => break, // le bootloader s'est arrêté
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
}

/// Attend que le sidecar accepte une connexion TCP sur `addr`, jusqu'à `timeout`.
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
    // Arrêt par signal (kill, Ctrl+C) : on tue le sidecar avant de sortir, pour ne pas laisser
    // le process API orphelin. La fermeture de fenêtre, elle, passe par ExitRequested plus bas.
    let _ = ctrlc::set_handler(|| {
        kill_sidecar();
        std::process::exit(0);
    });

    tauri::Builder::default()
        .setup(|app| {
            // Message explicite si le binaire sidecar est absent (sync-sidecar.sh pas lancé) :
            // sans ça, l'échec remonte en panic brute « échec de l'initialisation de Tauri ».
            let child = spawn_sidecar().map_err(|e| {
                format!("Impossible de lancer le service Opportune ({e}). Lance d'abord sync-sidecar.sh.")
            })?;
            sidecar_slot().lock().unwrap().replace(child);

            // L'attente de disponibilité tourne dans un **thread de fond** : la bloquer ici gèlerait
            // la boucle d'événements (sur macOS l'app apparaîtrait « ne répond pas » jusqu'à 20 s).
            // On n'ouvre la fenêtre qu'une fois le sidecar prêt — sinon la webview afficherait une
            // erreur de connexion avant que l'API réponde. 20 s couvrent le premier démarrage
            // (création + seed des bases). En cas d'échec, on **tue le sidecar** avant de quitter,
            // pour ne pas laisser le process API orphelin tenir le port (prochain lancement cassé).
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                let ready = wait_until_ready(&api_addr(), Duration::from_secs(20));
                let ui = handle.clone();
                let _ = handle.run_on_main_thread(move || {
                    if !ready {
                        eprintln!("Le service Opportune n'a pas démarré dans le délai imparti.");
                        kill_sidecar();
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
                        kill_sidecar();
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
                kill_sidecar();
            }
        });

    // Filet : si la boucle rend la main autrement, on s'assure que le sidecar est arrêté.
    kill_sidecar();
}
