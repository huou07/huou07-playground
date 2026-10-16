//! Descriptor-relative file adapter, executed as the owner's or NAS service UID.
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::ffi::CString;
use std::fs::File;
use std::io::{BufRead, Read, Seek, SeekFrom, Write};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::MetadataExt;
use std::path::{Component, Path};

type Result<T> = std::result::Result<T, String>;
pub static RESPONSE_STARTED: std::sync::atomic::AtomicBool =
    std::sync::atomic::AtomicBool::new(false);
fn io(e: std::io::Error) -> String {
    e.to_string()
}
fn c(s: &str) -> Result<CString> {
    CString::new(s).map_err(|_| "Invalid name".into())
}
fn open_at(dir: &File, name: &str, flags: i32, mode: u32) -> Result<File> {
    let name = c(name)?;
    let fd = unsafe {
        libc::openat(
            dir.as_raw_fd(),
            name.as_ptr(),
            flags | libc::O_NOFOLLOW | libc::O_CLOEXEC,
            mode,
        )
    };
    if fd < 0 {
        Err(io(std::io::Error::last_os_error()))
    } else {
        Ok(unsafe { File::from_raw_fd(fd) })
    }
}
fn parts(path: &str) -> Result<Vec<String>> {
    if path.len() > 4096 || path.chars().any(char::is_control) {
        return Err("Invalid path".into());
    }
    Path::new(path)
        .components()
        .filter_map(|p| match p {
            Component::RootDir | Component::CurDir => None,
            Component::Normal(s) => Some(
                s.to_str()
                    .map(str::to_owned)
                    .ok_or_else(|| "Path must be UTF-8".into()),
            ),
            _ => Some(Err("Parent traversal is not allowed".into())),
        })
        .collect()
}
fn root(area: &str) -> Result<File> {
    let path = match area {
        "nas" => {
            std::env::var("H07P_NAS_DIR").unwrap_or_else(|_| "/var/lib/h07p-private/nas".into())
        }
        "storage" => "/".into(),
        _ => return Err("Unknown file area".into()),
    };
    let path = c(&path)?;
    let fd = unsafe {
        libc::open(
            path.as_ptr(),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        return Err(io(std::io::Error::last_os_error()));
    }
    Ok(unsafe { File::from_raw_fd(fd) })
}
fn directory(area: &str, path: &str) -> Result<File> {
    let mut dir = root(area)?;
    for p in parts(path)? {
        dir = open_at(&dir, &p, libc::O_RDONLY | libc::O_DIRECTORY, 0)?;
    }
    Ok(dir)
}
fn parent(area: &str, path: &str) -> Result<(File, String)> {
    let mut ps = parts(path)?;
    let leaf = ps.pop().ok_or("Cannot modify a file-area root")?;
    let mut dir = root(area)?;
    for p in ps {
        dir = open_at(&dir, &p, libc::O_RDONLY | libc::O_DIRECTORY, 0)?;
    }
    Ok((dir, leaf))
}
fn stat_at(dir: &File, name: &str) -> Result<libc::stat> {
    let mut st = unsafe { std::mem::zeroed() };
    if unsafe {
        libc::fstatat(
            dir.as_raw_fd(),
            c(name)?.as_ptr(),
            &mut st,
            libc::AT_SYMLINK_NOFOLLOW,
        )
    } != 0
    {
        return Err(io(std::io::Error::last_os_error()));
    }
    Ok(st)
}
fn names(dir: &File) -> Result<Vec<String>> {
    let fd = unsafe { libc::dup(dir.as_raw_fd()) };
    if fd < 0 {
        return Err(io(std::io::Error::last_os_error()));
    }
    let stream = unsafe { libc::fdopendir(fd) };
    if stream.is_null() {
        unsafe { libc::close(fd) };
        return Err(io(std::io::Error::last_os_error()));
    }
    let mut result = Vec::new();
    loop {
        let entry = unsafe { libc::readdir(stream) };
        if entry.is_null() {
            break;
        }
        let name = unsafe { std::ffi::CStr::from_ptr((*entry).d_name.as_ptr()) }
            .to_string_lossy()
            .into_owned();
        if name != "." && name != ".." {
            // Hide an active transfer, but expose an abandoned upload for owner
            // recovery after a crash. Never silently delete retained data.
            let active = temporary_name(&name)
                && open_at(dir, &name, libc::O_RDONLY | libc::O_NONBLOCK, 0).is_ok_and(
                    |f| unsafe { libc::flock(f.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0,
                );
            if !active {
                result.push(name);
            }
        }
        if result.len() > 100_000 {
            unsafe { libc::closedir(stream) };
            return Err("Directory is too large; select a smaller scope".into());
        }
    }
    unsafe { libc::closedir(stream) };
    result.sort_by_key(|a| a.to_lowercase());
    Ok(result)
}
fn temporary_name(name: &str) -> bool {
    name.strip_prefix(".h07p-upload-")
        .is_some_and(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit()))
}
fn capacity(dir: &File) -> Result<Value> {
    let mut s: libc::statvfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatvfs(dir.as_raw_fd(), &mut s) } != 0 {
        return Err(io(std::io::Error::last_os_error()));
    }
    let total = s.f_blocks * s.f_frsize;
    let free = s.f_bfree * s.f_frsize;
    Ok(
        json!({"total":total,"free":free,"available":s.f_bavail*s.f_frsize,"used":total-free,"sampled_at":crate::now(),"units":"bytes"}),
    )
}
fn mime(name: &str) -> &'static str {
    match name
        .rsplit('.')
        .next()
        .unwrap_or("")
        .to_lowercase()
        .as_str()
    {
        "txt" | "md" | "rs" | "py" | "js" | "css" | "json" | "toml" | "yaml" | "yml" | "log"
        | "csv" | "conf" | "ini" | "sh" => "text/plain; charset=utf-8",
        "avif" => "image/avif",
        "bmp" => "image/bmp",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "gif" => "image/gif",
        "webp" => "image/webp",
        "mp4" | "m4v" => "video/mp4",
        "mov" => "video/quicktime",
        "webm" => "video/webm",
        "ogg" => "video/ogg",
        _ => "application/octet-stream",
    }
}
fn unlink(dir: &File, name: &str, directory: bool) -> Result<()> {
    if unsafe {
        libc::unlinkat(
            dir.as_raw_fd(),
            c(name)?.as_ptr(),
            if directory { libc::AT_REMOVEDIR } else { 0 },
        )
    } != 0
    {
        Err(io(std::io::Error::last_os_error()))
    } else {
        Ok(())
    }
}
fn mkdir(dir: &File, name: &str) -> Result<()> {
    if unsafe { libc::mkdirat(dir.as_raw_fd(), c(name)?.as_ptr(), 0o770) } != 0 {
        Err(io(std::io::Error::last_os_error()))
    } else {
        Ok(())
    }
}
fn rename(src: &File, name: &str, dst: &File, dest: &str) -> Result<()> {
    #[cfg(target_os = "linux")]
    let result = unsafe {
        libc::syscall(
            libc::SYS_renameat2,
            src.as_raw_fd(),
            c(name)?.as_ptr(),
            dst.as_raw_fd(),
            c(dest)?.as_ptr(),
            libc::RENAME_NOREPLACE,
        )
    };
    #[cfg(not(target_os = "linux"))]
    let result = -1;
    if result != 0 {
        Err(io(std::io::Error::last_os_error()))
    } else {
        Ok(())
    }
}
fn copy_entry(
    src: &File,
    name: &str,
    dst: &File,
    dest: &str,
    depth: usize,
    count: &mut usize,
) -> Result<()> {
    *count += 1;
    if depth > 32 || *count > 10_000 {
        return Err("Copy limit reached; use smaller batches".into());
    }
    let st = stat_at(src, name)?;
    if st.st_mode & libc::S_IFMT == libc::S_IFDIR {
        mkdir(dst, dest)?;
        let a = open_at(src, name, libc::O_RDONLY | libc::O_DIRECTORY, 0)?;
        let b = open_at(dst, dest, libc::O_RDONLY | libc::O_DIRECTORY, 0)?;
        for item in names(&a)? {
            copy_entry(&a, &item, &b, &item, depth + 1, count)?;
        }
        b.sync_all().map_err(io)?;
        return Ok(());
    }
    if st.st_mode & libc::S_IFMT != libc::S_IFREG {
        return Err("Copy of symlinks/devices is not supported".into());
    }
    let mut input = open_at(src, name, libc::O_RDONLY | libc::O_NONBLOCK, 0)?;
    let before = input.metadata().map_err(io)?;
    if !before.is_file() || before.dev() != st.st_dev || before.ino() != st.st_ino {
        return Err("Copy source changed before it could be opened".into());
    }
    let mut output = open_at(
        dst,
        dest,
        libc::O_RDWR | libc::O_CREAT | libc::O_EXCL,
        0o660,
    )?;
    let result: Result<()> = (|| {
        let mut hash = Sha256::new();
        let mut buf = [0; 65536];
        let mut bytes = 0u64;
        loop {
            let n = input.read(&mut buf).map_err(io)?;
            if n == 0 {
                break;
            }
            bytes += n as u64;
            if bytes > 16 * 1024 * 1024 * 1024 {
                return Err("File exceeds copy budget".into());
            }
            hash.update(&buf[..n]);
            output.write_all(&buf[..n]).map_err(io)?;
        }
        output.sync_all().map_err(io)?;
        output.seek(SeekFrom::Start(0)).map_err(io)?;
        let mut verify = Sha256::new();
        loop {
            let n = output.read(&mut buf).map_err(io)?;
            if n == 0 {
                break;
            }
            verify.update(&buf[..n]);
        }
        let after = input.metadata().map_err(io)?;
        if hash.finalize() != verify.finalize()
            || before.len() != after.len()
            || before.mtime() != after.mtime()
            || before.mtime_nsec() != after.mtime_nsec()
            || before.ctime() != after.ctime()
            || before.ctime_nsec() != after.ctime_nsec()
        {
            return Err("Source changed during copy; source retained".into());
        }
        dst.sync_all().map_err(io)?;
        Ok(())
    })();
    result
        .map_err(|error| format!("{error}; a partial destination may remain for owner inspection"))
}
fn remove_entry(dir: &File, name: &str, depth: usize) -> Result<()> {
    if depth > 32 {
        return Err("Delete depth limit reached".into());
    }
    let st = stat_at(dir, name)?;
    let is_dir = st.st_mode & libc::S_IFMT == libc::S_IFDIR;
    if is_dir {
        let sub = open_at(dir, name, libc::O_RDONLY | libc::O_DIRECTORY, 0)?;
        for entry in names(&sub)? {
            remove_entry(&sub, &entry, depth + 1)?;
        }
    }
    unlink(dir, name, is_dir)
}
fn expected(file: &File, request: &Value, parent: bool) -> Result<()> {
    let m = file.metadata().map_err(io)?;
    let (dev, ino) = if parent {
        ("expected_parent_dev", "expected_parent_ino")
    } else {
        ("expected_dev", "expected_ino")
    };
    if request[dev].as_u64() != Some(m.dev()) || request[ino].as_u64() != Some(m.ino()) {
        return Err("Approved object changed".into());
    }
    let (ctime, nanos) = if parent {
        ("expected_parent_ctime", "expected_parent_ctime_nsec")
    } else {
        ("expected_ctime", "expected_ctime_nsec")
    };
    if request[ctime].as_i64().is_some_and(|v| v != m.ctime())
        || request[nanos].as_i64().is_some_and(|v| v != m.ctime_nsec())
    {
        return Err("Approved object changed".into());
    }
    Ok(())
}
fn replace_from_input(
    dir: &File,
    name: &str,
    request: &Value,
    input: &mut impl Read,
    length: u64,
    private_result: bool,
) -> Result<()> {
    let original = open_at(dir, name, libc::O_WRONLY | libc::O_NONBLOCK, 0)?;
    expected(&original, request, false)?;
    let old = original.metadata().map_err(io)?;
    if !old.is_file() || old.nlink() != 1 || old.uid() != unsafe { libc::geteuid() } {
        return Err("Replace requires one owner-owned non-aliased regular file".into());
    }
    let stage = format!(".h07p-replace-{}", crate::random_token()?);
    if unsafe { libc::mkdirat(dir.as_raw_fd(), c(&stage)?.as_ptr(), 0o700) } != 0 {
        return Err(io(std::io::Error::last_os_error()));
    }
    let private = open_at(dir, &stage, libc::O_RDONLY | libc::O_DIRECTORY, 0)?;
    if private.metadata().map_err(io)?.uid() != old.uid() {
        return Err("Private staging directory changed".into());
    }
    let mut retain_recovery = false;
    let result = (|| {
        let mut file = open_at(
            &private,
            "replacement",
            libc::O_RDWR | libc::O_CREAT | libc::O_EXCL,
            0o600,
        )?;
        let copied = std::io::copy(&mut input.take(length), &mut file).map_err(io)?;
        if copied != length {
            return Err("Replacement interrupted; original retained".into());
        }
        // Do not inherit a broader directory ACL. A normal broker write preserves
        // the original ACL/group; cleaned log exports deliberately become private.
        if unsafe { libc::fremovexattr(file.as_raw_fd(), c"system.posix_acl_access".as_ptr()) } != 0
            && !matches!(
                std::io::Error::last_os_error().raw_os_error(),
                Some(libc::ENODATA | libc::EOPNOTSUPP)
            )
        {
            return Err("Could not clear inherited staging ACL".into());
        }
        if !private_result {
            if file.metadata().map_err(io)?.gid() != old.gid()
                && unsafe { libc::fchown(file.as_raw_fd(), u32::MAX, old.gid()) } != 0
            {
                return Err("Cannot preserve the original file group".into());
            }
            let mut acl = vec![0u8; 65536];
            let n = unsafe {
                libc::fgetxattr(
                    original.as_raw_fd(),
                    c"system.posix_acl_access".as_ptr(),
                    acl.as_mut_ptr() as *mut _,
                    acl.len(),
                )
            };
            if n > 0
                && unsafe {
                    libc::fsetxattr(
                        file.as_raw_fd(),
                        c"system.posix_acl_access".as_ptr(),
                        acl.as_ptr() as *const _,
                        n as usize,
                        0,
                    )
                } != 0
            {
                return Err("Could not preserve the original ACL".into());
            }
            if n < 0 && std::io::Error::last_os_error().raw_os_error() != Some(libc::ENODATA) {
                return Err("Could not inspect the original ACL".into());
            }
        }
        if unsafe {
            libc::fchmod(
                file.as_raw_fd(),
                if private_result {
                    0o600
                } else {
                    old.mode() & 0o777
                },
            )
        } != 0
        {
            return Err(io(std::io::Error::last_os_error()));
        }
        file.sync_all().map_err(io)?;
        expected(&original, request, false)?;
        // Keep a stable name CString alive across the syscall.
        let target = c(name)?;
        let rc = unsafe {
            libc::syscall(
                libc::SYS_renameat2,
                private.as_raw_fd(),
                c"replacement".as_ptr(),
                dir.as_raw_fd(),
                target.as_ptr(),
                libc::RENAME_EXCHANGE,
            )
        };
        if rc != 0 {
            return Err(io(std::io::Error::last_os_error()));
        }
        retain_recovery = true;
        let moved = stat_at(&private, "replacement")?;
        if moved.st_dev != old.dev() || moved.st_ino != old.ino() {
            let _ = unsafe {
                libc::syscall(
                    libc::SYS_renameat2,
                    private.as_raw_fd(),
                    c"replacement".as_ptr(),
                    dir.as_raw_fd(),
                    target.as_ptr(),
                    libc::RENAME_EXCHANGE,
                )
            };
            return Err(format!("Target changed; retained recovery data in {stage}"));
        }
        dir.sync_all().map_err(io)?;
        unlink(&private, "replacement", false)?;
        retain_recovery = false;
        Ok(())
    })();
    if result.is_err() && !retain_recovery {
        let _ = unlink(&private, "replacement", false);
    }
    let _ = unlink(dir, &stage, true);
    result
}
fn broker_mutate(area: &str, path: &str, op: &str, request: &Value) -> Result<()> {
    let (dir, name) = parent(area, path)?;
    if op == "fs_broker_create" || op == "fs_broker_delete" {
        expected(&dir, request, true)?;
    }
    if op == "fs_broker_delete" {
        // Keep the approved inode open across rename so it cannot be recycled.
        let original = open_at(&dir, &name, libc::O_RDONLY | libc::O_NONBLOCK, 0)?;
        expected(&original, request, false)?;
        let quarantine = format!(".h07p-delete-{}", crate::random_token()?);
        if unsafe { libc::mkdirat(dir.as_raw_fd(), c(&quarantine)?.as_ptr(), 0o700) } != 0 {
            return Err(io(std::io::Error::last_os_error()));
        }
        let private = open_at(&dir, &quarantine, libc::O_RDONLY | libc::O_DIRECTORY, 0)?;
        if private.metadata().map_err(io)?.uid() != unsafe { libc::geteuid() } {
            return Err("Private staging directory changed".into());
        }
        rename(&dir, &name, &private, "target")?;
        let moved = open_at(&private, "target", libc::O_RDONLY | libc::O_NONBLOCK, 0);
        let checked = moved.and_then(|file| {
            let m = file.metadata().map_err(io)?;
            let original_meta = original.metadata().map_err(io)?;
            if m.dev() != original_meta.dev() || m.ino() != original_meta.ino() {
                return Err("Approved object changed".into());
            }
            if !m.is_file() || m.nlink() != 1 {
                return Err("Only one non-aliased regular file may be deleted".into());
            }
            Ok(())
        });
        if let Err(error) = checked {
            return match rename(&private, "target", &dir, &name) {
                Ok(()) => {
                    let _ = unlink(&dir, &quarantine, true);
                    Err(error)
                }
                Err(_) => Err(format!(
                    "{error}; recover the retained object at {quarantine}/target"
                )),
            };
        }
        unlink(&private, "target", false)?;
        let _ = unlink(&dir, &quarantine, true);
    } else {
        let content = request["content"]
            .as_str()
            .ok_or("Missing approved content")?
            .as_bytes();
        if content.len() > 65536 {
            return Err("Approved write exceeds 64 KiB".into());
        }
        if op == "fs_broker_create" {
            let stage = format!(".h07p-create-{}", crate::random_token()?);
            if unsafe { libc::mkdirat(dir.as_raw_fd(), c(&stage)?.as_ptr(), 0o700) } != 0 {
                return Err(io(std::io::Error::last_os_error()));
            }
            let private = open_at(&dir, &stage, libc::O_RDONLY | libc::O_DIRECTORY, 0)?;
            if private.metadata().map_err(io)?.uid() != unsafe { libc::geteuid() } {
                return Err("Private staging directory changed".into());
            }
            let mut file = open_at(
                &private,
                "target",
                libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL,
                0o600,
            )?;
            let result = file
                .write_all(content)
                .and_then(|_| file.sync_all())
                .map_err(io);
            if result.is_err() {
                let _ = unlink(&private, "target", false);
                let _ = unlink(&dir, &stage, true);
            }
            result?;
            let result = rename(&private, "target", &dir, &name);
            if result.is_err() {
                let _ = unlink(&private, "target", false);
            }
            let _ = unlink(&dir, &stage, true);
            result?;
        } else {
            replace_from_input(
                &dir,
                &name,
                request,
                &mut std::io::Cursor::new(content),
                content.len() as u64,
                false,
            )?;
        }
    }
    dir.sync_all().map_err(io)
}
pub fn actor() -> Result<()> {
    let stdin = std::io::stdin();
    let mut input = stdin.lock();
    let mut line = String::new();
    input
        .by_ref()
        .take(131073)
        .read_line(&mut line)
        .map_err(io)?;
    if line.len() > 131072 {
        return Err("Request too large".into());
    }
    let request: Value = serde_json::from_str(&line).map_err(|_| "Invalid file request")?;
    let area = request["area"].as_str().unwrap_or("nas");
    let path = request["path"].as_str().unwrap_or("/");
    let op = request["op"].as_str().unwrap_or("");
    match op {
        "fs_guard_replace" => {
            let length = request["length"]
                .as_u64()
                .filter(|n| *n <= 1024 * 1024)
                .ok_or("Replacement exceeds 1 MiB")?;
            let (dir, name) = parent(area, path)?;
            replace_from_input(&dir, &name, &request, &mut input, length, true)?;
            println!("{}", json!({"ok":true,"data":{"ok":true,"bytes":length}}));
        }
        "fs_broker_write" | "fs_broker_create" | "fs_broker_delete" => {
            broker_mutate(area, path, op, &request)?;
            println!("{}", json!({"ok":true,"data":{"ok":true}}));
        }
        "fs_list" | "fs_broker_list" => {
            let dir = directory(area, path)?;
            if op == "fs_broker_list" {
                expected(&dir, &request, false)?;
            }
            let all = names(&dir)?;
            let offset = request["offset"].as_u64().unwrap_or(0) as usize;
            let mut entries = Vec::new();
            for name in all.iter().skip(offset).take(500) {
                if let Ok(st) = stat_at(&dir, name) {
                    let mode = st.st_mode & libc::S_IFMT;
                    entries.push(json!({"name":name,"path":format!("{}/{}",path.trim_end_matches('/'),name),"kind":if mode==libc::S_IFDIR{"directory"}else if mode==libc::S_IFREG{"file"}else if mode==libc::S_IFLNK{"symlink"}else{"other"},"size":st.st_size,"modified":st.st_mtime,"temporary":temporary_name(name)}));
                }
            }
            let mut p = parts(path)?;
            p.pop();
            println!(
                "{}",
                json!({"ok":true,"data":{"path":path,"parent":format!("/{}",p.join("/")),"entries":entries,"total":all.len(),"capacity":capacity(&dir)?,"private":area=="nas"}})
            );
        }
        "fs_read" => {
            let (dir, name) = parent(area, path)?;
            let mut file = open_at(&dir, &name, libc::O_RDONLY | libc::O_NONBLOCK, 0)?;
            let metadata = file.metadata().map_err(io)?;
            if !metadata.is_file() {
                return Err("Only regular files can be downloaded".into());
            }
            if request["expected_dev"].is_u64() {
                expected(&file, &request, false)?;
            }
            if request["expected_dev"]
                .as_u64()
                .is_some_and(|v| v != metadata.dev())
                || request["expected_ino"]
                    .as_u64()
                    .is_some_and(|v| v != metadata.ino())
            {
                return Err("Approved object changed".into());
            }
            let size = metadata.len();
            let preview = request["preview"].as_bool().unwrap_or(false);
            let content = mime(&name);
            if preview && content == "application/octet-stream" {
                return Err("Unsupported preview; use Download".into());
            }
            if preview && content.starts_with("image/") && size > 20 * 1024 * 1024 {
                return Err("Image preview exceeds 20 MiB".into());
            }
            let start = request["start"].as_u64().unwrap_or(0);
            if start > size {
                return Err("Invalid range".into());
            }
            let mut length = request["length"]
                .as_u64()
                .unwrap_or(size - start)
                .min(size - start);
            if preview && content.starts_with("text/") {
                length = length.min(256 * 1024);
            }
            RESPONSE_STARTED.store(true, std::sync::atomic::Ordering::SeqCst);
            println!(
                "{}",
                json!({"ok":true,"data":{"size":size,"start":start,"length":length,"content_type":content,"filename":name,"truncated":length<size && content.starts_with("text/"),"expected_dev":metadata.dev(),"expected_ino":metadata.ino(),"expected_ctime":metadata.ctime(),"expected_ctime_nsec":metadata.ctime_nsec()}})
            );
            std::io::stdout().flush().map_err(io)?;
            file.seek(SeekFrom::Start(start)).map_err(io)?;
            std::io::copy(&mut file.take(length), &mut std::io::stdout()).map_err(io)?;
        }
        "fs_upload" => {
            let length = request["length"]
                .as_u64()
                .ok_or("Content-Length is required")?;
            if length > 512 * 1024 * 1024 {
                return Err("Upload exceeds 512 MiB".into());
            }
            let (dir, name) = parent(area, path)?;
            if stat_at(&dir, &name).is_ok() {
                return Err("Destination exists; overwrite is never implicit".into());
            }
            let temp = format!(".h07p-upload-{}", crate::random_token()?);
            let mut file = open_at(
                &dir,
                &temp,
                libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL,
                if area == "nas" { 0o640 } else { 0o660 },
            )?;
            if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
                return Err("Could not lock upload staging file".into());
            }
            let result: Result<()> = (|| {
                let actual = std::io::copy(&mut input.take(length), &mut file).map_err(io)?;
                if actual != length {
                    return Err("Upload interrupted; temporary file removed".into());
                }
                file.sync_all().map_err(io)?;
                rename(&dir, &temp, &dir, &name)?;
                dir.sync_all().map_err(io)?;
                Ok(())
            })();
            if result.is_err() {
                let _ = unlink(&dir, &temp, false);
            }
            result?;
            println!("{}", json!({"ok":true,"data":{"ok":true,"bytes":length}}));
        }
        "fs_mutate" => {
            let action = request["action"].as_str().unwrap_or("");
            let (src, name) = parent(area, path)?;
            match action {
                "mkdir" => mkdir(&src, &name)?,
                "delete" => {
                    if request["confirmed"] != true {
                        return Err("Permanent deletion requires explicit confirmation".into());
                    }
                    remove_entry(&src, &name, 0)?;
                }
                "rename" | "copy" | "move" => {
                    let dest = request["destination"]
                        .as_str()
                        .ok_or("Destination is required")?;
                    if parts(dest)?.starts_with(&parts(path)?) {
                        return Err("Cannot copy or move into itself".into());
                    }
                    let (dst, destname) = parent(area, dest)?;
                    if action == "copy" {
                        copy_entry(&src, &name, &dst, &destname, 0, &mut 0)?;
                    } else if let Err(error) = rename(&src, &name, &dst, &destname) {
                        if action != "move"
                            || !error.contains("cross-device") && !error.contains("Cross-device")
                        {
                            return Err(error);
                        }
                        let before = stat_at(&src, &name)?;
                        copy_entry(&src, &name, &dst, &destname, 0, &mut 0)?;
                        let after = stat_at(&src, &name)?;
                        if before.st_ino != after.st_ino || before.st_mtime != after.st_mtime {
                            return Err(
                                "Source changed; copied destination and original retained".into()
                            );
                        }
                        remove_entry(&src, &name, 0)?;
                    }
                }
                _ => return Err("Unsupported file operation".into()),
            }
            src.sync_all().map_err(io)?;
            println!("{}", json!({"ok":true,"data":{"ok":true}}));
        }
        _ => return Err("Unsupported file operation".into()),
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_traversal_and_control_characters() {
        assert!(parts("/a/../secret").is_err());
        assert!(parts("/a\nheader").is_err());
        assert_eq!(parts("/a/b").unwrap(), vec!["a", "b"]);
    }
    #[test]
    fn active_content_never_has_inline_mime() {
        assert_eq!(mime("attack.svg"), "application/octet-stream");
        assert_eq!(mime("attack.html"), "application/octet-stream");
        assert_eq!(mime("clip.mp4"), "video/mp4");
    }
}
