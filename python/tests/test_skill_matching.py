"""Tests du rapprochement de compétences (alias + familles) (OPP-139)."""

from app.skill_matching import canonicalize, expand_skills


# --- canonicalize ------------------------------------------------------------


def test_canonicalize_normalizes_case_and_spaces():
    assert canonicalize("  Python  ") == "python"
    assert canonicalize("Node   JS") == canonicalize("nodejs") == "node.js"


def test_canonicalize_applies_aliases():
    assert canonicalize("JS") == "javascript"
    assert canonicalize("TS") == "typescript"
    assert canonicalize("Postgres") == "postgresql"
    assert canonicalize("ReactJS") == "react"


def test_canonicalize_unknown_skill_is_left_normalized():
    assert canonicalize("Rust") == "rust"


def test_canonicalize_versions_and_rest_family():
    # OPP-157 : versions = même techno ; la famille REST converge (évite les quasi-doublons).
    assert canonicalize("HTML5") == "html"
    assert canonicalize("CSS3") == "css"
    assert canonicalize("REST API") == canonicalize("RESTful Design") == "rest api"
    assert canonicalize("CI-CD") == canonicalize("CICD") == "ci/cd"


# --- expand_skills (familles / implications) ---------------------------------


def test_family_specific_implies_general():
    # Avoir React ou TypeScript implique JavaScript.
    assert "javascript" in expand_skills(["React"])
    assert "javascript" in expand_skills(["TypeScript"])


def test_family_is_transitive():
    # next.js ⇒ react ⇒ javascript
    owned = expand_skills(["Next.js"])
    assert {"next.js", "react", "javascript"} <= owned


def test_family_is_unidirectional():
    # JavaScript n'implique PAS TypeScript (spécifique ⇒ général, jamais l'inverse).
    owned = expand_skills(["JavaScript"])
    assert owned == {"javascript"}


def test_github_actions_implies_git_and_github():
    owned = expand_skills(["GitHub Actions"])
    assert {"github actions", "github", "git"} <= owned


def test_ci_cd_implied_by_pipelines():
    # OPP-157 : maîtriser GitHub Actions / GitLab CI / Jenkins implique « CI/CD ».
    assert "ci/cd" in expand_skills(["GitHub Actions"])
    assert "ci/cd" in expand_skills(["GitLab CI"])
    assert "ci/cd" in expand_skills(["Jenkins"])


def test_expand_skips_blank_and_dedups():
    owned = expand_skills(["  ", "React", "reactjs"])
    # "React" et "reactjs" → même canonique ; pas d'entrée vide.
    assert "react" in owned and "" not in owned
