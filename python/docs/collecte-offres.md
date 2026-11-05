# Collecter des offres réelles (OPP-120 / OPP-122)

La collecte réelle branche une **source** (port `SourceOffres`) sur le socle de collecte
(OPP-119) : dédoublonnage **avant** analyse LLM, normalisation, persistance. Chaque runner ne
fait que lire sa configuration, assembler sa source et lancer la passe (briques communes dans
`app.collection_runner`). Les runners affichent un bilan (collectées / persistées / doublons /
échecs) et sortent en code non nul si la **source** a échoué (quota, réseau, identifiants) ;
les échecs d'analyse **par offre** sont consignés sans interrompre la passe.

> **Quelle source utiliser ?** Pour un usage prêt à l'emploi, **Adzuna** est la source
> recommandée : inscription gratuite et **clé délivrée instantanément en self-service**, sans
> démarche manuelle. Le connecteur **RSS** complète (aucun identifiant, mais à vous de fournir
> des flux). **France Travail**, l'API officielle, serait la plus riche mais n'est **pas
> utilisable** aujourd'hui (voir plus bas) — d'où le choix d'Adzuna par défaut.

> **Depuis l'app** : la collecte se lance aussi depuis le catalogue d'offres (`POST /collect`,
> job de fond annulable, sources `adzuna` et `rss`). Elle utilise alors les **clés Adzuna** et
> les **URLs de flux RSS** saisies dans la page Réglages (OPP-195 / OPP-222). L'app n'utilise
> **que** les clés saisies dans les Réglages de l'espace : `ADZUNA_APP_ID` / `ADZUNA_APP_KEY`
> ne servent plus de repli (OPP-227). Sans clés saisies, le bouton de collecte Adzuna est
> désactivé. Les runners ci-dessous restent la voie en ligne de commande et lisent
> l'environnement.

## RSS — connecteur actif, sans secret

`app.rss_runner` ingère des offres depuis des **flux RSS/Atom** d'alertes emploi (`app.rss_feed`
parse RSS 2.0 / RDF / Atom ; `app.rss_source` fetch SSRF-safe + nettoyage HTML du contenu). Aucun
identifiant requis : c'est le connecteur le plus simple et le plus pérenne.

Le contenu d'un article RSS étant du HTML, ce runner **requiert l'extra `scrape`** (BeautifulSoup) ;
il échoue d'emblée avec un message clair s'il est absent.

```bash
pip install -e ".[scrape]"                       # requis : nettoyage HTML du contenu des flux
export OPPORTUNE_LLM_TIMEOUT=300                # timeout LLM (s) pour l'analyse d'intake
# OLLAMA_HOST / OLLAMA_MODEL / OPPORTUNE_DB_PATH : cf. README back

python -m app.rss_runner --feed https://exemple.fr/offres.rss --feed https://autre.fr/flux.xml
RSS_FEED_URLS="https://a.rss,https://b.xml" python -m app.rss_runner   # ou via l'environnement
```

Options : `--feed` (répétable) ou `RSS_FEED_URLS` (séparé par virgules/espaces), `--max` (plafond
d'offres sur l'ensemble des flux, défaut 500). Les flux sont parcourus en séquence ; l'échec d'un
flux (réseau, XML malformé) arrête la passe en `source_error`, les offres déjà émises restant acquises.

## Adzuna — connecteur actif

`app.adzuna_runner` interroge l'[API Adzuna](https://developer.adzuna.com) (marché français),
en ciblant par défaut les contrats permanents (≈ CDI). Inscription gratuite et instantanée sur
developer.adzuna.com : l'`app_id` et l'`app_key` sont affichés aussitôt (cf. `../.env.example`).

```bash
export ADZUNA_APP_ID=...                        # requis
export ADZUNA_APP_KEY=...                        # requis
export OPPORTUNE_LLM_TIMEOUT=300                # timeout LLM (s) pour l'analyse d'intake
# OLLAMA_HOST / OLLAMA_MODEL / OPPORTUNE_DB_PATH : cf. README back

python -m app.adzuna_runner --what "python" --where "Paris" --max 100
python -m app.adzuna_runner --tous-contrats     # ne pas restreindre aux CDI
```

Options : `--what`, `--where` (filtres de recherche), `--max` (plafond d'offres, défaut 200 —
modéré pour ménager le quota gratuit de 2 500 appels/mois), `--tous-contrats` (lève le filtre
CDI). Le runner pagine jusqu'au total annoncé (`count`) ou au plafond.

## Entreprises ciblées (Greenhouse, Lever) — connecteur actif, sans secret (OPP-226)

Beaucoup d'entreprises publient leurs offres via un **ATS** (logiciel de recrutement) dont l'API
de lecture est publique et sans clé. Opportune en lit deux :

| ATS | Pages carrière reconnues | API interrogée |
|---|---|---|
| Greenhouse | `boards.greenhouse.io/{id}`, `job-boards.greenhouse.io/{id}` (et leurs variantes `.eu.`), `boards.greenhouse.io/embed/job_board?for={id}` | `boards-api.greenhouse.io/v1/boards/{id}/jobs?content=true` |
| Lever | `jobs.lever.co/{id}`, `jobs.eu.lever.co/{id}` | `api.lever.co/v0/postings/{id}` (ou `api.eu.lever.co`) |

Fonctionnement (règles métier complètes dans le ticket OPP-226) :

- L'utilisatrice colle les pages carrière dans les Réglages (`PUT /settings/ats`, 50 maximum).
  Chaque **nouvelle** entreprise est vérifiée auprès de son ATS, une par une (RG-21) : URL non reconnue ou entreprise introuvable → refus de tout l'enregistrement (400) ; ATS
  injoignable → 502 ; fichier impossible à écrire → 500.
- La collecte (`POST /collect` avec `source: "ats"`) lit toutes les offres publiées de chaque
  entreprise. `where` ne s'applique pas. `what` (poste recherché) est **facultatif** : s'il est
  renseigné, une offre n'est gardée que si chacun de ses mots **commence un mot** de l'intitulé
  (casse et accents ignorés : « dev » garde « Développeur », « IA » ne garde pas « Commercial »),
  **avant** l'analyse LLM ; le bilan compte les offres écartées (`off_target`). Vide, toutes les
  offres en France sont gardées et c'est le score qui trie. Limite : « C++ » se réduit à « c ».
- **Filtre France** : Lever, `country = FR` ou un lieu qui mentionne la France ; Greenhouse, le
  lieu ou un bureau qui mentionne la France. « Mentionne la France » = contient « France » ou le
  nom d'une grande ville française (`FRENCH_CITIES` : Paris, Lyon, Nantes…), car Greenhouse ne
  donne souvent que la ville. Une ville française ne suffit pas si le morceau qui la suit après
  une virgule est un pays, un État américain, une province canadienne (`FOREIGN_PLACES`) ou leur
  code (`FOREIGN_REGION_CODES`) : « Paris, Texas », « Paris, TX », « Nice, CA » sont écartés,
  mais « Paris, Berlin, Germany » est gardé. Un lieu qui en liste plusieurs (« Paris or Berlin,
  Germany ») est jugé morceau par morceau. Une offre en télétravail sans pays est écartée. Le
  bilan compte les offres écartées (`excluded`).
- **Plafond en offres neuves** (toutes sources de `POST /collect`) : `max` compte les offres
  **neuves**, pas les doublons. La passe s'arrête après `max` offres neuves ; la source est
  plafonnée à `max × 5` pour que les doublons d'une passe précédente ne bloquent pas la collecte
  sans laisser une source paginée lire sans fin.
- La vérification à l'enregistrement demande à Greenhouse la liste **sans** descriptions (plus
  légère) : le nombre d'offres en France affiché se fonde alors sur le lieu de l'offre, pas sur
  ses bureaux. À la première erreur, les entreprises suivantes ne sont pas interrogées.
- Une entreprise en échec pendant la passe (404, 429, réseau) est signalée dans le bilan
  (`warnings`) et la passe continue ; la collecte n'échoue que si **toutes** échouent.
- Lecture seule, requêtes séquentielles, `User-Agent` qui identifie Opportune. Aucune
  dépendance : la description HTML est convertie par `app.html_text` (bibliothèque standard).

Modules : `app.ats_company` (URL → entreprise), `app.ats_client` (HTTP), `app.ats_location`
(filtre France), `app.ats_title_filter` (filtre poste), `app.ats_offer` (offre → `RawOffer`), `app.ats_source` (port `SourceOffres`),
`app.ats_companies_store` / `app.ats_companies_service` (réglages).

Couverture : de nombreuses entreprises françaises utilisent d'autres ATS (Workday, Teamtailor,
Taleez…) et ne sont pas collectables ainsi. SmartRecruiters (endpoint public sans clé, mais sans
conditions d'utilisation officielles trouvées) est prévu dans un ticket séparé.

## France Travail — connecteur dormant

`app.france_travail_runner` interroge l'API officielle France Travail « Offres d'emploi ».
⚠️ **Cette API n'est pas utilisable en l'état** (vérifié oct. 2026). Elle a été **retirée de
`francetravail.io`** le temps d'une analyse des modalités de distribution et de réutilisation,
**suite à des usages automatisés massifs par des solutions d'IA** ne respectant pas les
conditions/licences associées. Quand l'accès rouvrira, il sera **« Restreint »** : demande via
le formulaire de contact + **autorisation préalable** (pas de self-service), acceptation d'une
**licence de réutilisation** (non ouverte au sens strict ; rappelle les art. L.5321-1 et s. du
Code du travail sur le placement). Les **particuliers** font partie des publics éligibles.

Conséquence pour Opportune : ce modèle d'autorisation **au cas par cas** se prête mal à une
diffusion où chaque utilisateur apporterait ses identifiants — c'est précisément le profil
d'usage que France Travail cherche à encadrer. Le connecteur reste donc **prêt mais dormant**,
conservé pour un usage personnel autorisé ou une réouverture future. **Adzuna** reste la source
par défaut.

```bash
export FRANCE_TRAVAIL_CLIENT_ID=...             # requis : identifiant de l'application
export FRANCE_TRAVAIL_CLIENT_SECRET=...         # requis : secret (SECRET, jamais en dur)

python -m app.france_travail_runner --mots-cles "python" --max 150
python -m app.france_travail_runner --code-rome M1805 --commune 75056
```

Options : `--mots-cles`, `--code-rome`, `--commune`, `--max` (plafond borné à la fenêtre dure
de l'API, `range` ≤ 1000/1149, soit ~1150 offres par requête ; au-delà il faudrait fragmenter
par date/département, hors périmètre).
