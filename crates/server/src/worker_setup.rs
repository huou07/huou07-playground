//! Fixed harness catalog and owner-reviewed, serialized account maintenance jobs.
use serde_json::{json, Value};
use std::{
    fs,
    sync::{Arc, Mutex, OnceLock},
};
fn job() -> &'static Mutex<Value> {
    static JOB: OnceLock<Mutex<Value>> = OnceLock::new();
    JOB.get_or_init(|| Mutex::new(json!({"state":"idle"})))
}
pub fn catalog() -> Result<Value, String> {
    let policy = crate::helper::load()?;
    let passwd = fs::read_to_string("/etc/passwd").map_err(|_| "Account metadata unavailable")?;
    let workers:Vec<_>=crate::helper::workers().iter().map(|name|{
        let harness=name.trim_end_matches("-worker");
        let executable=match harness {"dsh"=>"/home/huou07/.local/bin/dsh","codex"=>"/home/huou07/.local/bin/codex",_=>"/home/huou07/.local/bin/opencode"};
        let fields=passwd.lines().find_map(|line|{let fields:Vec<_>=line.split(':').collect();(fields.len()==7&&fields[0]==*name).then_some(fields)});
        let account=crate::user_ids(name).ok();
        let setting=crate::helper::worker_setting(&policy,name);
        json!({"name":name,"harness":harness,"detected":fs::metadata(executable).map(|m|{use std::os::unix::fs::PermissionsExt;m.is_file()&&m.permissions().mode()&0o111!=0}).unwrap_or(false),"account_exists":account.is_some(),"uid":account.map(|a|a.0),"home":fields.as_ref().map(|f|f[5]),"preset":setting["preset"],"workspace":setting["workspace"],"enabled":setting["enabled"]})
    }).collect();
    Ok(
        json!({"workers":workers,"revision":policy["revision"],"job":job().lock().unwrap_or_else(|e|e.into_inner()).clone(),"note":"Detects supported installed harness executables without running them. Shared apps/home are reused. Removal retains shared data and a locked retired UID to prevent permission reuse."}),
    )
}
pub fn control(op: &str, v: &Value, lock: Arc<Mutex<()>>) -> Result<Value, String> {
    match op {
        "worker_setup_status" => catalog(),
        "worker_setup_job" => Ok(job().lock().unwrap_or_else(|e| e.into_inner()).clone()),
        "worker_setup_run" => {
            let action = v["action"].as_str().ok_or("Select a worker action")?;
            if !["create", "repair", "remove", "start-web"].contains(&action) {
                return Err("Unsupported worker action".into());
            }
            let workers = v["workers"]
                .as_array()
                .filter(|s| !s.is_empty() && s.len() <= 3)
                .ok_or("Select one or more supported workers")?;
            let mut unique = std::collections::BTreeSet::new();
            for worker in workers {
                let name = worker.as_str().ok_or("Invalid worker")?;
                if !crate::helper::workers().contains(&name) || !unique.insert(name) {
                    return Err("Choose distinct supported worker accounts".into());
                }
            }
            if v["confirmed"] != true {
                return Err("Review and confirm the selected account changes".into());
            }
            let id = crate::random_token()?;
            let mut current = job().lock().unwrap_or_else(|e| e.into_inner());
            if current["state"] == "running" {
                return Err("Worker maintenance is already running. Wait for its result.".into());
            }
            *current = json!({"id":id,"state":"running","action":action,"workers":workers,"started_at":crate::now()});
            let request = v.clone();
            let job_id = id.clone();
            std::thread::spawn(move || {
                let _guard = lock.lock().unwrap_or_else(|e| e.into_inner());
                let result = crate::helper::maintain_workers(&request);
                let mut record = job().lock().unwrap_or_else(|e| e.into_inner());
                record["state"] = json!(if result.is_ok() {
                    "completed"
                } else {
                    "failed"
                });
                record["finished_at"] = json!(crate::now());
                record["result"] = match result {
                    Ok(value) => value,
                    Err(error) => json!({"error":error}),
                };
                record["id"] = json!(job_id);
            });
            Ok(current.clone())
        }
        _ => Err("Unknown worker setup operation".into()),
    }
}
pub(crate) fn driver(action: &str, workers: &[Value]) -> Result<(), String> {
    let path = std::env::var("H07P_WORKER_SETUP")
        .unwrap_or_else(|_| "/usr/lib/huou07-playground/workers.py".into());
    let metadata = fs::symlink_metadata(&path)
        .map_err(|_| "Worker setup adapter is missing. Repair the installed package.")?;
    use std::os::unix::fs::MetadataExt;
    if !metadata.is_file() || metadata.uid() != 0 || metadata.mode() & 0o022 != 0 {
        return Err("Worker setup adapter must be root-owned and protected".into());
    }
    for parent in std::path::Path::new(&path).ancestors().skip(1) {
        let m =
            fs::symlink_metadata(parent).map_err(|_| "Cannot verify worker setup installation")?;
        if !m.is_dir() || m.uid() != 0 || m.mode() & 0o022 != 0 {
            return Err("Worker setup adapter has an unprotected ancestor".into());
        }
    }
    let control = crate::helper::dir();
    let control = control.to_str().ok_or("Invalid control path")?;
    let mut arguments = vec![path.as_str(), action, "--control-dir", control];
    for worker in workers {
        arguments.push(worker.as_str().ok_or("Invalid worker")?);
    }
    crate::telemetry::command("/usr/bin/python3",&arguments,300).ok_or_else(||"Account/ACL setup failed or exceeded its bound. Affected workers remain stopped; use Repair and inspect the protected ACL backup.".into()).map(|_|())
}
