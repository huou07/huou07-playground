//! Bounded source redaction. Never emit a partial line before classification.
//! Known signatures/headers only: this is not proof that arbitrary text is safe.
use std::io::{Read, Write};
const MAX_LINE: usize = 16 * 1024;
const MASK: &[u8] = b"[H07P: secret-bearing log line redacted]\n";

#[derive(Default, Clone, Copy)]
pub struct Counts {
    pub lines: u64,
    pub redacted_lines: u64,
    pub oversized_lines: u64,
}

pub fn sensitive(bytes: &[u8]) -> bool {
    let lower = bytes.to_ascii_lowercase();
    let text = String::from_utf8_lossy(&lower);
    if text.contains("private key-----") || text.contains("bearer ") || text.contains("basic ") {
        return true;
    }
    for key in [
        "authorization",
        "api_key",
        "api-key",
        "apikey",
        "password",
        "refresh_token",
        "access_token",
        "client_secret",
        "secret_key",
        "cookie",
        "csrf",
        "token",
    ] {
        let mut rest = text.as_ref();
        while let Some(index) = rest.find(key) {
            let after = &rest[index + key.len()..];
            if after
                .trim_start_matches([' ', '\t', '"', '\''])
                .starts_with([':', '='])
            {
                return true;
            }
            rest = after;
        }
    }
    for prefix in [
        "sk-",
        "ghp_",
        "github_pat_",
        "xoxb-",
        "xoxp-",
        "akia",
        "asia",
    ] {
        let mut rest = text.as_ref();
        while let Some(index) = rest.find(prefix) {
            let boundary = index == 0 || !rest.as_bytes()[index - 1].is_ascii_alphanumeric();
            let after = &rest[index + prefix.len()..];
            if boundary
                && after
                    .bytes()
                    .take_while(|b| b.is_ascii_alphanumeric() || b"_-".contains(b))
                    .count()
                    >= 16
            {
                return true;
            }
            rest = after;
        }
    }
    // Authentication embedded in a URL is sensitive even without named headers.
    if let Some((_, tail)) = text.split_once("://") {
        if tail
            .split(['/', ' ', '\t'])
            .next()
            .is_some_and(|authority| authority.contains('@'))
        {
            return true;
        }
    }
    false
}

pub fn safe_path(path: &str) -> String {
    path.split('/')
        .map(|part| {
            if sensitive(part.as_bytes()) || part.chars().any(char::is_control) {
                "[redacted-name]"
            } else {
                part
            }
        })
        .collect::<Vec<_>>()
        .join("/")
}

fn finish<W: Write>(
    line: &mut Vec<u8>,
    output: &mut W,
    private: &mut bool,
    oversized: bool,
    counts: &mut Counts,
) -> std::io::Result<()> {
    counts.lines += 1;
    let lower = line.to_ascii_lowercase();
    let begin = lower.windows(10).any(|s| s == b"-----begin")
        && lower.windows(11).any(|s| s == b"private key");
    let end = lower.windows(8).any(|s| s == b"-----end")
        && lower.windows(11).any(|s| s == b"private key");
    let hide = *private
        || begin
        || oversized
        || line.contains(&0)
        || std::str::from_utf8(line).is_err()
        || sensitive(line);
    if hide {
        output.write_all(MASK)?;
        counts.redacted_lines += 1;
    } else {
        output.write_all(line)?;
    }
    if begin {
        *private = true;
    }
    // A header after the retained prefix of an oversized line cannot be safely
    // classified. Keep subsequent output masked until a recognized end marker.
    if oversized {
        *private = true;
    }
    if end {
        *private = false;
    }
    if oversized {
        counts.oversized_lines += 1;
    }
    line.fill(0);
    line.clear();
    output.flush()
}

pub fn stream<R: Read, W: Write>(mut input: R, mut output: W) -> std::io::Result<Counts> {
    let mut counts = Counts::default();
    let mut line = Vec::with_capacity(MAX_LINE);
    let mut private = false;
    let mut oversized = false;
    let mut block = [0; 4096];
    loop {
        let n = input.read(&mut block)?;
        if n == 0 {
            break;
        }
        for byte in &block[..n] {
            if line.len() < MAX_LINE {
                line.push(*byte);
            } else {
                oversized = true;
            }
            if *byte == b'\n' {
                finish(&mut line, &mut output, &mut private, oversized, &mut counts)?;
                oversized = false;
            }
        }
        block[..n].fill(0);
    }
    if !line.is_empty() || oversized {
        finish(&mut line, &mut output, &mut private, oversized, &mut counts)?;
    }
    Ok(counts)
}

pub fn clean(input: &[u8]) -> Result<(Vec<u8>, Counts), String> {
    if input.len() > 1024 * 1024 {
        return Err("Log export exceeds 1 MiB; split or export a smaller closed log".into());
    }
    if std::str::from_utf8(input).is_err() || input.contains(&0) {
        return Err("Only UTF-8 text log exports can be cleaned".into());
    }
    let mut output = Vec::new();
    let counts =
        stream(std::io::Cursor::new(input), &mut output).map_err(|_| "Log redaction failed")?;
    Ok((output, counts))
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Bytes {
        data: Vec<u8>,
        at: usize,
    }
    impl Read for Bytes {
        fn read(&mut self, output: &mut [u8]) -> std::io::Result<usize> {
            if self.at == self.data.len() {
                return Ok(0);
            }
            output[0] = self.data[self.at];
            self.at += 1;
            Ok(1)
        }
    }
    #[test]
    fn secrets_crossing_every_chunk_boundary_never_escape() {
        let input=b"ordinary startup\nAuthorization: Bearer fake-sensitive-value\napi_key=synthetic-other-value\nnormal end\n";
        let mut output = Vec::new();
        let counts = stream(
            Bytes {
                data: input.to_vec(),
                at: 0,
            },
            &mut output,
        )
        .unwrap();
        assert_eq!(counts.redacted_lines, 2);
        let result = String::from_utf8(output).unwrap();
        assert!(result.contains("ordinary startup"));
        assert!(result.contains("normal end"));
        assert!(!result.contains("fake-sensitive-value"));
        assert!(!result.contains("synthetic-other-value"));
    }
    #[test]
    fn private_key_blocks_and_large_lines_are_not_partially_emitted() {
        let mut input =
            b"-----BEGIN PRIVATE KEY-----\nsynthetic-key-body\n-----END PRIVATE KEY-----\n"
                .to_vec();
        input.extend(vec![b'a'; MAX_LINE + 1]);
        input.push(b'\n');
        let (output, counts) = clean(&input).unwrap();
        assert_eq!(counts.redacted_lines, 4);
        assert_eq!(counts.oversized_lines, 1);
        assert!(!String::from_utf8(output)
            .unwrap()
            .contains("synthetic-key-body"));
    }
    #[test]
    fn ordinary_unicode_and_nonsecret_hashes_are_preserved() {
        let input = "Khởi động thành công\nbuild_hash=0123456789abcdef0123456789abcdef\n";
        let (output, counts) = clean(input.as_bytes()).unwrap();
        assert_eq!(output, input.as_bytes());
        assert_eq!(counts.redacted_lines, 0);
    }
    #[test]
    fn binary_exports_fail_and_secret_names_are_hidden() {
        assert!(clean(b"log\0binary").is_err());
        assert_eq!(
            safe_path("/logs/api_key=synthetic-secret.log"),
            "/logs/[redacted-name]"
        );
    }
}
