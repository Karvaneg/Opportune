"""Tests de l'autorisation des interactions Discord (OPP-124).

Pur, sans réseau : extraction d'identité depuis un payload simulé + décision allowlist.
"""

from app.discord_authz import ENV_VAR, ReviewerAllowlist, extract_discord_user_id


# --- extract_discord_user_id -------------------------------------------------


def test_extracts_identity_from_guild_member():
    interaction = {"member": {"user": {"id": "u-42"}}}
    assert extract_discord_user_id(interaction) == "u-42"


def test_extracts_identity_from_direct_message_user():
    interaction = {"user": {"id": "u-7"}}
    assert extract_discord_user_id(interaction) == "u-7"


def test_member_user_takes_precedence_over_root_user():
    # Contexte salon : member.user est le cliqueur ; on ne se laisse pas berner par un
    # user racine divergent.
    interaction = {"member": {"user": {"id": "u-member"}}, "user": {"id": "u-root"}}
    assert extract_discord_user_id(interaction) == "u-member"


def test_missing_or_malformed_identity_is_none():
    assert extract_discord_user_id({}) is None
    assert extract_discord_user_id({"member": {}}) is None
    assert extract_discord_user_id({"user": {"id": ""}}) is None
    assert extract_discord_user_id({"user": {"id": 123}}) is None  # id non-str
    assert extract_discord_user_id("pas un dict") is None


# --- ReviewerAllowlist -------------------------------------------------------


def test_is_allowed_true_for_listed_id():
    allowlist = ReviewerAllowlist(frozenset({"a", "b"}))
    assert allowlist.is_allowed("a") is True
    assert allowlist.is_allowed("z") is False


def test_is_allowed_false_for_none_or_empty():
    allowlist = ReviewerAllowlist(frozenset({"a"}))
    assert allowlist.is_allowed(None) is False
    assert allowlist.is_allowed("") is False


def test_empty_allowlist_denies_everyone_fail_closed():
    empty = ReviewerAllowlist(frozenset())
    assert empty.is_allowed("a") is False


def test_from_env_parses_csv_and_trims():
    allowlist = ReviewerAllowlist.from_env({ENV_VAR: " a , b ,, c "})
    assert allowlist.allowed == frozenset({"a", "b", "c"})


def test_from_env_absent_or_empty_is_fail_closed():
    assert ReviewerAllowlist.from_env({}).allowed == frozenset()
    assert ReviewerAllowlist.from_env({ENV_VAR: ""}).allowed == frozenset()
    assert ReviewerAllowlist.from_env({ENV_VAR: "  "}).allowed == frozenset()
