//! Versioned registry of sensitive locations and file types.
//!
//! Two consumers share this module so detection and enforcement cannot drift:
//!
//! * Auto Detect uses [`classify`] to propose owner review items. A match is a
//!   *proposal*; it never grants access and never substitutes for owner review.
//! * The privileged helper uses [`is_protected_name`] for the exact protected
//!   file names that ACL enforcement must never share with a worker.
//!
//! Rules are matched against whole path components, file extensions and word
//! boundaries instead of substrings, and never against a hardcoded user name, so
//! the registry is portable across owners and does not depend on the owner being
//! called `huou07`. Containers whose contents are encrypted or unreadable
//! (`*.kdbx`, `*.p12`, `*.age`) are recognised from their type alone; nothing is
//! ever decrypted and no matched content is retained.

use std::fs::Metadata;
use std::os::unix::fs::MetadataExt;
use std::path::Path;

/// Bump when rule semantics change. Recorded with scan results so a cached
/// decision computed under older rules is never presented as current.
pub(crate) const REGISTRY_VERSION: u32 = 1;

/// Result of classifying one path. `reason` and `category` are stable machine
/// identifiers; the GUI renders them and they are never secret values.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct Classification {
    /// True when the path is a sensitive location or type.
    pub sensitive: bool,
    /// `high`, `medium` or `unknown`. Never `low`: an unclassified path is
    /// reported as `unknown` and must not be shown as safe.
    pub confidence: &'static str,
    /// Stable reason identifier.
    pub reason: &'static str,
    /// Stable category identifier, or `none` for an ordinary path.
    pub category: &'static str,
}

impl Classification {
    const fn ordinary() -> Self {
        Self {
            sensitive: false,
            confidence: "unknown",
            reason: "no_known_sensitive_marker",
            category: "none",
        }
    }

    const fn sensitive(category: &'static str, reason: &'static str) -> Self {
        Self {
            sensitive: true,
            confidence: "high",
            reason,
            category,
        }
    }
}

/// Directory sequences matched as consecutive whole path components at any
/// depth, compared case-insensitively. A single-element sequence matches that
/// component anywhere in the path, which keeps the registry independent of the
/// owner's home directory and user name.
const SENSITIVE_DIRECTORIES: &[(&[&str], &str, &str)] = &[
    (&[".ssh"], "ssh_keys", "sensitive_ssh_directory"),
    (&[".gnupg"], "gpg_keys", "sensitive_gpg_directory"),
    (
        &[".aws"],
        "cloud_credentials",
        "sensitive_cloud_credentials",
    ),
    (
        &[".azure"],
        "cloud_credentials",
        "sensitive_cloud_credentials",
    ),
    (
        &[".kube"],
        "cluster_credentials",
        "sensitive_cluster_credentials",
    ),
    (
        &[".docker"],
        "container_credentials",
        "sensitive_container_credentials",
    ),
    (
        &[".config", "gcloud"],
        "cloud_credentials",
        "sensitive_cloud_credentials",
    ),
    (
        &[".config", "rclone"],
        "cloud_credentials",
        "sensitive_cloud_credentials",
    ),
    (
        &[".config", "gh"],
        "ci_credentials",
        "sensitive_ci_credentials",
    ),
    (
        &[".config", "glab-cli"],
        "ci_credentials",
        "sensitive_ci_credentials",
    ),
    (
        &[".config", "containers"],
        "container_credentials",
        "sensitive_container_credentials",
    ),
    (
        &[".local", "share", "containers"],
        "container_credentials",
        "sensitive_container_credentials",
    ),
    (
        &[".local", "share", "keyrings"],
        "session_store",
        "sensitive_session_store",
    ),
    (
        &[".password-store"],
        "password_database",
        "sensitive_password_store",
    ),
    (
        &[".mozilla", "firefox"],
        "browser_profile",
        "sensitive_browser_profile",
    ),
    (
        &[".config", "chromium"],
        "browser_profile",
        "sensitive_browser_profile",
    ),
    (
        &[".config", "google-chrome"],
        "browser_profile",
        "sensitive_browser_profile",
    ),
    (
        &[".config", "bravesoftware"],
        "browser_profile",
        "sensitive_browser_profile",
    ),
    (
        &[".config", "microsoft-edge"],
        "browser_profile",
        "sensitive_browser_profile",
    ),
];

/// Exact lowercase file names that are sensitive wherever they appear.
const SENSITIVE_NAMES: &[(&str, &str, &str)] = &[
    (".netrc", "package_manager_credentials", "sensitive_netrc"),
    (".npmrc", "package_manager_credentials", "sensitive_netrc"),
    (".pypirc", "package_manager_credentials", "sensitive_netrc"),
    (".s3cfg", "cloud_credentials", "sensitive_cloud_credentials"),
    (
        ".git-credentials",
        "vcs_credentials",
        "sensitive_vcs_credentials",
    ),
    (
        ".gitcookies",
        "vcs_credentials",
        "sensitive_vcs_credentials",
    ),
    (
        ".pgpass",
        "database_credentials",
        "sensitive_database_credentials",
    ),
    (
        ".my.cnf",
        "database_credentials",
        "sensitive_database_credentials",
    ),
    (
        ".htpasswd",
        "password_database",
        "sensitive_password_database",
    ),
    (".envrc", "api_configuration", "sensitive_api_configuration"),
    (
        "kubeconfig",
        "cluster_credentials",
        "sensitive_cluster_credentials",
    ),
    (
        "auth.json",
        "api_configuration",
        "sensitive_api_configuration",
    ),
    (
        "credentials",
        "api_configuration",
        "sensitive_api_configuration",
    ),
    (
        "credentials.json",
        "api_configuration",
        "sensitive_api_configuration",
    ),
    (
        "credentials.yaml",
        "api_configuration",
        "sensitive_api_configuration",
    ),
    (
        "credentials.yml",
        "api_configuration",
        "sensitive_api_configuration",
    ),
    (
        "credentials.toml",
        "api_configuration",
        "sensitive_api_configuration",
    ),
    (
        ".credentials.yaml",
        "api_configuration",
        "sensitive_api_configuration",
    ),
    ("master.key", "application_key", "sensitive_application_key"),
    ("id_rsa", "ssh_keys", "sensitive_ssh_key"),
    ("id_dsa", "ssh_keys", "sensitive_ssh_key"),
    ("id_ecdsa", "ssh_keys", "sensitive_ssh_key"),
    ("id_ed25519", "ssh_keys", "sensitive_ssh_key"),
    (
        "authorized_keys",
        "ssh_keys",
        "sensitive_ssh_authorized_keys",
    ),
    ("known_hosts", "ssh_keys", "sensitive_ssh_known_hosts"),
    (".bash_history", "session_store", "sensitive_session_store"),
    (".zsh_history", "session_store", "sensitive_session_store"),
    (".lesshst", "session_store", "sensitive_session_store"),
    (
        "passwd",
        "system_authentication",
        "sensitive_system_authentication",
    ),
    (
        "shadow",
        "system_authentication",
        "sensitive_system_authentication",
    ),
    (
        "gshadow",
        "system_authentication",
        "sensitive_system_authentication",
    ),
    (
        "sudoers",
        "system_authentication",
        "sensitive_system_authentication",
    ),
    ("terraform.tfstate", "iac_state", "sensitive_iac_state"),
];

/// Extensions that identify a secret container by type, including containers
/// whose contents are encrypted and therefore unreadable.
const SENSITIVE_EXTENSIONS: &[(&str, &str, &str)] = &[
    ("pem", "private_certificate", "sensitive_private_key_file"),
    ("key", "private_certificate", "sensitive_private_key_file"),
    ("p12", "private_certificate", "sensitive_private_key_file"),
    ("pfx", "private_certificate", "sensitive_private_key_file"),
    ("jks", "private_certificate", "sensitive_private_key_file"),
    (
        "keystore",
        "private_certificate",
        "sensitive_private_key_file",
    ),
    ("ppk", "private_certificate", "sensitive_private_key_file"),
    ("kdbx", "password_database", "sensitive_password_database"),
    (
        "age",
        "encrypted_container",
        "sensitive_encrypted_container",
    ),
];

/// Lowercase extensions that make a generic secret-ish word worth reviewing.
const API_CONFIGURATION_EXTENSIONS: &[&str] = &[
    "env",
    "json",
    "yaml",
    "yml",
    "toml",
    "ini",
    "cfg",
    "conf",
    "properties",
];

/// Whole-word tokens that mark a file as a probable credential container.
const CREDENTIAL_TOKENS: &[&str] = &[
    "credential",
    "credentials",
    "secret",
    "secrets",
    "password",
    "passwd",
    "passphrase",
    "token",
    "tokens",
    "apikey",
    "api",
    "accesskey",
    "privatekey",
];

/// Names that only ever appear as documentation or fixtures.
const PLACEHOLDER_MARKERS: &[&str] = &["example", "sample", "template", "dist", "fixture"];

/// Exact protected names used by ACL enforcement. This is the historical
/// protected set; keeping it here makes the detection registry and enforcement
/// share one definition and prevents the two lists drifting apart.
const PROTECTED_NAMES: &[&str] = &[
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".git-credentials",
    ".bash_history",
    ".zsh_history",
    ".lesshst",
    "auth.json",
    ".credentials.yaml",
    "credentials.json",
    "credentials.yaml",
    "credentials.yml",
    "credentials",
    "credentials.toml",
    "known_hosts",
    "passwd",
    "shadow",
    "gshadow",
    "sudoers",
    ".s3cfg",
    ".envrc",
    ".gitcookies",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "authorized_keys",
];

/// Suffixes protected by ACL enforcement. Narrower than the detection registry
/// on purpose: enforcement must not start denying paths that used to be shared
/// merely because detection learned about more container types.
const PROTECTED_SUFFIXES: &[&str] = &[".pem", ".key", ".p12", ".pfx"];

/// True when a file name is a protected credential name under ACL enforcement.
///
/// This reproduces the historical helper predicate exactly: an exact protected
/// name, one of four protected suffixes, or an environment file that is not a
/// template. It is not the detection registry; see [`classify`].
pub(crate) fn is_protected_name(name: &str) -> bool {
    let name = name.to_ascii_lowercase();
    PROTECTED_NAMES.contains(&name.as_str())
        || PROTECTED_SUFFIXES
            .iter()
            .any(|suffix| name.ends_with(suffix))
        || ((name == ".env" || name.starts_with(".env.") || name.ends_with(".env"))
            && !["example", "sample", "template"]
                .iter()
                .any(|part| name.contains(part)))
}

fn lower_components(path: &Path) -> Vec<String> {
    path.components()
        .filter_map(|component| match component {
            std::path::Component::Normal(part) => Some(part.to_string_lossy().to_ascii_lowercase()),
            _ => None,
        })
        .collect()
}

fn contains_sequence(components: &[String], sequence: &[&str]) -> bool {
    if sequence.is_empty() || sequence.len() > components.len() {
        return false;
    }
    components
        .windows(sequence.len())
        .any(|window| window.iter().zip(sequence).all(|(part, want)| part == want))
}

/// Split a file name into a lowercase stem and extension.
fn split_name(name: &str) -> (&str, &str) {
    match name.rsplit_once('.') {
        // A leading dot does not introduce an extension (".env" has no extension).
        Some((stem, extension)) if !stem.is_empty() => (stem, extension),
        _ => (name, ""),
    }
}

fn is_placeholder(name: &str) -> bool {
    let token_boundaries = name
        .split(|c: char| !c.is_ascii_alphanumeric())
        .filter(|part| !part.is_empty());
    PLACEHOLDER_MARKERS
        .iter()
        .any(|marker| token_boundaries.clone().any(|part| part == *marker))
}

fn generic_credential_match(name: &str) -> bool {
    let (stem, extension) = split_name(name);
    if extension.is_empty() {
        // A bare name such as "deploy-token" is still a credential container.
    } else if !API_CONFIGURATION_EXTENSIONS.contains(&extension) {
        return false;
    }
    if is_placeholder(name) {
        return false;
    }
    stem.split(|c: char| !c.is_ascii_alphanumeric())
        .filter(|part| !part.is_empty())
        .any(|part| CREDENTIAL_TOKENS.contains(&part))
}

fn is_private_file(meta: &Metadata) -> bool {
    meta.is_file() && meta.mode() & 0o077 == 0
}

/// Classify one path. `meta` is optional so callers can classify a name they
/// cannot stat; without metadata a generic match stays `medium` rather than
/// being promoted to `high`.
pub(crate) fn classify(path: &Path, meta: Option<&Metadata>) -> Classification {
    let components = lower_components(path);
    for (sequence, category, reason) in SENSITIVE_DIRECTORIES {
        if contains_sequence(&components, sequence) {
            return Classification::sensitive(category, reason);
        }
    }
    let name = components.last().cloned().unwrap_or_default();
    // ".env" itself, and ".env.<environment>" variants, but never templates.
    if name == ".env" || (name.starts_with(".env.") && !is_placeholder(&name)) {
        return Classification::sensitive("api_configuration", "sensitive_api_configuration");
    }
    if let Some((_, category, reason)) = SENSITIVE_NAMES.iter().find(|(want, _, _)| *want == name) {
        return Classification::sensitive(category, reason);
    }
    let (_, extension) = split_name(&name);
    if !extension.is_empty() {
        if let Some((_, category, reason)) = SENSITIVE_EXTENSIONS
            .iter()
            .find(|(want, _, _)| *want == extension)
        {
            return Classification::sensitive(category, reason);
        }
    }
    if generic_credential_match(&name) {
        // Private permission bits corroborate the name; without them the match
        // is only a review suggestion.
        let confidence = match meta {
            Some(meta) if is_private_file(meta) => "high",
            _ => "medium",
        };
        return Classification {
            sensitive: true,
            confidence,
            reason: "sensitive_credential_name",
            category: "api_configuration",
        };
    }
    Classification::ordinary()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn classified(path: &str) -> Classification {
        classify(Path::new(path), None)
    }

    #[test]
    fn portable_locations_are_sensitive_without_a_hardcoded_user() {
        for path in [
            "/home/someone/.ssh/id_ed25519",
            "/home/someone/.gnupg/private-keys-v1.d/key.key",
            "/home/someone/.aws/credentials",
            "/srv/backup/home/another-user/.azure/msal_token_cache.json",
            "/home/third/.config/gcloud/application_default_credentials.json",
            "/home/third/.kube/config",
            "/home/third/.docker/config.json",
            "/home/third/.config/containers/auth.json",
            "/home/third/.local/share/containers/storage/overlay",
            "/home/third/.local/share/keyrings/login.keyring",
            "/home/third/.password-store/email.gpg",
            "/home/third/.mozilla/firefox/abc.default-release/logins.json",
            "/home/third/.config/chromium/Default/Login Data",
            "/home/third/.config/google-chrome/Default/Cookies",
            "/home/third/.config/gh/hosts.yml",
            "/home/third/.config/glab-cli/config.yml",
        ] {
            assert!(classified(path).sensitive, "{path}");
            assert_eq!(classified(path).confidence, "high", "{path}");
        }
    }

    #[test]
    fn sensitive_file_types_are_recognised_by_type() {
        for (path, reason) in [
            ("/home/x/vault.kdbx", "sensitive_password_database"),
            ("/home/x/tls.pem", "sensitive_private_key_file"),
            ("/home/x/service.p12", "sensitive_private_key_file"),
            ("/home/x/id.ppk", "sensitive_private_key_file"),
            ("/home/x/backup.tar.age", "sensitive_encrypted_container"),
            ("/home/x/.env", "sensitive_api_configuration"),
            ("/home/x/.env.production", "sensitive_api_configuration"),
            ("/home/x/.netrc", "sensitive_netrc"),
            ("/home/x/terraform.tfstate", "sensitive_iac_state"),
            ("/home/x/kubeconfig", "sensitive_cluster_credentials"),
        ] {
            let result = classified(path);
            assert!(result.sensitive, "{path}");
            assert_eq!(result.reason, reason, "{path}");
        }
    }

    #[test]
    fn ordinary_project_files_are_not_reported_as_sensitive() {
        for path in [
            "/home/x/Projects/app/src/tokenizer.rs",
            "/home/x/Projects/app/docs/secretary.md",
            "/home/x/Projects/app/tests/password_reset_test.py",
            "/home/x/Projects/app/.env.example",
            "/home/x/Projects/app/.env.sample",
            "/home/x/Projects/app/credentials_example.json",
            "/home/x/Projects/app/docs/aws-example.md",
            "/home/x/Projects/app/src/keys/public.crt",
            "/home/x/Projects/app/build/target.o",
            "/home/x/Projects/app/config/settings.toml",
            "/home/x/Projects/app/README.md",
        ] {
            assert!(!classified(path).sensitive, "{path}");
            assert_eq!(classified(path).confidence, "unknown", "{path}");
            assert_eq!(classified(path).category, "none", "{path}");
        }
    }

    #[test]
    fn generic_credential_names_need_a_configuration_shape() {
        // Word-boundary matching keeps ordinary source names out of the results.
        assert!(!classified("/home/x/Projects/app/tokenizer.rs").sensitive);
        assert!(!classified("/home/x/Projects/app/secretary.md").sensitive);
        // A configuration-shaped name is a review suggestion, not a claim.
        let medium = classified("/home/x/Projects/app/secrets.yaml");
        assert!(medium.sensitive);
        assert_eq!(medium.confidence, "medium");
        assert_eq!(medium.reason, "sensitive_credential_name");
        // A bare name is still worth reviewing.
        assert!(classified("/home/x/deploy-token").sensitive);
    }

    #[test]
    fn classification_never_grants_access_and_never_claims_safety() {
        let ordinary = classified("/home/x/Projects/app/src/main.rs");
        assert!(!ordinary.sensitive);
        // An ordinary path is "unknown", never "safe": the GUI must not show a
        // green indicator for content that was never classified.
        assert_eq!(ordinary.confidence, "unknown");
        assert_ne!(ordinary.reason, "no_finding");
    }

    #[test]
    fn enforcement_predicate_keeps_the_historical_protected_set() {
        for name in [
            ".netrc",
            ".npmrc",
            ".pypirc",
            ".git-credentials",
            ".bash_history",
            ".zsh_history",
            ".lesshst",
            "auth.json",
            ".credentials.yaml",
            "credentials.json",
            "credentials.yaml",
            "credentials.yml",
            "credentials",
            "credentials.toml",
            "known_hosts",
            "passwd",
            "shadow",
            "gshadow",
            "sudoers",
            ".s3cfg",
            ".envrc",
            ".gitcookies",
            "id_rsa",
            "id_ed25519",
            "id_ecdsa",
            "authorized_keys",
            "server.pem",
            "server.key",
            "bundle.p12",
            "bundle.pfx",
            ".env",
            ".env.local",
            "production.env",
        ] {
            assert!(is_protected_name(name), "{name}");
        }
        for name in [
            ".env.example",
            ".env.sample",
            ".env.template",
            "tokenizer.rs",
            "secretary.md",
            "public.crt",
            "vaul.kdbx",
            ".age",
        ] {
            assert!(!is_protected_name(name), "{name}");
        }
        // Case folding matches the historical helper predicate.
        assert!(is_protected_name("ID_RSA"));
        assert!(is_protected_name("Credentials.JSON"));
    }
}
