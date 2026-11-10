// Empêche l'ouverture d'une console Windows en plus de la fenêtre (release).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

//! Coquille desktop d'Opportune (OPP-192, étendue OPP-194).
//!
//! Tauri ne porte aucune logique métier : il lance **deux sidecars**, attend qu'ils
//! répondent, ouvre une fenêtre sur le front servi par l'API, puis **arrête les sidecars**
//! à la sortie. Front et données viennent du même origin (l'API) : aucun CORS.
//!
//! - **Ollama** (OPP-194, OPP-251) : le moteur LLM local. On l'embarque en version CPU seule
//!   (cf. `sync-ollama.sh`). Pour ne pas surcharger la machine, on **réutilise** l'Ollama de la
//!   personne s'il répond (sur `127.0.0.1:11434` ou à l'adresse de son `OLLAMA_HOST`) et que sa
//!   version suffit. Sinon on lance le nôtre, sur un autre port si `11434` est pris, et sur les
//!   modèles de la personne si elle a déjà le bon. Les décisions sont dans `ollama_plan.rs` ;
//!   le téléchargement du modèle reste géré côté front/API (flux OPP-193, `/system/llm/*`).
//! - **API** (`opportune-api`, OPP-190) : sert le front compilé (OPP-191) sur `127.0.0.1:8000`.
//!
//! Arrêt des sidecars — le point délicat. Le binaire API est un onefile PyInstaller : il tourne
//! en **deux** processus (un bootloader + le vrai process Python, petit-fils, qui tient le port).
//! Tuer le seul bootloader laisserait le process Python orphelin à retenir `8000`, et le
//! lancement suivant échouerait. On lance donc **chaque** sidecar dans son **propre groupe de
//! processus** (`setsid`) et on tue le **groupe entier** à la sortie.

mod ollama_plan;

use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream, ToSocketAddrs};
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use tauri::path::BaseDirectory;
use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};

use ollama_plan::{Decision, Probe};

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
    // `CREATE_NO_WINDOW` : empêche le sidecar d'ouvrir sa propre fenêtre console à côté de l'app
    // (OPP-221) — l'API (onefile PyInstaller `console=True`) comme `ollama serve` en ouvriraient
    // une sinon. Réservé au build **release** : en debug la coquille a elle-même une console (cf.
    // `windows_subsystem` en tête), dont le sidecar hérite → ses logs restent visibles. Sans effet
    // sur l'arrêt, qui passe par `taskkill /T /F` (arbre de process, indépendant de la console).
    #[cfg(all(windows, not(debug_assertions)))]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    command.spawn()
}

/// Envoie `GET <path>` à `addr` en HTTP/1.0 et rend la réponse brute (en-têtes + corps).
///
/// `None` si **aucune connexion** n'aboutit : rien n'écoute, ou l'adresse est injoignable. On
/// essaie **toutes** les adresses que donne la résolution du nom : `localhost` peut donner
/// `::1` avant `127.0.0.1` alors qu'Ollama n'écoute que sur la seconde. Une connexion établie
/// mais muette rend une réponse vide. Timeouts courts, pour qu'un port tenu par un process
/// non-HTTP ne fasse pas traîner le démarrage ; la lecture est plafonnée à `max_bytes`.
fn http_get(addr: &str, path: &str, max_bytes: usize) -> Option<String> {
    let mut stream = addr
        .to_socket_addrs()
        .ok()?
        .find_map(|socket_addr| TcpStream::connect_timeout(&socket_addr, Duration::from_secs(1)).ok())?;
    let timeout = Some(Duration::from_secs(2));
    let _ = stream.set_read_timeout(timeout);
    let _ = stream.set_write_timeout(timeout);
    let request = format!("GET {path} HTTP/1.0\r\nHost: {addr}\r\nConnection: close\r\n\r\n");
    if stream.write_all(request.as_bytes()).is_err() {
        return Some(String::new());
    }
    // On lit **en boucle** jusqu'à la fermeture de la connexion (HTTP/1.0 + `Connection: close`) :
    // un seul `read` peut rendre un segment tronqué. Un read qui expire rompt la boucle ; on juge
    // alors sur ce qu'on a reçu.
    let mut response = Vec::with_capacity(512);
    let mut chunk = [0u8; 4096];
    while response.len() < max_bytes {
        match stream.read(&mut chunk) {
            Ok(0) | Err(_) => break,
            Ok(n) => response.extend_from_slice(&chunk[..n]),
        }
    }
    Some(String::from_utf8_lossy(&response).into_owned())
}

/// Corps de la réponse si son statut est 200, sinon `None`.
fn body_if_ok(response: &str) -> Option<&str> {
    let status_line = response.lines().next().unwrap_or("");
    if status_line.starts_with("HTTP/") && status_line.contains(" 200") {
        ollama_plan::http_body(response)
    } else {
        None
    }
}

/// Sonde `addr` : rien n'écoute, un autre service écoute, ou un Ollama répond (avec sa version).
///
/// Un Ollama se reconnaît à `/api/version` : statut 200 **et** un corps JSON portant un champ
/// `version` lisible. Un service HTTP qui imiterait exactement cette réponse serait pris pour un
/// Ollama : on ne peut pas l'exclure sans lui envoyer une vraie requête de génération.
fn probe_ollama(addr: &str) -> Probe {
    let Some(response) = http_get(addr, "/api/version", 4096) else {
        return Probe::Absent;
    };
    match body_if_ok(&response).and_then(ollama_plan::parse_version) {
        Some(version) => Probe::Ollama(version),
        None => Probe::NotOllama,
    }
}

/// Vrai si l'Ollama qui répond sur `addr` a déjà ce modèle (`/api/tags`). L'inventaire d'une
/// personne qui a beaucoup de modèles est long : la lecture est plafonnée large (4 Mo).
fn ollama_has_model(addr: &str, model: &str) -> bool {
    http_get(addr, "/api/tags", 4 * 1024 * 1024)
        .as_deref()
        .and_then(body_if_ok)
        .is_some_and(|body| ollama_plan::tags_list_model(body, model))
}

/// Sonde toutes les adresses **en parallèle** : le pire cas (service qui accepte la connexion
/// puis ne répond pas) coûte un seul délai d'attente, pas un par adresse.
fn probe_all(addrs: Vec<String>) -> Vec<(String, Probe)> {
    let handles: Vec<_> = addrs
        .into_iter()
        .map(|addr| {
            std::thread::spawn(move || {
                let probe = probe_ollama(&addr);
                (addr, probe)
            })
        })
        .collect();
    handles.into_iter().filter_map(|handle| handle.join().ok()).collect()
}

/// Demande au système un port libre sur la boucle locale. Le listener est refermé aussitôt
/// (Ollama ne sait pas reprendre un port déjà ouvert) : un autre programme peut donc prendre le
/// port avant Ollama. `spawn_ollama` couvre ce cas en réessayant sur un autre port.
fn free_local_addr() -> std::io::Result<String> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    Ok(format!("127.0.0.1:{}", listener.local_addr()?.port()))
}

/// Modèle utilisé par l'app : `OLLAMA_MODEL`, sinon le défaut du back.
fn configured_model() -> String {
    std::env::var("OLLAMA_MODEL")
        .ok()
        .map(|model| model.trim().to_string())
        .filter(|model| !model.is_empty())
        .unwrap_or_else(|| ollama_plan::DEFAULT_MODEL.to_string())
}

/// Vrai si ce dossier de modèles Ollama contient déjà le modèle (son manifeste existe).
fn dir_has_model(models_dir: &std::path::Path, model: &str) -> bool {
    models_dir.join(ollama_plan::manifest_relative_path(model)).is_file()
}

/// Dossier de modèles propre à l'app, dans son dossier de données.
fn app_models_dir(app: &tauri::AppHandle) -> PathBuf {
    app.path()
        .app_data_dir()
        .map(|d| d.join("ollama-models"))
        .unwrap_or_else(|_| PathBuf::from("ollama-models"))
}

/// Dossier de modèles Ollama **de la personne** : son `OLLAMA_MODELS` si elle en a défini un,
/// sinon `~/.ollama/models`. Limite connue : un Ollama installé comme service système sous Linux
/// range ses modèles sous `/usr/share/ollama`, que l'on ne regarde pas (dossier d'un autre compte).
fn user_models_dir(app: &tauri::AppHandle) -> Option<PathBuf> {
    match std::env::var("OLLAMA_MODELS") {
        Ok(dir) if !dir.trim().is_empty() => Some(PathBuf::from(dir)),
        _ => Some(app.path().home_dir().ok()?.join(".ollama").join("models")),
    }
}

/// Attend que l'Ollama qu'on vient de lancer (`child`) réponde sur `addr`.
///
/// - Il répond à `/api/version` : il a bien pris le port → `true`.
/// - Il s'arrête avant : le port lui a été pris par un autre programme → `false`, l'appelant
///   réessaie ailleurs.
/// - Il tourne encore à l'échéance sans avoir répondu (démarrage lent, gros dossier de modèles
///   à parcourir) : on le garde → `true`. Le front surveille ensuite sa disponibilité.
fn ollama_took_port(child: &mut Child, addr: &str, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    loop {
        if !matches!(child.try_wait(), Ok(None)) {
            return false;
        }
        if matches!(probe_ollama(addr), Probe::Ollama(_)) || Instant::now() >= deadline {
            return true;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
}

/// L'Ollama retenu pour l'app.
struct OllamaChoice {
    /// Adresse `hôte:port` où l'API doit le joindre.
    addr: String,
    /// Dossier de modèles, **quand c'est nous qui lançons Ollama**. `None` si on réutilise
    /// l'Ollama de la personne : son dossier relève de sa configuration, on ne le connaît pas.
    models_dir: Option<PathBuf>,
}

/// Adresse à donner à l'API quand **aucun** Ollama n'est utilisable. Si le port par défaut est
/// tenu par un service qu'on a écarté (autre programme, Ollama trop ancien), on ne branche pas
/// l'API dessus : on lui donne un port où rien n'écoute, pour que le front affiche « moteur
/// indisponible » au lieu d'erreurs incompréhensibles pendant l'analyse des offres.
fn unusable_ollama_addr(default_port_free: bool) -> String {
    if default_port_free {
        return ollama_plan::DEFAULT_ADDR.to_string();
    }
    free_local_addr().unwrap_or_else(|_| ollama_plan::DEFAULT_ADDR.to_string())
}

/// Choisit l'Ollama de l'app et le démarre si besoin.
///
/// 1. Si un Ollama de version suffisante répond (à l'adresse de l'`OLLAMA_HOST` de la personne,
///    puis sur le port par défaut), on le **réutilise**. Exception : si l'app a déjà téléchargé
///    le modèle dans son propre dossier et que cet Ollama ne l'a pas, on garde le nôtre, pour ne
///    pas télécharger le modèle une seconde fois.
/// 2. Sinon on lance l'Ollama **embarqué**, sur le port par défaut s'il est libre, sinon sur un
///    port libre quelconque (port tenu par un autre service, ou par un Ollama trop ancien).
///    Dossier de modèles, par ordre de préférence : celui de l'app s'il a déjà le modèle, celui
///    de la personne s'il a déjà le modèle, sinon celui de l'app (le modèle y sera téléchargé).
fn spawn_ollama(app: &tauri::AppHandle) -> OllamaChoice {
    let model = configured_model();
    let app_dir = app_models_dir(app);
    let app_has_model = dir_has_model(&app_dir, &model);

    let user_ollama_host = std::env::var("OLLAMA_HOST").ok();
    let probes = probe_all(ollama_plan::candidate_addrs(user_ollama_host.as_deref()));

    for (addr, probe) in &probes {
        match probe {
            Probe::NotOllama => eprintln!(
                "Un service répond sur {addr} sans ressembler à Ollama : on ne l'utilise pas."
            ),
            Probe::Ollama(version) if !ollama_plan::version_is_supported(*version) => eprintln!(
                "L'Ollama qui répond sur {addr} est trop ancien ({version:?}, minimum {:?}) : \
                 on lance l'Ollama embarqué à la place.",
                ollama_plan::MIN_VERSION
            ),
            _ => {}
        }
    }

    let decision = ollama_plan::decide(&probes, app_has_model, |addr| ollama_has_model(addr, &model));
    let default_port_free = match decision {
        Decision::Reuse(addr) => return OllamaChoice { addr, models_dir: None },
        Decision::Embedded { default_port_free } => default_port_free,
    };

    let Some((bin, lib_dir)) = ollama_paths(app) else {
        // Pas d'arbre embarqué (sync-ollama.sh pas lancé en dev). On ne bloque pas le démarrage :
        // le front signalera l'absence de moteur via /system/llm/status (flux OPP-193).
        eprintln!("Ollama embarqué introuvable : moteur LLM indisponible (lance sync-ollama.sh).");
        return OllamaChoice { addr: unusable_ollama_addr(default_port_free), models_dir: None };
    };

    let user_dir_with_model = user_models_dir(app).filter(|dir| dir_has_model(dir, &model));
    let (models_dir, belongs_to_user) = match user_dir_with_model {
        Some(user_dir) if !app_has_model => (user_dir, true),
        _ => (app_dir, false),
    };
    if !belongs_to_user {
        let _ = std::fs::create_dir_all(&models_dir);
    }

    // Jusqu'à trois essais : le port par défaut s'il est libre, puis des ports libres donnés par
    // le système. Un port peut être pris par un autre programme entre le moment où on le choisit
    // et celui où Ollama l'ouvre ; Ollama s'arrête alors, et on réessaie ailleurs.
    for attempt in 0..3 {
        let addr = if attempt == 0 && default_port_free {
            ollama_plan::DEFAULT_ADDR.to_string()
        } else {
            match free_local_addr() {
                Ok(addr) => addr,
                Err(e) => {
                    eprintln!("Aucun port libre pour Ollama : {e}");
                    break;
                }
            }
        };

        let mut command = Command::new(&bin);
        command.arg("serve");
        command.env("OLLAMA_HOST", &addr);
        command.env("OLLAMA_MODELS", &models_dir);
        if belongs_to_user {
            // Ce dossier appartient à la personne : on interdit à notre Ollama d'y faire son
            // ménage de démarrage (suppression des fichiers qu'aucun modèle ne référence), qui
            // pourrait effacer un téléchargement qu'elle a laissé en cours.
            command.env("OLLAMA_NOPRUNE", "1");
        }
        // Où le binaire trouve ses runners : le `lib/ollama` voisin suffit (résolution relative à
        // l'exe), mais on le pose aussi explicitement pour les versions qui lisent cette variable.
        command.env("OLLAMA_LIBRARY_PATH", &lib_dir);

        let mut child = match spawn_in_group(command) {
            Ok(child) => child,
            Err(e) => {
                eprintln!("Échec du démarrage d'Ollama : {e}");
                break;
            }
        };
        if ollama_took_port(&mut child, &addr, Duration::from_secs(5)) {
            register_child(child);
            return OllamaChoice { addr, models_dir: Some(models_dir) };
        }
        eprintln!("Ollama s'est arrêté dès son démarrage sur {addr} : nouvel essai sur un autre port.");
    }

    OllamaChoice { addr: unusable_ollama_addr(default_port_free), models_dir: None }
}

/// Démarre l'API en sidecar (dans son propre groupe de processus).
///
/// On lui impose `OPPORTUNE_DATA_DIR` = dossier de données de l'app : les bases SQLite de l'API
/// vivent ainsi dans la **même** arborescence que les modèles Ollama de l'app, au lieu du dossier
/// par défaut de `app.paths`. `ollama` est le choix fait par `spawn_ollama`.
fn spawn_api(app: &tauri::AppHandle, ollama: &OllamaChoice) -> std::io::Result<()> {
    let mut command = Command::new(api_path());
    if let Ok(data_dir) = app.path().app_data_dir() {
        command.env("OPPORTUNE_DATA_DIR", &data_dir);
    }
    // On impose l'adresse choisie par `spawn_ollama` (Ollama réutilisé ou embarqué). Sans ça,
    // l'API hériterait de l'`OLLAMA_HOST` ambiant de la personne, souvent une adresse de bind
    // (`0.0.0.0`, sans port) inutilisable telle quelle, ou l'adresse d'un Ollama qu'on a écarté
    // parce qu'il est trop ancien. (Le back ajoute le `http://` manquant.)
    command.env("OLLAMA_HOST", &ollama.addr);
    // Dossier où un modèle téléchargé par l'app atterrira, quand on le connaît : l'API le note
    // avec le nom du modèle (`app.model_origin`), pour qu'une désinstallation ne supprime que
    // cette copie-là. Absent quand on réutilise l'Ollama de la personne.
    match &ollama.models_dir {
        Some(models_dir) => command.env("OPPORTUNE_OLLAMA_MODELS_DIR", models_dir),
        None => command.env_remove("OPPORTUNE_OLLAMA_MODELS_DIR"),
    };
    let child = spawn_in_group(command)?;
    register_child(child);
    Ok(())
}

/// Arrête tous les sidecars encore en vie (idempotent). `drain` garantit qu'un seul chemin
/// d'arrêt les emporte, même si deux se déclenchent (fermeture + signal).
///
/// Sous Unix, SIGTERM au **groupe** entier de chaque sidecar (`kill(-pgid)`, grâce au `setsid` du
/// spawn) : atteint le bootloader ET les process enfants. L'arrêt est **parallèle** : on signale
/// d'abord *tous* les groupes, puis on attend leur sortie propre (flush SQLite, etc.) sous une
/// **seule** échéance de ~5 s partagée avant de forcer au SIGKILL ceux qui traînent. Un arrêt
/// séquentiel cumulerait l'échéance par sidecar (jusqu'à 5 s chacun) et retarderait d'autant la
/// fermeture de la fenêtre. L'échéance évite aussi qu'un sidecar bloqué (requête LLM/scrape qui
/// ignore SIGTERM) fasse pendre `wait()` indéfiniment. Ailleurs, `kill` direct de chaque process.
fn kill_all() {
    let drained: Vec<Child> = children().lock().unwrap().drain(..).collect();

    #[cfg(unix)]
    {
        // Le sidecar est chef de son groupe (setsid), donc pgid == child.id(). On envoie SIGTERM à
        // tous les groupes d'abord, puis on attend sous une échéance commune.
        let mut pending: Vec<(i32, Child)> = drained
            .into_iter()
            .map(|child| {
                let pgid = child.id() as i32;
                unsafe {
                    libc::kill(-pgid, libc::SIGTERM);
                }
                (pgid, child)
            })
            .collect();

        let deadline = Instant::now() + Duration::from_secs(5);
        while !pending.is_empty() {
            // On retire ceux qui se sont arrêtés proprement (ou qu'on ne peut plus attendre).
            pending.retain_mut(|(_, child)| matches!(child.try_wait(), Ok(None)));
            if pending.is_empty() {
                break;
            }
            if Instant::now() >= deadline {
                // Échéance partagée dépassée : on force d'un coup le reste au SIGKILL.
                for (pgid, mut child) in pending.drain(..) {
                    unsafe {
                        libc::kill(-pgid, libc::SIGKILL);
                    }
                    let _ = child.wait();
                }
                break;
            }
            std::thread::sleep(Duration::from_millis(100));
        }
    }

    #[cfg(not(unix))]
    {
        for mut child in drained {
            let _ = child.kill();
            let _ = child.wait();
        }
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
        // Ouverture des liens externes via le navigateur système (openUrl côté front). La page
        // étant distante (127.0.0.1), l'accès à cette commande est autorisé par `remote.urls`
        // dans capabilities/default.json.
        .plugin(tauri_plugin_opener::init())
        // Export des données (OPP-232) : fenêtre « Enregistrer sous » puis écriture du fichier.
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .setup(|app| {
            let handle = app.handle().clone();

            // Tout le démarrage tourne dans un **thread de fond** : le choix d'Ollama sonde le
            // réseau (jusqu'à quelques secondes si un service ne répond pas), et l'attente de
            // l'API peut durer. Le faire ici gèlerait la boucle d'événements (sur macOS l'app
            // apparaîtrait « ne répond pas »).
            //
            // Ollama d'abord : l'API a besoin de son adresse. Le back ne s'y connecte qu'à la
            // première requête LLM, donc pas besoin d'attendre qu'il soit prêt. Sa disponibilité
            // est surveillée côté front (LlmSetupGate, /system/llm/status, OPP-193).
            //
            // On n'ouvre la fenêtre qu'une fois l'API prête, sinon la webview afficherait une
            // erreur de connexion. 20 s couvrent le premier démarrage (création + seed des bases).
            // En cas d'échec, on **tue les sidecars** avant de quitter, pour ne pas laisser de
            // process orphelin tenir un port (prochain lancement cassé).
            std::thread::spawn(move || {
                let ollama = spawn_ollama(&handle);
                let ready = match spawn_api(&handle, &ollama) {
                    Ok(()) => {
                        let ready = wait_until_ready(&api_addr(), Duration::from_secs(20));
                        if !ready {
                            eprintln!("Le service Opportune n'a pas démarré dans le délai imparti.");
                        }
                        ready
                    }
                    Err(e) => {
                        // Binaire API absent (sync-sidecar.sh pas lancé) : message explicite.
                        eprintln!(
                            "Impossible de lancer le service Opportune ({e}). Lance d'abord sync-sidecar.sh."
                        );
                        false
                    }
                };
                let ui = handle.clone();
                let _ = handle.run_on_main_thread(move || {
                    if !ready {
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

#[cfg(test)]
mod tests {
    use super::*;

    /// Verrou partagé par les tests : ils ouvrent et libèrent des ports de la boucle locale, et
    /// lancés en parallèle ils se prendraient le port qu'un autre vient de libérer.
    static PORTS: Mutex<()> = Mutex::new(());

    fn lock_ports() -> std::sync::MutexGuard<'static, ()> {
        PORTS.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    /// Lance sur la boucle locale un faux serveur qui répond `response` à la première connexion.
    /// Renvoie son adresse `127.0.0.1:<port>`.
    fn serve_once(response: &'static str) -> String {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let addr = format!("127.0.0.1:{}", listener.local_addr().unwrap().port());
        std::thread::spawn(move || {
            if let Ok((mut stream, _)) = listener.accept() {
                let mut request = [0u8; 512];
                let _ = stream.read(&mut request);
                let _ = stream.write_all(response.as_bytes());
            }
        });
        addr
    }

    #[test]
    fn probe_reads_version_of_a_responding_ollama() {
        let _ports = lock_ports();
        let ollama_addr = serve_once(
            "HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n{\"version\":\"0.13.1\"}",
        );

        assert_eq!(probe_ollama(&ollama_addr), Probe::Ollama((0, 13, 1)));
    }

    #[test]
    fn probe_flags_a_service_that_is_not_ollama() {
        let _ports = lock_ports();
        let other_service_addr = serve_once("HTTP/1.0 404 Not Found\r\n\r\n");

        assert_eq!(probe_ollama(&other_service_addr), Probe::NotOllama);
    }

    #[test]
    fn probe_flags_a_service_that_does_not_speak_http() {
        let _ports = lock_ports();
        let non_http_service_addr = serve_once("SSH-2.0-OpenSSH_9.6\r\n");

        assert_eq!(probe_ollama(&non_http_service_addr), Probe::NotOllama);
    }

    #[test]
    fn probe_ignores_version_found_in_headers_only() {
        let _ports = lock_ports();
        let service_with_version_header =
            serve_once("HTTP/1.0 200 OK\r\nX-Info: \"version\":\"1.2.0\"\r\n\r\n<html>ok</html>");

        assert_eq!(probe_ollama(&service_with_version_header), Probe::NotOllama);
    }

    #[test]
    fn probe_tries_every_resolved_address_of_a_host_name() {
        let _ports = lock_ports();
        // Le faux Ollama n'écoute qu'en IPv4 ; `localhost` peut donner `::1` en premier.
        let ollama_addr = serve_once("HTTP/1.0 200 OK\r\n\r\n{\"version\":\"0.20.0\"}");
        let same_port_by_name = ollama_addr.replace("127.0.0.1", "localhost");

        assert_eq!(probe_ollama(&same_port_by_name), Probe::Ollama((0, 20, 0)));
    }

    #[test]
    fn ollama_has_model_reads_the_inventory() {
        let _ports = lock_ports();
        let ollama_with_model =
            serve_once("HTTP/1.0 200 OK\r\n\r\n{\"models\":[{\"name\":\"ministral-3:3b\"}]}");
        let ollama_without_model = serve_once("HTTP/1.0 200 OK\r\n\r\n{\"models\":[]}");

        assert!(ollama_has_model(&ollama_with_model, "ministral-3:3b"));
        assert!(!ollama_has_model(&ollama_without_model, "ministral-3:3b"));
    }

    #[test]
    fn probe_all_keeps_one_result_per_address() {
        let _ports = lock_ports();
        let ollama_addr = serve_once("HTTP/1.0 200 OK\r\n\r\n{\"version\":\"0.20.0\"}");
        let unused_addr = free_local_addr().unwrap();

        let probes = probe_all(vec![ollama_addr.clone(), unused_addr.clone()]);

        assert_eq!(
            probes,
            vec![(ollama_addr, Probe::Ollama((0, 20, 0))), (unused_addr, Probe::Absent)]
        );
    }

    #[test]
    fn probe_is_absent_when_nothing_listens() {
        let _ports = lock_ports();
        let unused_addr = free_local_addr().unwrap();

        assert_eq!(probe_ollama(&unused_addr), Probe::Absent);
    }

    #[cfg(unix)]
    #[test]
    fn ollama_took_port_when_it_answers_on_its_address() {
        let _ports = lock_ports();
        let answering_addr = serve_once("HTTP/1.0 200 OK\r\n\r\n{\"version\":\"0.40.13\"}");
        let mut running_child = Command::new("sleep").arg("30").spawn().unwrap();

        let took_port = ollama_took_port(&mut running_child, &answering_addr, Duration::from_secs(5));
        let _ = running_child.kill();
        let _ = running_child.wait();

        assert!(took_port);
    }

    #[cfg(unix)]
    #[test]
    fn ollama_did_not_take_port_when_it_exits_at_startup() {
        let _ports = lock_ports();
        let unused_addr = free_local_addr().unwrap();
        let mut child_that_exits = Command::new("true").spawn().unwrap();

        let took_port = ollama_took_port(&mut child_that_exits, &unused_addr, Duration::from_secs(5));

        assert!(!took_port);
    }

    #[cfg(unix)]
    #[test]
    fn slow_ollama_still_running_at_deadline_is_kept() {
        let _ports = lock_ports();
        let unused_addr = free_local_addr().unwrap();
        let mut slow_child = Command::new("sleep").arg("30").spawn().unwrap();

        let took_port = ollama_took_port(&mut slow_child, &unused_addr, Duration::from_millis(300));
        let _ = slow_child.kill();
        let _ = slow_child.wait();

        assert!(took_port);
    }

    #[test]
    fn free_local_addr_can_be_bound() {
        let _ports = lock_ports();
        let free_addr = free_local_addr().unwrap();

        assert!(TcpListener::bind(&free_addr).is_ok());
    }
}
