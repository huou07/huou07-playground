//! Explicit supported web-login exports; never harvest provider/native auth stores.
use serde_json::{json, Value};
use std::io::{Read, Write};
fn file(v: &Value) -> Result<Value, String> {
    let mut child = crate::helper::actor(v)?;
    let mut stdin = child.stdin.take().ok_or("Private NAS input unavailable")?;
    writeln!(stdin, "{v}").map_err(|_| "Private NAS request failed")?;
    drop(stdin);
    let mut bytes = Vec::new();
    child
        .stdout
        .take()
        .ok_or("Private NAS output unavailable")?
        .take(8193)
        .read_to_end(&mut bytes)
        .map_err(|_| "Private NAS response failed")?;
    let success = child
        .wait()
        .map_err(|_| "Private NAS actor failed")?
        .success();
    if bytes.len() > 8192 {
        return Err("Invalid private NAS response".into());
    }
    let response: Value =
        serde_json::from_slice(&bytes).map_err(|_| "Invalid private NAS response")?;
    if !success || response["ok"] != true {
        return Err(response["error"]
            .as_str()
            .unwrap_or("Private NAS operation failed")
            .into());
    }
    Ok(response["data"].clone())
}
pub(crate) fn document(entries: &Value) -> Result<Vec<u8>, String> {
    let entries = entries
        .as_array()
        .filter(|e| !e.is_empty() && e.len() <= 20)
        .ok_or("Choose one to twenty existing app logins")?;
    let mut out=String::from("# Apps login passwords\n\nPrivate owner NAS. This file contains selected existing web-app logins only.\nDelete it from NAS whenever you no longer want this copy. App authentication is unchanged.\nValues below use JSON string escaping. No API/provider keys are included.\n");
    let mut names = std::collections::BTreeSet::new();
    for entry in entries {
        let name = entry["name"]
            .as_str()
            .filter(|s| {
                !s.trim().is_empty() && s.chars().count() <= 60 && !s.chars().any(char::is_control)
            })
            .ok_or("Enter a valid app name")?;
        let username = entry["username"]
            .as_str()
            .filter(|s| s.len() <= 256 && !s.chars().any(char::is_control))
            .ok_or("Enter a valid existing username")?;
        let password = entry["password"]
            .as_str()
            .filter(|s| !s.is_empty() && s.len() <= 4096 && !s.chars().any(char::is_control))
            .ok_or("Enter a valid existing app password")?;
        if !names.insert(name.to_lowercase()) {
            return Err("App login names must be unique".into());
        }
        out.push_str("\n## App login\n\n```json\n");
        // Escape backticks so a password cannot escape its Markdown code block.
        out.push_str(
            &serde_json::to_string_pretty(
                &json!({"app":name,"username":username,"password":password}),
            )
            .map_err(|_| "Login encoding failed")?
            .replace('`', "\\u0060"),
        );
        out.push_str("\n```\n");
    }
    Ok(out.into_bytes())
}
pub(crate) fn exported_entries(bytes: &[u8]) -> Option<Vec<Value>> {
    let text = std::str::from_utf8(bytes).ok()?;
    let mut entries = Vec::new();
    for section in text.split("\n```json\n").skip(1) {
        let (block, _) = section.split_once("\n```\n")?;
        let entry: Value = serde_json::from_str(block).ok()?;
        entries.push(
            json!({"name":entry["app"],"username":entry["username"],"password":entry["password"]}),
        );
        if entries.len() > 20 {
            return None;
        }
    }
    // Preserve manually added notes/formatting: only our exact known format can merge.
    let mut canonical = document(&json!(entries)).ok()?;
    let exact = canonical == bytes;
    canonical.fill(0);
    exact.then_some(entries)
}
fn supported_public_login() -> Option<Value> {
    // Public bridge login only. Backend/provider/harness credentials are excluded.
    let (user, password) = crate::native_proxy::public_login()?;
    Some(json!({"name":"OpenCode public web / DSH LAN bridge","username":user,"password":password}))
}
pub fn control(op: &str, v: &Value) -> Result<Value, String> {
    match op {
        "app_logins_status" => {
            let status = file(&json!({"op":"fs_login_status","area":"nas"}))?;
            Ok(
                json!({"file":status,"sources":[{"id":"opencode-public","name":"OpenCode public web / DSH LAN bridge","available":supported_public_login().is_some(),"can_change":crate::native_proxy::credentials().is_some(),"description":"Existing public bridge login only; native backend and provider credentials excluded."}],"note":"Linux/Cockpit/PAM and other hash-only passwords cannot be recovered. Unsupported apps use manual entry or their existing administration page. Apps without passwords need no entry."}),
            )
        }
        "app_logins_change" => {
            if v["source"] != "opencode-public" {
                return Err("This app has no supported password-change adapter; use its existing administration page".into());
            }
            let (username, _) =
                crate::native_proxy::public_login().ok_or("No existing supported web login")?;
            crate::native_proxy::change_public_login(
                &username,
                v["password"].as_str().ok_or("Enter the new password")?,
            )?;
            Ok(
                json!({"changed":true,"credentials_returned":false,"scope":"OpenCode public web and DSH LAN bridge only. Native/provider credentials are unchanged. Existing login exports need an explicit refresh."}),
            )
        }
        "app_logins_save" => {
            let mut entries = v["entries"]
                .as_array()
                .cloned()
                .ok_or("Choose existing app logins")?;
            let selected = v["selected"]
                .as_array()
                .ok_or("Select supported login sources explicitly")?;
            let mut seen = std::collections::BTreeSet::new();
            for source in selected {
                let id = source.as_str().ok_or("Invalid login source")?;
                if !seen.insert(id) || id != "opencode-public" {
                    return Err("Unsupported or repeated login source".into());
                }
                entries.push(
                    supported_public_login()
                        .ok_or("This app has no supported existing login to export")?,
                );
            }
            // Validate before passing any secret into the NAS actor. No response returns it.
            let mut preview = document(&json!(entries))?;
            preview.fill(0);
            file(
                &json!({"op":"fs_login_save","area":"nas","entries":entries,"replace":v["replace"],"mode":v["mode"],"expected_version":v["expected_version"]}),
            )
        }
        _ => Err("Unsupported app-login action".into()),
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn selected_existing_login_document_is_bounded_and_markdown_safe() {
        let bytes =
            document(&json!([{"name":"Fixture","username":"owner","password":"fake```value"}]))
                .unwrap();
        let text = String::from_utf8(bytes).unwrap();
        assert!(text.contains("fake\\u0060\\u0060\\u0060value"));
        assert_eq!(text.matches("```").count(), 2);
        assert!(document(&json!([])).is_err());
        assert!(document(&json!([{"name":"Anonymous","username":"","password":""}])).is_err());
        assert!(document(&json!([{"name":"Bad\nname","username":"u","password":"p"}])).is_err());
        assert!(document(&json!([{"name":"a","username":"u","password":"p"},{"name":"A","username":"u","password":"p"}])).is_err());
    }
    #[test]
    fn only_exact_generated_login_documents_can_merge() {
        let entries = json!([{"name":"Fixture","username":"owner","password":"fake```value"}]);
        let mut bytes = document(&entries).unwrap();
        assert_eq!(exported_entries(&bytes), entries.as_array().cloned());
        bytes.extend_from_slice(b"\nOwner's manual notes\n");
        assert!(exported_entries(&bytes).is_none());
        assert!(exported_entries(b"unrecognized manual login file").is_none());
    }
}
