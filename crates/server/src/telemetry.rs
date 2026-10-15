//! Native Linux dashboard APIs. Mount only behind the owner's authentication layer.
use axum::{
    body::Bytes,
    extract::{Query, State},
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::get,
    Json, Router,
};
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet, HashMap},
    ffi::CStr,
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::{Arc, Mutex},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

const LIMIT: u64 = 2 * 1024 * 1024;
type NetCounters = BTreeMap<String, (u64, u64)>;
#[derive(Default)]
struct Samples {
    cpu: Option<(u64, u64, Instant)>,
    net: Option<(Instant, NetCounters)>,
    processes: HashMap<u32, (u64, u64)>,
    process_total: Option<(u64, Instant)>,
}
#[derive(Default)]
struct Cached {
    value: Option<(Instant, Value)>,
}
type IconSample = (Instant, Option<(String, Vec<u8>)>);
struct Api {
    samples: Mutex<Samples>,
    caches: Mutex<HashMap<String, Arc<Mutex<Cached>>>>,
    registry: Mutex<()>,
    icons: Mutex<HashMap<String, IconSample>>,
    work: Arc<tokio::sync::Semaphore>,
}
impl Default for Api {
    fn default() -> Self {
        Self {
            samples: Mutex::new(Samples::default()),
            caches: Mutex::new(HashMap::new()),
            registry: Mutex::new(()),
            icons: Mutex::new(HashMap::new()),
            work: Arc::new(tokio::sync::Semaphore::new(8)),
        }
    }
}
type Shared = Arc<Api>;

pub fn router() -> Router {
    Router::new()
        .route("/api/metrics", get(metrics))
        .route("/api/processes", get(processes))
        .route("/api/services", get(services))
        .route("/api/cockpit", get(cockpit))
        .route("/api/files", get(files))
        .route("/api/vpn", get(vpn))
        .route("/api/private-service-ports", get(ports))
        .route("/api/apps", get(apps).post(mutate))
        .route("/api/apps/icon", get(icon))
        .route("/api/apps/launch", get(launch))
        .layer(axum::extract::DefaultBodyLimit::max(65536))
        .with_state(Arc::new(Api::default()))
}
fn now() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
}
fn read(path: impl AsRef<Path>) -> String {
    read_limited(path, LIMIT).unwrap_or_default()
}
fn read_limited(path: impl AsRef<Path>, cap: u64) -> std::io::Result<String> {
    let mut out = String::new();
    File::open(path)?.take(cap + 1).read_to_string(&mut out)?;
    if out.len() as u64 > cap {
        return Err(std::io::Error::other("sample too large"));
    }
    Ok(out)
}
fn read_json(path: impl AsRef<Path>) -> Value {
    serde_json::from_str(&read(path)).unwrap_or(Value::Null)
}
fn env_path(key: &str, fallback: &str) -> PathBuf {
    std::env::var_os(key)
        .map(PathBuf::from)
        .unwrap_or_else(|| fallback.into())
}
fn entries(path: impl AsRef<Path>) -> Vec<PathBuf> {
    let mut v: Vec<_> = fs::read_dir(path)
        .into_iter()
        .flatten()
        .filter_map(Result::ok)
        .map(|e| e.path())
        .collect();
    v.sort();
    v
}
fn num(text: &str) -> Option<u64> {
    text.trim().parse().ok()
}
fn rounded(n: f64, digits: i32) -> f64 {
    let factor = 10f64.powi(digits);
    (n * factor).round_ties_even() / factor
}
fn unavailable(reason: &str) -> Value {
    json!({"available":false,"reason":reason})
}
fn json_response(value: Value) -> Response {
    let mut response = Json(value).into_response();
    response
        .headers_mut()
        .insert("cache-control", "no-store".parse().unwrap());
    response
        .headers_mut()
        .insert("x-content-type-options", "nosniff".parse().unwrap());
    response
}
async fn cached(api: Shared, key: &'static str, ttl: u64, collect: fn(&Api) -> Value) -> Response {
    let slot = api
        .caches
        .lock()
        .unwrap()
        .entry(key.into())
        .or_default()
        .clone();
    let Ok(permit) = api.work.clone().try_acquire_owned() else {
        return StatusCode::SERVICE_UNAVAILABLE.into_response();
    };
    match tokio::task::spawn_blocking(move || {
        let _permit = permit;
        let mut cache = slot.lock().unwrap();
        if let Some((at, v)) = &cache.value {
            if at.elapsed() < Duration::from_secs(ttl) {
                return v.clone();
            }
        }
        let value = collect(&api);
        cache.value = Some((Instant::now(), value.clone()));
        value
    })
    .await
    {
        Ok(v) => json_response(v),
        Err(_) => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"error":"Collector unavailable."})),
        )
            .into_response(),
    }
}
async fn metrics(State(a): State<Shared>) -> Response {
    cached(a, "metrics", 1, collect_metrics).await
}
async fn processes(State(a): State<Shared>) -> Response {
    cached(a, "processes", 2, collect_processes).await
}
async fn services(State(a): State<Shared>) -> Response {
    cached(a, "services", 5, |_| collect_services()).await
}
async fn cockpit(State(a): State<Shared>) -> Response {
    cached(a, "cockpit", 5, |_| collect_cockpit()).await
}
async fn files(State(a): State<Shared>) -> Response {
    cached(a, "files", 5, |_| collect_files()).await
}
async fn vpn(State(a): State<Shared>) -> Response {
    cached(a, "vpn", 5, |_| collect_vpn()).await
}
async fn apps(State(a): State<Shared>) -> Response {
    cached(a, "apps", 5, |a| {
        let _guard = a.registry.lock().unwrap();
        collect_apps()
    })
    .await
}
async fn ports() -> Response {
    json_response(
        json!({"ports":private_services().iter().filter_map(|s|s["wireguard_port"].as_u64()).collect::<Vec<_>>()}),
    )
}

/// Bounded command output and wall time, with no shell or inherited locale.
fn command(binary: &str, args: &[&str], seconds: u64) -> Option<String> {
    use std::os::unix::process::CommandExt;
    let mut cmd = Command::new(binary);
    cmd.args(args)
        .env_clear()
        .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
        .env("LANG", "C.UTF-8")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    unsafe {
        cmd.pre_exec(|| {
            if libc::setpgid(0, 0) == -1 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }
    let mut child = cmd.spawn().ok()?;
    let stdout = child.stdout.take()?;
    let reader = std::thread::spawn(move || {
        let mut bytes = Vec::new();
        stdout.take(LIMIT + 1).read_to_end(&mut bytes).ok()?;
        if bytes.len() as u64 > LIMIT {
            None
        } else {
            String::from_utf8(bytes).ok()
        }
    });
    let start = Instant::now();
    let success = loop {
        match child.try_wait() {
            Ok(Some(s)) => break s.success(),
            Ok(None) if start.elapsed() < Duration::from_secs(seconds) => {
                std::thread::sleep(Duration::from_millis(10))
            }
            _ => {
                unsafe {
                    libc::kill(-(child.id() as i32), libc::SIGKILL);
                }
                let _ = child.wait();
                break false;
            }
        }
    };
    // Descendants must not keep a collector's output pipe open.
    unsafe {
        libc::kill(-(child.id() as i32), libc::SIGKILL);
    }
    let output = reader.join().ok().flatten();
    if success {
        output
    } else {
        None
    }
}
fn logical_cores() -> Option<u64> {
    let n = unsafe { libc::sysconf(libc::_SC_NPROCESSORS_ONLN) };
    if n > 0 {
        Some(n as u64)
    } else {
        None
    }
}
fn cpu_counters(text: &str) -> (u64, u64) {
    let v: Vec<u64> = text
        .lines()
        .next()
        .filter(|l| l.starts_with("cpu "))
        .unwrap_or("")
        .split_whitespace()
        .skip(1)
        .filter_map(|n| n.parse().ok())
        .collect();
    (
        v.iter().take(8).sum(),
        v.get(3).copied().unwrap_or(0) + v.get(4).copied().unwrap_or(0),
    )
}
fn cpu_usage(prev: Option<(u64, u64, Instant)>, total: u64, idle: u64, at: Instant) -> Option<f64> {
    prev.and_then(|(t, i, last)| {
        let gap = at.duration_since(last).as_secs_f64();
        let delta = total.checked_sub(t)?;
        if gap > 0. && gap <= 30. && delta > 0 {
            Some(rounded(
                ((delta as f64 - (idle as f64 - i as f64)) * 100. / delta as f64).clamp(0., 100.),
                0,
            ))
        } else {
            None
        }
    })
}
fn memory() -> BTreeMap<String, u64> {
    read("/proc/meminfo")
        .lines()
        .filter_map(|l| {
            let (k, v) = l.split_once(':')?;
            Some((
                k.into(),
                v.split_whitespace()
                    .next()?
                    .parse::<u64>()
                    .ok()?
                    .saturating_mul(1024),
            ))
        })
        .collect()
}
fn percent(used: u64, total: u64, digits: i32) -> Option<Value> {
    if total > 0 {
        let value = rounded(used as f64 * 100. / total as f64, digits);
        Some(if digits == 0 {
            json!(value as u64)
        } else {
            json!(value)
        })
    } else {
        None
    }
}
// libc filesystem counter widths differ between macOS and Linux.
#[allow(clippy::unnecessary_cast)]
fn disk_usage() -> Value {
    unsafe {
        let mut stat: libc::statvfs = std::mem::zeroed();
        if libc::statvfs(c"/".as_ptr(), &mut stat) != 0 {
            return json!({"used":null,"total":null,"percent":null,"mount":"/"});
        }
        let total = stat.f_blocks as u64 * stat.f_frsize as u64;
        let used = total.saturating_sub(stat.f_bfree as u64 * stat.f_frsize as u64);
        json!({"used":used,"total":total,"percent":percent(used,total,0),"mount":"/"})
    }
}
fn physical_devices(root: &Path) -> Vec<Value> {
    entries(root).into_iter().filter_map(|p|{let name=p.file_name()?.to_str()?;if name.is_empty()||name.len()>32||!name.bytes().all(|c|c.is_ascii_alphanumeric()||b"._-".contains(&c))||!p.join("device").exists(){return None}let kind=match read(p.join("queue/rotational")).trim(){"1"=>"HDD","0"=>"SSD",_=>"Unknown"};let model=read(p.join("device/model")).split_whitespace().collect::<Vec<_>>().join(" ").chars().take(100).collect::<String>();Some(json!({"name":name,"model":if model.is_empty(){"Unknown model"}else{&model},"kind":kind,"size":num(&read(p.join("size"))).and_then(|v|v.checked_mul(512))}))}).collect()
}
fn swap_metrics(text: &str, root: &Path) -> (Value, Value) {
    let mut disk = Vec::new();
    let mut swaps = BTreeMap::new();
    for l in text.lines().skip(1) {
        let f: Vec<_> = l.split_whitespace().collect();
        if f.len() < 4 {
            continue;
        }
        let (Some(total), Some(used)) = (
            num(f[2]).and_then(|v| v.checked_mul(1024)),
            num(f[3]).and_then(|v| v.checked_mul(1024)),
        ) else {
            continue;
        };
        let item = json!({"name":f[0],"total":total,"used":used,"kind":f[1]});
        let name = Path::new(f[0])
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("");
        if name.starts_with("zram") {
            swaps.insert(name.to_string(), item);
        } else {
            disk.push(item);
        }
    }
    let mut zram = Vec::new();
    for p in entries(root) {
        let name = p
            .file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .into_owned();
        if !name.starts_with("zram") {
            continue;
        }
        let total = num(&read(p.join("disksize")));
        let stat = read(p.join("mm_stat"));
        let stats: Option<Vec<u64>> = stat.split_whitespace().map(|s| s.parse().ok()).collect();
        let valid = total.is_some() && stats.is_some() && p.join("mm_stat").is_file();
        let values = stats.unwrap_or_default();
        let get = |i| {
            if valid {
                values
                    .get(i)
                    .copied()
                    .or(if i == 0 { Some(0) } else { None })
            } else {
                None
            }
        };
        zram.push(json!({"name":name,"total":if valid{total}else{None},"used":get(0),"compressed":get(1),"physical_used":get(2),"swap_used":swaps.get(&name).and_then(|v|v["used"].as_u64()).unwrap_or(0)}));
    }
    let sum = |v: &Vec<Value>, key: &str| v.iter().filter_map(|d| d[key].as_u64()).sum::<u64>();
    let dt = sum(&disk, "total");
    let du = sum(&disk, "used");
    let zt = zram
        .iter()
        .filter_map(|d| swaps.get(d["name"].as_str().unwrap_or("")))
        .filter_map(|d| d["total"].as_u64())
        .sum::<u64>();
    let zu = sum(&zram, "swap_used");
    (
        json!({"devices":disk,"used":du+zu,"total":dt+zt,"percent":percent(du+zu,dt+zt,0),"disk_used":du,"disk_total":dt}),
        json!({"used":sum(&zram,"used"),"total":sum(&zram,"total"),"compressed":sum(&zram,"compressed"),"physical_used":sum(&zram,"physical_used"),"swap_used":zu,"swap_total":zt,"devices":zram}),
    )
}
fn temperature() -> Option<f64> {
    let mut temperatures = Vec::new();
    for hw in entries("/sys/class/hwmon") {
        let name = read(hw.join("name")).to_lowercase();
        for p in entries(&hw) {
            let file = p.file_name().unwrap_or_default().to_string_lossy();
            if !file.starts_with("temp") || !file.ends_with("_label") {
                continue;
            }
            let label = format!("{name} {}", read(&p).to_lowercase());
            if !["package", "tctl", "tdie", "cpu"]
                .iter()
                .any(|s| label.contains(s))
            {
                continue;
            }
            let input = p.with_file_name(file.replace("_label", "_input"));
            if let Ok(v) = read(input).trim().parse::<f64>() {
                let v = v / 1000.;
                if (-20. ..=150.).contains(&v) {
                    temperatures.push(v)
                }
            }
        }
    }
    if !temperatures.is_empty() {
        return temperatures
            .into_iter()
            .reduce(f64::max)
            .map(|n| rounded(n, 1));
    }
    for zone in entries("/sys/class/thermal") {
        if ["x86_pkg_temp", "cpu-thermal"].contains(&read(zone.join("type")).trim()) {
            if let Ok(v) = read(zone.join("temp")).trim().parse::<f64>() {
                let v = v / 1000.;
                if (-20. ..=150.).contains(&v) {
                    return Some(rounded(v, 1));
                }
            }
        }
    }
    None
}
fn collect_metrics(api: &Api) -> Value {
    if !cfg!(target_os = "linux") {
        return json!({"supported":false,"reason":"Linux host metrics are available when deployed on Linux."});
    }
    let at = Instant::now();
    let (total_ticks, idle) = cpu_counters(&read("/proc/stat"));
    let mem = memory();
    let total = *mem.get("MemTotal").unwrap_or(&0);
    let available = *mem.get("MemAvailable").unwrap_or(&0);
    let used = total.saturating_sub(available);
    let mut net = BTreeMap::new();
    for line in read("/proc/net/dev").lines().skip(2) {
        if let Some((name, rest)) = line.split_once(':') {
            let name = name.trim();
            let f: Vec<_> = rest.split_whitespace().collect();
            let device = Path::new("/sys/class/net").join(name);
            if f.len() > 8
                && name != "lo"
                && device.join("device").exists()
                && read(device.join("operstate")).trim() == "up"
            {
                if let (Some(rx), Some(tx)) = (num(f[0]), num(f[8])) {
                    net.insert(name.to_string(), (rx, tx));
                }
            }
        }
    }
    let (cpu_pct, rx, tx) = {
        let mut s = api.samples.lock().unwrap();
        let pct = cpu_usage(s.cpu, total_ticks, idle, at);
        s.cpu = Some((total_ticks, idle, at));
        let rates = s.net.as_ref().and_then(|(last, prev)| {
            let elapsed = at.duration_since(*last).as_secs_f64();
            if elapsed <= 0. || elapsed > 30. || net.is_empty() {
                return None;
            }
            let (mut rx, mut tx) = (0u64, 0u64);
            for (k, v) in &net {
                let old = prev.get(k).unwrap_or(v);
                rx += v.0.saturating_sub(old.0);
                tx += v.1.saturating_sub(old.1)
            }
            Some((rx as f64 / elapsed, tx as f64 / elapsed))
        });
        s.net = Some((at, net.clone()));
        (pct, rates.map(|r| r.0), rates.map(|r| r.1))
    };
    let cpuinfo = read("/proc/cpuinfo");
    let model = cpuinfo
        .lines()
        .find_map(|l| {
            l.strip_prefix("model name")
                .and_then(|s| s.split_once(':'))
                .map(|(_, v)| v.trim())
        })
        .unwrap_or("Unknown");
    let mut pairs = BTreeSet::new();
    for block in cpuinfo.split("\n\n") {
        let field = |key: &str| {
            block.lines().find_map(|l| {
                let (k, v) = l.split_once(':')?;
                if k.trim() == key {
                    Some(v.trim().to_string())
                } else {
                    None
                }
            })
        };
        if let (Some(p), Some(c)) = (field("physical id"), field("core id")) {
            pairs.insert((p, c));
        }
    }
    let mut frequencies: Vec<f64> = entries("/sys/devices/system/cpu")
        .iter()
        .filter_map(|p| num(&read(p.join("cpufreq/scaling_cur_freq"))).map(|v| v as f64 / 1000.))
        .collect();
    if frequencies.is_empty() {
        frequencies = cpuinfo
            .lines()
            .filter_map(|l| {
                let (k, v) = l.split_once(':')?;
                if k.trim() == "cpu MHz" {
                    v.trim().parse::<f64>().ok().filter(|v| v.is_finite())
                } else {
                    None
                }
            })
            .collect()
    }
    let frequency = if frequencies.is_empty() {
        None
    } else {
        Some(rounded(
            frequencies.iter().sum::<f64>() / frequencies.len() as f64,
            0,
        ))
    };
    let (swap, zram) = swap_metrics(&read("/proc/swaps"), Path::new("/sys/block"));
    let mut load = [0.; 3];
    unsafe {
        libc::getloadavg(load.as_mut_ptr(), 3);
    }
    let kernel = read("/proc/sys/kernel/osrelease").trim().to_string();
    let os = format!("Linux-{kernel}-{}", std::env::consts::ARCH);
    json!({"supported":true,"sampled_at":now(),"cpu":{"usage_percent":cpu_pct,"logical_cores":logical_cores(),"physical_cores":if pairs.is_empty(){None}else{Some(pairs.len())},"frequency_mhz":frequency,"temperature_c":temperature(),"model":model,"load":load},"memory":{"used":used,"total":total,"available":available,"percent":percent(used,total,0)},"storage":disk_usage(),"storage_devices":physical_devices(Path::new("/sys/block")),"swap":swap,"zram":zram,"network":{"interfaces":net.iter().map(|(n,(rx,tx))|json!({"name":n,"received_total":rx,"sent_total":tx})).collect::<Vec<_>>(),"download_bytes_per_second":rx,"upload_bytes_per_second":tx},"system":{"os":os,"kernel":kernel,"uptime_seconds":read("/proc/uptime").split_whitespace().next().and_then(|v|v.parse::<f64>().ok()).unwrap_or(0.).max(0.)},"gpu":gpu(),"power":power()})
}
fn fresh(sample: &Value, maximum: f64) -> bool {
    sample["sampled_at"]
        .as_f64()
        .map(|s| s.is_finite() && (0. ..=maximum).contains(&(now() - s)))
        .unwrap_or(false)
}
fn bounded(sample: &Value, key: &str, min: f64, max: f64) -> Option<f64> {
    sample[key]
        .as_f64()
        .filter(|v| v.is_finite() && (*v >= min) && (*v <= max))
}
fn reason(sample: &Value, fallback: &str) -> Value {
    unavailable(
        &sample["reason"]
            .as_str()
            .filter(|s| !s.is_empty())
            .unwrap_or(fallback)
            .chars()
            .take(160)
            .collect::<String>(),
    )
}
fn power() -> Value {
    let sample = read_json(env_path(
        "POWER_FILE",
        "/var/lib/huou07-playground-power/sample.json",
    ));
    if !fresh(&sample, 60.) {
        return unavailable("No current CPU package-power sample is available.");
    }
    if sample["available"] == true {
        if let Some(v) = bounded(&sample, "watts", 0., 2000.) {
            return json!({"available":true,"watts":rounded(v,1),"measurement":"CPU package power"});
        }
    }
    reason(&sample, "CPU package power is unavailable.")
}
fn gpu() -> Value {
    if !cfg!(target_os = "linux") {
        return unavailable("GPU telemetry is available when deployed on Linux.");
    }
    if let Some(binary) = which("nvidia-smi") {
        let Some(output) = command(
            &binary,
            &[
                "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            2,
        ) else {
            return unavailable("nvidia-smi could not read GPU telemetry.");
        };
        let row = output.lines().next().unwrap_or("");
        let fields = csv_row(row);
        if fields.len() != 5 {
            return unavailable("nvidia-smi could not read GPU telemetry.");
        }
        let number = |i: usize, max: f64| {
            fields[i]
                .trim()
                .parse::<f64>()
                .ok()
                .filter(|v| v.is_finite() && (0. ..=max).contains(v))
        };
        return json!({"available":true,"model":fields[0].trim().chars().take(120).collect::<String>(),"usage_percent":number(1,100.),"memory_used":number(2,10_000_000.).map(|n|rounded(n*1048576.,0)),"memory_total":number(3,10_000_000.).map(|n|rounded(n*1048576.,0)),"temperature_c":number(4,150.)});
    }
    let sample = read_json(env_path(
        "GPU_FILE",
        "/var/lib/huou07-playground-gpu/sample.json",
    ));
    if !fresh(&sample, 75.) {
        return unavailable("No current Intel GPU sample is available.");
    }
    if sample["available"] == true {
        if let Some(usage) = bounded(&sample, "usage_percent", 0., 100.) {
            let engines: serde_json::Map<String, Value> = sample["engines"]
                .as_object()
                .into_iter()
                .flatten()
                .filter_map(|(k, v)| {
                    v.as_f64()
                        .filter(|n| n.is_finite() && (0. ..=100.).contains(n))
                        .map(|n| (k.chars().take(40).collect(), json!(rounded(n, 1))))
                })
                .collect();
            return json!({"available":true,"model":"Intel integrated graphics (i915)","usage_percent":rounded(usage,1),"engines":engines,"frequency_mhz":bounded(&sample,"frequency_mhz",f64::MIN_POSITIVE,10000.).map(|n|rounded(n,0)),"rc6_percent":bounded(&sample,"rc6_percent",0.,100.).map(|n|rounded(n,1)),"measurement":"Busiest GPU engine"});
        }
    }
    reason(&sample, "Intel GPU telemetry is unavailable.")
}
fn csv_row(text: &str) -> Vec<String> {
    let mut fields = vec![String::new()];
    let mut quoted = false;
    let mut chars = text.chars().peekable();
    while let Some(c) = chars.next() {
        match c {
            '"' => {
                if quoted && chars.peek() == Some(&'"') {
                    fields.last_mut().unwrap().push('"');
                    chars.next();
                } else {
                    quoted = !quoted
                }
            }
            ',' if !quoted => fields.push(String::new()),
            _ => fields.last_mut().unwrap().push(c),
        }
    }
    fields
}
fn which(name: &str) -> Option<String> {
    ["/usr/sbin", "/usr/bin", "/sbin", "/bin", "/usr/local/bin"]
        .iter()
        .map(|d| Path::new(d).join(name))
        .find(|p| {
            fs::metadata(p)
                .map(|m| m.is_file() && m.mode() & 0o111 != 0)
                .unwrap_or(false)
        })
        .map(|p| p.to_string_lossy().into_owned())
}
fn process_stat(stat: &str) -> Option<(u64, u64, String)> {
    let close = stat.rfind(')')?;
    let open = stat.find('(')?;
    let f: Vec<_> = stat[close + 1..].split_whitespace().collect();
    Some((
        f.get(11)?
            .parse::<u64>()
            .ok()?
            .checked_add(f.get(12)?.parse().ok()?)?,
        f.get(19)?.parse().ok()?,
        stat[open + 1..close].to_string(),
    ))
}
fn owner(uid: u32) -> String {
    unsafe {
        let mut record: libc::passwd = std::mem::zeroed();
        let mut result = std::ptr::null_mut();
        let mut buf = vec![0i8; 65536];
        if libc::getpwuid_r(uid, &mut record, buf.as_mut_ptr(), buf.len(), &mut result) == 0
            && !result.is_null()
            && !record.pw_name.is_null()
        {
            CStr::from_ptr(record.pw_name)
                .to_string_lossy()
                .into_owned()
        } else {
            uid.to_string()
        }
    }
}
fn collect_processes(api: &Api) -> Value {
    if !cfg!(target_os = "linux") {
        return unavailable("Process metrics are available when deployed on Linux.");
    }
    let at = Instant::now();
    let (total, _) = cpu_counters(&read("/proc/stat"));
    let ram = *memory().get("MemTotal").unwrap_or(&0);
    let cores = logical_cores().unwrap_or(1) as f64;
    let mut sample = api.samples.lock().unwrap();
    let delta = sample.process_total.and_then(|(old, last)| {
        let gap = at.duration_since(last).as_secs_f64();
        if gap > 0. && gap <= 30. {
            total.checked_sub(old).filter(|n| *n > 0)
        } else {
            None
        }
    });
    let mut current = HashMap::new();
    let mut processes = Vec::new();
    let mut owners = HashMap::new();
    for proc in entries("/proc") {
        let Some(pid) = proc
            .file_name()
            .and_then(|p| p.to_str())
            .and_then(|p| p.parse::<u32>().ok())
        else {
            continue;
        };
        let Some((ticks, started, fallback)) = process_stat(&read(proc.join("stat"))) else {
            continue;
        };
        current.insert(pid, (ticks, started));
        let cpu = sample
            .processes
            .get(&pid)
            .filter(|(_, s)| *s == started)
            .and_then(|(old, _)| {
                delta.map(|d| {
                    rounded(
                        ticks.saturating_sub(*old) as f64 * cores * 100. / d as f64,
                        1,
                    )
                })
            });
        let status = read(proc.join("status"));
        let field = |key: &str| {
            status.lines().find_map(|l| {
                l.strip_prefix(key)
                    .and_then(|v| v.split_whitespace().next())
                    .and_then(num)
            })
        };
        let uid = field("Uid:");
        let rss = field("VmRSS:").unwrap_or(0).saturating_mul(1024);
        let owner = uid
            .map(|u| owners.entry(u).or_insert_with(|| owner(u as u32)).clone())
            .unwrap_or_else(|| "unknown".into());
        let name = read(proc.join("comm")).trim().to_string();
        processes.push(json!({"pid":pid,"name":if name.is_empty(){fallback}else{name},"owner":owner,"cpu_percent":cpu,"memory_bytes":rss,"memory_percent":percent(rss,ram,2)}));
    }
    sample.processes = current;
    sample.process_total = Some((total, at));
    processes.sort_by(|a, b| {
        b["cpu_percent"]
            .as_f64()
            .unwrap_or(0.)
            .total_cmp(&a["cpu_percent"].as_f64().unwrap_or(0.))
            .then(b["memory_bytes"].as_u64().cmp(&a["memory_bytes"].as_u64()))
    });
    let total = processes.len();
    processes.truncate(1000);
    json!({"available":true,"sampled_at":now(),"total":total,"processes":processes})
}
fn collect_services() -> Value {
    if !cfg!(target_os = "linux") {
        return unavailable("Systemd service data is available when deployed on Linux.");
    }
    let Some(text) = command(
        "systemctl",
        &[
            "list-units",
            "--type=service",
            "--all",
            "--plain",
            "--no-pager",
            "--no-legend",
        ],
        3,
    ) else {
        return unavailable("systemctl could not provide service data.");
    };
    let mut units = Vec::new();
    for line in text.lines() {
        let fields: Vec<_> = line.split_whitespace().collect();
        if fields.len() < 4 {
            continue;
        }
        units.push(json!({"name":fields[0],"load":fields[1],"active":fields[2],"state":fields[3],"description":fields[4..].join(" ").chars().take(100).collect::<String>()}));
    }
    units.sort_by_key(|u| {
        (
            u["active"] != "active",
            u["name"].as_str().unwrap_or("").to_lowercase(),
        )
    });
    json!({"available":true,"sampled_at":now(),"total":units.len(),"services":units})
}
fn collect_cockpit() -> Value {
    if !cfg!(target_os = "linux") {
        return unavailable("Cockpit is available when deployed on Linux.");
    }
    json!({"available":command("systemctl",&["is-active","--quiet","cockpit.socket"],2).is_some(),"reason":"Cockpit is not installed or its socket is stopped."})
}
fn collect_files() -> Value {
    if !cfg!(target_os = "linux") {
        return json!({"available":false,"installed":false,"move_available":false,"reason":"Cockpit Files is available when deployed on Linux."});
    }
    let installed = ["/usr/share/cockpit", "/usr/local/share/cockpit"]
        .iter()
        .any(|r| Path::new(r).join("files/manifest.json").is_file());
    let moves = ["/usr/share/cockpit", "/usr/local/share/cockpit"]
        .iter()
        .any(|r| {
            Path::new(r)
                .join("huou07-move-files/manifest.json")
                .is_file()
        })
        && Path::new("/usr/libexec/huou07-move-files").is_file();
    if !installed {
        return json!({"available":false,"installed":false,"move_available":moves,"reason":"Cockpit Files is not installed."});
    }
    if collect_cockpit()["available"] != true {
        return json!({"available":false,"installed":true,"move_available":moves,"reason":"Cockpit Files is installed, but Cockpit is unavailable."});
    }
    json!({"available":true,"installed":true,"move_available":moves})
}
fn http_client(milliseconds: u64) -> Option<reqwest::blocking::Client> {
    reqwest::blocking::Client::builder()
        .timeout(Duration::from_millis(milliseconds))
        .connect_timeout(Duration::from_millis(milliseconds))
        .redirect(reqwest::redirect::Policy::none())
        .no_proxy()
        .resolve("localhost", std::net::SocketAddr::from(([127, 0, 0, 1], 0)))
        .user_agent("huou07-playground/0.1")
        .build()
        .ok()
}
fn wg_sample() -> Option<Value> {
    let s = read_json(env_path(
        "WG_STATUS_FILE",
        "/var/lib/huou07-wg-easy-status/status.json",
    ));
    if s["available"] != true
        || !fresh(&s, 90.)
        || s["peer_count"].as_u64().filter(|n| *n <= 65535).is_none()
    {
        return None;
    }
    if !s["latest_handshake_at"].is_null()
        && s["latest_handshake_at"]
            .as_u64()
            .filter(|n| *n > 0 && *n as f64 <= now() + 30.)
            .is_none()
    {
        return None;
    }
    if !s["listen_port"].is_null()
        && s["listen_port"]
            .as_u64()
            .filter(|n| (1..=65535).contains(n))
            .is_none()
    {
        return None;
    }
    Some(s)
}
fn setup_required() -> bool {
    http_client(1000)
        .and_then(|c| c.get("http://127.0.0.1:51821/").send().ok())
        .map(|r| {
            r.status().is_redirection()
                && r.headers()
                    .get("location")
                    .and_then(|s| s.to_str().ok())
                    .map(|s| {
                        s.starts_with("/setup/")
                            || reqwest::Url::parse(s)
                                .map(|u| u.path().starts_with("/setup/"))
                                .unwrap_or(false)
                    })
                    .unwrap_or(false)
        })
        .unwrap_or(false)
}
fn collect_vpn() -> Value {
    if !cfg!(target_os = "linux") {
        let v = json!({"available":false,"connected":false,"state":"Unavailable"});
        return json!({"available":false,"connected":false,"state":"Unavailable","wireguard":v,"tailscale":v});
    }
    let tail = if let Some(bin) = which("tailscale") {
        let data = command(&bin, &["status", "--json"], 2)
            .and_then(|s| serde_json::from_str::<Value>(&s).ok())
            .unwrap_or(Value::Null);
        let connected = data["BackendState"] == "Running";
        json!({"available":true,"connected":connected,"state":if connected{"Connected"}else{"Disconnected"}})
    } else {
        json!({"available":false,"connected":false,"state":"Unavailable"})
    };
    let wg = if !Path::new("/etc/systemd/system/huou07-wg-easy.service").is_file() {
        json!({"available":false,"connected":false,"state":"Not installed","peer_count":0})
    } else if command(
        "systemctl",
        &["is-active", "--quiet", "huou07-wg-easy.service"],
        2,
    )
    .is_none()
    {
        json!({"available":false,"connected":false,"state":"Stopped","peer_count":0})
    } else if let Some(s) = wg_sample() {
        let peers = s["peer_count"].as_u64().unwrap();
        if peers == 0 {
            json!({"available":true,"connected":false,"state":if setup_required(){"Needs owner setup"}else{"Waiting for peer"},"peer_count":0,"listen_port":s["listen_port"]})
        } else {
            let age = s["latest_handshake_at"]
                .as_u64()
                .map(|h| (now() as u64).saturating_sub(h));
            let connected = age.map(|s| s <= 180).unwrap_or(false);
            json!({"available":true,"connected":connected,"state":if connected{"Connected"}else{"Waiting for peer"},"peer_count":peers,"listen_port":s["listen_port"],"last_handshake_seconds":age})
        }
    } else {
        json!({"available":true,"connected":false,"state":if setup_required(){"Needs owner setup"}else{"Status unavailable"},"peer_count":0,"listen_port":null})
    };
    json!({"available":wg["available"],"connected":wg["connected"],"state":wg["state"],"wireguard":wg,"tailscale":tail})
}
fn private_services() -> Vec<Value> {
    let v: Value = serde_json::from_str(include_str!("../../../deploy/private-services.json"))
        .unwrap_or(Value::Null);
    v["services"].as_array().cloned().unwrap_or_default()
}
fn port(id: &str, default: u16) -> u16 {
    private_services()
        .iter()
        .find(|s| s["id"] == id)
        .and_then(|s| s["wireguard_port"].as_u64())
        .map(|n| n as u16)
        .unwrap_or(default)
}
fn valid_url(v: &Value) -> Option<reqwest::Url> {
    let s = v.as_str()?;
    if s.len() > 2048 || s.chars().any(|c| c < ' ') {
        return None;
    }
    if s.split_once("://")
        .map(|(_, rest)| {
            rest.split(['/', '?', '#'])
                .next()
                .unwrap_or("")
                .contains('@')
        })
        .unwrap_or(false)
    {
        return None;
    }
    let u = reqwest::Url::parse(s).ok()?;
    if !["http", "https"].contains(&u.scheme())
        || u.host_str().is_none()
        || !u.username().is_empty()
        || u.password().is_some()
        || u.port() == Some(0)
    {
        return None;
    }
    Some(u)
}
fn loopback_url(u: &reqwest::Url) -> bool {
    matches!(
        u.host_str(),
        Some("127.0.0.1" | "localhost" | "[::1]" | "::1")
    )
}
fn raw_loopback(value: &Value) -> bool {
    let Some(s) = value.as_str() else {
        return false;
    };
    let Some((_, rest)) = s.split_once("://") else {
        return false;
    };
    let authority = rest.split(['/', '?', '#']).next().unwrap_or("");
    let host = if authority.starts_with('[') {
        authority
            .split(']')
            .next()
            .unwrap_or("")
            .trim_start_matches('[')
    } else {
        authority.split(':').next().unwrap_or("")
    };
    matches!(
        host.to_ascii_lowercase().as_str(),
        "127.0.0.1" | "localhost" | "::1"
    )
}
// shortcut: lowercase plus common casefold expansions; add full Unicode folding if non-ASCII registry collisions become a supported migration case.
fn folded(s: &str) -> String {
    s.to_lowercase().replace('ß', "ss").replace('ς', "σ")
}
fn validate_apps(config: &Value) -> Result<Vec<Value>, ()> {
    let entries = config["apps"].as_array().ok_or(())?;
    if entries.len() > 20 {
        return Err(());
    }
    let mut names = BTreeSet::new();
    let mut out = Vec::new();
    for e in entries {
        let name = e["name"].as_str().ok_or(())?;
        let description = e
            .get("description")
            .unwrap_or(&Value::Null)
            .as_str()
            .unwrap_or("");
        let category = e
            .get("category")
            .and_then(Value::as_str)
            .unwrap_or("Application");
        if name.trim().is_empty()
            || name.chars().count() > 60
            || valid_url(&e["url"]).is_none()
            || description.chars().count() > 160
            || category.chars().count() > 40
            || e.get("description")
                .map(|v| !v.is_string())
                .unwrap_or(false)
            || e.get("category").map(|v| !v.is_string()).unwrap_or(false)
        {
            return Err(());
        }
        if !(e["health_url"].is_null()
            || valid_url(&e["health_url"])
                .map(|u| loopback_url(&u))
                .unwrap_or(false)
                && raw_loopback(&e["health_url"]))
        {
            return Err(());
        }
        if !e["management_url"].is_null() && valid_url(&e["management_url"]).is_none() {
            return Err(());
        }
        let method = e
            .get("health_method")
            .and_then(Value::as_str)
            .unwrap_or("GET");
        if !["GET", "HEAD"].contains(&method)
            || e.get("health_method")
                .map(|v| !v.is_string())
                .unwrap_or(false)
            || !names.insert(folded(name.trim()))
        {
            return Err(());
        }
        out.push(json!({"name":name.trim(),"url":e["url"],"description":description,"category":category,"health_url":e["health_url"],"health_method":method,"management_url":e["management_url"]}));
    }
    Ok(out)
}
fn registry_path() -> PathBuf {
    env_path("APPS_FILE", "/var/lib/huou07-playground/apps.json")
}
fn health(url: &str, method: &str) -> String {
    let Some(client) = http_client(1000) else {
        return "unavailable".into();
    };
    let Ok(method) = reqwest::Method::from_bytes(method.as_bytes()) else {
        return "unavailable".into();
    };
    let Ok(response) = client.request(method, url).send() else {
        return "unavailable".into();
    };
    let code = response.status().as_u16();
    if (300..400).contains(&code) {
        let setup = response
            .headers()
            .get("location")
            .and_then(|l| l.to_str().ok())
            .map(|s| {
                s.starts_with("/setup/")
                    || reqwest::Url::parse(s)
                        .map(|u| u.path().starts_with("/setup/"))
                        .unwrap_or(false)
            })
            .unwrap_or(false);
        if setup {
            "setup_required".into()
        } else {
            "available".into()
        }
    } else if (200..300).contains(&code) {
        "available".into()
    } else if code == 401 {
        "authentication_required".into()
    } else {
        "unavailable".into()
    }
}
fn collect_apps() -> Value {
    let Ok(items) = validate_apps(&read_json(registry_path())) else {
        return json!({"available":false,"reason":"Application configuration is unavailable or invalid.","apps":[]});
    };
    let mut result = Vec::new();
    for batch in items.chunks(8) {
        std::thread::scope(|scope| {
            let checks: Vec<_> = batch
                .iter()
                .map(|item| {
                    scope.spawn(move || {
                        item["health_url"]
                            .as_str()
                            .map(|u| health(u, item["health_method"].as_str().unwrap_or("GET")))
                            .unwrap_or_else(|| "unmonitored".into())
                    })
                })
                .collect();
            for (item, check) in batch.iter().zip(checks) {
                result.push(json!({"name":item["name"],"url":item["url"],"description":item["description"],"category":item["category"],"management_url":item["management_url"],"status":check.join().unwrap_or_else(|_|"unavailable".into())}));
            }
        })
    }
    json!({"available":true,"sampled_at":now(),"total":result.len(),"apps":result})
}
fn save_apps(path: &Path, items: Vec<Value>) -> std::io::Result<()> {
    let data = serde_json::to_vec(&json!({"apps":items}))?;
    let parent = path
        .parent()
        .ok_or_else(|| std::io::Error::other("registry parent absent"))?;
    let metadata = fs::symlink_metadata(path)?;
    if fs::symlink_metadata(parent)?.file_type().is_symlink()
        || !parent.is_dir()
        || !metadata.is_file()
        || metadata.file_type().is_symlink()
    {
        return Err(std::io::Error::other("registry unavailable"));
    }
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    let temporary = parent.join(format!(".apps-{}-{stamp}", std::process::id()));
    let result = (|| {
        let mut output = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW)
            .open(&temporary)?;
        output.write_all(&data)?;
        output.sync_all()?;
        use std::os::fd::AsRawFd;
        unsafe {
            if libc::fchown(output.as_raw_fd(), libc::geteuid(), metadata.gid()) != 0 {
                return Err(std::io::Error::last_os_error());
            }
        }
        output.set_permissions(fs::Permissions::from_mode(0o660))?;
        fs::rename(&temporary, path)?;
        File::open(parent)?.sync_all()
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}
fn change_apps(change: &Value) -> Result<(), ()> {
    let path = registry_path();
    let mut items = validate_apps(&read_json(&path))?;
    let name = change["name"]
        .as_str()
        .filter(|s| !s.trim().is_empty())
        .ok_or(())?;
    let found = items
        .iter()
        .position(|i| folded(i["name"].as_str().unwrap_or("")) == folded(name.trim()));
    match change["action"].as_str() {
        Some("add") => {
            if found.is_some() {
                return Err(());
            }
            items.push(validate_apps(&json!({"apps":[change["app"]]}))?.remove(0));
        }
        Some("update") => {
            let index = found.ok_or(())?;
            let mut item = validate_apps(&json!({"apps":[change["app"]]}))?.remove(0);
            if change["app"].get("health_url").is_none() {
                item["health_url"] = items[index]["health_url"].clone();
                item["health_method"] = items[index]["health_method"].clone();
            }
            items[index] = item;
        }
        Some("delete") => {
            items.remove(found.ok_or(())?);
        }
        _ => return Err(()),
    }
    let items = validate_apps(&json!({"apps":items}))?;
    save_apps(&path, items).map_err(|_| ())
}
async fn mutate(State(api): State<Shared>, headers: HeaderMap, body: Bytes) -> Response {
    if headers
        .get("content-type")
        .and_then(|v| v.to_str().ok())
        .map(|v| v.split(';').next().unwrap_or("").trim())
        != Some("application/json")
    {
        return (
            StatusCode::UNSUPPORTED_MEDIA_TYPE,
            Json(json!({"error":"Send application/json."})),
        )
            .into_response();
    }
    let Ok(change) = serde_json::from_slice::<Value>(&body) else {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error":"Application registry is invalid or could not be saved."})),
        )
            .into_response();
    };
    let Ok(permit) = api.work.clone().try_acquire_owned() else {
        return StatusCode::SERVICE_UNAVAILABLE.into_response();
    };
    match tokio::task::spawn_blocking(move || {
        let _permit = permit;
        let _guard = api.registry.lock().unwrap();
        change_apps(&change)?;
        let value = collect_apps();
        api.caches.lock().unwrap().remove("apps");
        api.icons.lock().unwrap().clear();
        Ok::<_, ()>(value)
    })
    .await
    {
        Ok(Ok(v)) => json_response(v),
        _ => (
            StatusCode::BAD_REQUEST,
            Json(json!({"error":"Application registry is invalid or could not be saved."})),
        )
            .into_response(),
    }
}
fn same_origin(a: &reqwest::Url, b: &reqwest::Url) -> bool {
    a.scheme() == b.scheme()
        && a.host_str() == b.host_str()
        && a.port_or_known_default() == b.port_or_known_default()
        && b.username().is_empty()
        && b.password().is_none()
}
fn fetch_local(
    client: &reqwest::blocking::Client,
    origin: &reqwest::Url,
    url: reqwest::Url,
) -> Option<reqwest::blocking::Response> {
    let mut url = url;
    for _ in 0..=3 {
        if !same_origin(origin, &url) {
            return None;
        }
        let response = client.get(url.clone()).send().ok()?;
        if !response.status().is_redirection() {
            return Some(response);
        }
        url = url
            .join(response.headers().get("location")?.to_str().ok()?)
            .ok()?;
    }
    None
}
fn media(response: &reqwest::blocking::Response) -> String {
    response
        .headers()
        .get("content-type")
        .and_then(|h| h.to_str().ok())
        .unwrap_or("")
        .split(';')
        .next()
        .unwrap_or("")
        .trim()
        .to_lowercase()
}
fn small_body(response: reqwest::blocking::Response) -> Option<Vec<u8>> {
    let mut bytes = Vec::new();
    response.take(128 * 1024 + 1).read_to_end(&mut bytes).ok()?;
    if bytes.len() <= 128 * 1024 {
        Some(bytes)
    } else {
        None
    }
}
// Parse link attributes without executing or rendering the app's HTML.
fn icon_links(html: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut rest = html;
    while let Some(start) = rest.find('<') {
        rest = &rest[start + 1..];
        let Some(end) = rest.find('>') else { break };
        let tag = &rest[..end];
        rest = &rest[end + 1..];
        let name = tag.split_whitespace().next().unwrap_or("");
        if !name.eq_ignore_ascii_case("link") {
            continue;
        }
        let mut attrs = HashMap::new();
        let mut s = &tag[name.len()..];
        while !s.trim_start().is_empty() {
            s = s.trim_start();
            let end = s
                .find(|c: char| c.is_whitespace() || c == '=' || c == '/')
                .unwrap_or(s.len());
            if end == 0 {
                break;
            }
            let key = s[..end].to_lowercase();
            s = s[end..].trim_start();
            if !s.starts_with('=') {
                continue;
            }
            s = s[1..].trim_start();
            let Some(first) = s.chars().next() else { break };
            let value;
            if first == '\'' || first == '"' {
                s = &s[1..];
                let Some(end) = s.find(first) else { break };
                value = s[..end].to_string();
                s = &s[end + 1..];
            } else {
                let end = s.find(char::is_whitespace).unwrap_or(s.len());
                value = s[..end].to_string();
                s = &s[end..];
            }
            attrs.insert(key, value);
        }
        if attrs
            .get("rel")
            .map(|s| s.split_whitespace().any(|r| r.eq_ignore_ascii_case("icon")))
            .unwrap_or(false)
        {
            if let Some(href) = attrs.get("href") {
                out.push(href.replace("&amp;", "&"));
            }
        }
    }
    out
}
fn app_icon(name: &str) -> Option<(String, Vec<u8>)> {
    let apps = validate_apps(&read_json(registry_path())).ok()?;
    let app = apps
        .iter()
        .find(|i| folded(i["name"].as_str().unwrap_or("")) == folded(name))?;
    let mut origin = valid_url(&app["url"])?;
    if origin.scheme() != "http" || !loopback_url(&origin) || !raw_loopback(&app["url"]) {
        return None;
    }
    origin.set_query(None);
    origin.set_fragment(None);
    let deadline = Instant::now();
    let client = http_client(500)?;
    let mut candidates = Vec::new();
    if let Some(page) = fetch_local(&client, &origin, origin.clone()) {
        if page.status() == 200 && media(&page) == "text/html" {
            if let Some(body) = small_body(page) {
                for href in icon_links(&String::from_utf8_lossy(&body))
                    .into_iter()
                    .take(16)
                {
                    if let Ok(url) = origin.join(&href) {
                        if same_origin(&origin, &url) {
                            candidates.push((url, false));
                        }
                    }
                }
            }
        }
    }
    for ext in ["ico", "svg"] {
        candidates.push((origin.join(&format!("/favicon.{ext}")).ok()?, true));
    }
    for (url, fallback) in candidates {
        if deadline.elapsed() > Duration::from_secs(3) {
            break;
        }
        let Some(response) = fetch_local(&client, &origin, url.clone()) else {
            continue;
        };
        let kind = media(&response);
        let allowed = if fallback && url.path().ends_with(".ico") {
            ["image/x-icon", "image/vnd.microsoft.icon"].contains(&kind.as_str())
        } else if fallback {
            kind == "image/svg+xml"
        } else {
            [
                "image/x-icon",
                "image/vnd.microsoft.icon",
                "image/svg+xml",
                "image/png",
                "image/jpeg",
                "image/webp",
            ]
            .contains(&kind.as_str())
        };
        if response.status() == 200 && allowed {
            if let Some(bytes) = small_body(response) {
                return Some((kind, bytes));
            }
        }
    }
    None
}
async fn icon(State(api): State<Shared>, Query(query): Query<Vec<(String, String)>>) -> Response {
    let names: Vec<_> = query.iter().filter(|(k, _)| k == "name").collect();
    let name = if query.len() <= 2 && names.len() == 1 {
        names[0].1.clone()
    } else {
        String::new()
    };
    let Ok(permit) = api.work.clone().try_acquire_owned() else {
        return StatusCode::SERVICE_UNAVAILABLE.into_response();
    };
    let result = tokio::task::spawn_blocking(move || {
        let _permit = permit;
        if name.chars().count() > 60 {
            return None;
        }
        let mut icons = api.icons.lock().unwrap();
        if let Some((at, value)) = icons.get(&name) {
            if at.elapsed() < Duration::from_secs(300) {
                return value.clone();
            }
        }
        let value = app_icon(&name);
        if icons.len() >= 20 {
            if let Some(old) = icons
                .iter()
                .min_by_key(|(_, v)| v.0)
                .map(|(k, _)| k.clone())
            {
                icons.remove(&old);
            }
        }
        icons.insert(name, (Instant::now(), value.clone()));
        value
    })
    .await
    .ok()
    .flatten();
    let (kind, bytes) = result.unwrap_or_else(|| {
        (
            "image/gif".into(),
            vec![
                71, 73, 70, 56, 57, 97, 1, 0, 1, 0, 0, 255, 0, 44, 0, 0, 0, 0, 1, 0, 1, 0, 0, 2, 0,
                59,
            ],
        )
    });
    let mut response = bytes.into_response();
    for (k, v) in [
        ("content-type", kind.as_str()),
        ("cache-control", "private, max-age=300"),
        ("x-content-type-options", "nosniff"),
        ("content-security-policy", "default-src 'none'; sandbox"),
    ] {
        response.headers_mut().insert(
            axum::http::HeaderName::from_bytes(k.as_bytes()).unwrap(),
            v.parse().unwrap(),
        );
    }
    response
}
fn wg_addresses() -> Vec<String> {
    let data = command("ip", &["-j", "-4", "addr", "show", "dev", "wg0"], 2)
        .and_then(|s| serde_json::from_str::<Value>(&s).ok())
        .unwrap_or(Value::Null);
    data.as_array()
        .into_iter()
        .flatten()
        .filter(|l| l["ifname"] == "wg0")
        .flat_map(|l| l["addr_info"].as_array().into_iter().flatten())
        .filter(|a| a["scope"] == "global")
        .filter_map(|a| a["local"].as_str())
        .filter(|s| {
            s.parse::<std::net::Ipv4Addr>()
                .map(|ip| {
                    ip.is_private()
                        && !ip.is_loopback()
                        && !ip.is_link_local()
                        && !ip.is_unspecified()
                        && !ip.is_multicast()
                })
                .unwrap_or(false)
        })
        .map(str::to_string)
        .collect()
}
fn launch_url(token: &str, host: &str, addresses: &[String]) -> Option<String> {
    let value = token.strip_prefix("/?token=")?;
    if !(32..=128).contains(&value.len())
        || !value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
    {
        return None;
    }
    if host.contains(['/', '?', '#', '@']) || host.chars().any(char::is_whitespace) {
        return None;
    }
    let url = reqwest::Url::parse(&format!("http://{host}")).ok()?;
    let (_, explicit_port) = host.rsplit_once(':')?;
    let port_number = explicit_port.parse::<u16>().ok().filter(|p| *p > 0)?;
    url.host_str()?;
    let raw_hostname = host.rsplit_once(':')?.0;
    let hostname = raw_hostname.trim_matches(['[', ']']);
    let loopback = hostname.eq_ignore_ascii_case("localhost")
        || hostname
            .parse::<std::net::IpAddr>()
            .map(|a| a.is_loopback())
            .unwrap_or(false);
    if !loopback
        && (port_number != port("dashboard", 8765) || !addresses.iter().any(|a| a == hostname))
    {
        return None;
    }
    let host = if hostname.contains(':') {
        format!("[{hostname}]")
    } else {
        hostname.into()
    };
    Some(format!("http://{host}:{}{token}", port("dsh", 3080)))
}
fn launch_format(query: &[(String, String)]) -> Option<bool> {
    let json_format = query.len() == 2
        && query
            .iter()
            .filter(|(key, value)| key == "format" && value == "json")
            .count()
            == 1;
    if query.len() > 2
        || query.iter().any(|(key, _)| key == "format") && !json_format
        || query
            .iter()
            .filter(|(k, _)| k == "name")
            .map(|(_, v)| v.as_str())
            .collect::<Vec<_>>()
            != ["DeepSeek Harness"]
    {
        return None;
    }
    Some(json_format)
}
async fn launch(
    State(api): State<Shared>,
    headers: HeaderMap,
    Query(query): Query<Vec<(String, String)>>,
) -> Response {
    let Some(json_format) = launch_format(&query) else {
        return StatusCode::NOT_FOUND.into_response();
    };
    let host = headers
        .get("host")
        .and_then(|h| h.to_str().ok())
        .unwrap_or("")
        .to_string();
    let Ok(permit) = api.work.clone().try_acquire_owned() else {
        return StatusCode::SERVICE_UNAVAILABLE.into_response();
    };
    let location = tokio::task::spawn_blocking(move || {
        let _permit = permit;
        let path = env_path("DSH_URL_FILE", "/run/huou07-dsh-link/url");
        if fs::symlink_metadata(&path)
            .map(|m| m.file_type().is_symlink())
            .unwrap_or(true)
        {
            return None;
        }
        launch_url(read_limited(path, 256).ok()?.trim(), &host, &wg_addresses())
    })
    .await
    .ok()
    .flatten();
    let Some(location) = location else {
        return(StatusCode::SERVICE_UNAVAILABLE,Json(json!({"error":"DeepSeek Harness is starting or its private login link is unavailable."}))).into_response();
    };
    if json_format {
        return json_response(json!({"url": location}));
    }
    let mut response = StatusCode::FOUND.into_response();
    response
        .headers_mut()
        .insert("location", location.parse().unwrap());
    response
        .headers_mut()
        .insert("cache-control", "no-store".parse().unwrap());
    response
        .headers_mut()
        .insert("referrer-policy", "no-referrer".parse().unwrap());
    response
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture() -> PathBuf {
        let p = std::env::temp_dir().join(format!(
            "telemetry-fixture-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir(&p).unwrap();
        p
    }
    #[test]
    fn launch_json_requires_exact_format_and_one_harness_name() {
        let query = |items: &[(&str, &str)]| {
            items
                .iter()
                .map(|(k, v)| (k.to_string(), v.to_string()))
                .collect::<Vec<_>>()
        };
        assert_eq!(
            launch_format(&query(&[("name", "DeepSeek Harness")])),
            Some(false)
        );
        assert_eq!(
            launch_format(&query(&[("name", "DeepSeek Harness"), ("format", "json")])),
            Some(true)
        );
        assert_eq!(
            launch_format(&query(&[("name", "DeepSeek Harness"), ("format", "html")])),
            None
        );
        assert_eq!(
            launch_format(&query(&[("name", "other"), ("format", "json")])),
            None
        );
        assert_eq!(
            launch_format(&query(&[
                ("name", "DeepSeek Harness"),
                ("name", "DeepSeek Harness")
            ])),
            None
        );
        assert_eq!(
            launch_format(&query(&[
                ("name", "DeepSeek Harness"),
                ("format", "json"),
                ("extra", "1")
            ])),
            None
        );
    }
    #[test]
    fn collectors_bound_commands_and_reject_stale_or_boolean_samples() {
        let at = Instant::now();
        assert!(command("/bin/sleep", &["2"], 0).is_none());
        assert!(at.elapsed() < Duration::from_secs(1));
        assert!(!fresh(&json!({"sampled_at":now()-100.}), 60.));
        assert!(!fresh(&json!({"sampled_at":true}), 60.));
        assert!(!fresh(&json!({"sampled_at":now()+10.}), 60.));
        assert!(fresh(&json!({"sampled_at":now()}), 60.));
        assert_eq!(bounded(&json!({"watts":true}), "watts", 0., 2000.), None);
    }
    #[test]
    fn local_http_health_and_redirect_boundaries() {
        fn serve(
            status: &'static str,
            headers: &'static str,
        ) -> (String, std::thread::JoinHandle<()>) {
            let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
            let address = listener.local_addr().unwrap();
            let thread = std::thread::spawn(move || {
                let (mut socket, _) = listener.accept().unwrap();
                socket
                    .set_read_timeout(Some(Duration::from_secs(2)))
                    .unwrap();
                let mut request = [0; 4096];
                let _ = socket.read(&mut request);
                write!(
                    socket,
                    "HTTP/1.1 {status}\r\n{headers}Content-Length: 0\r\nConnection: close\r\n\r\n"
                )
                .unwrap();
            });
            (format!("http://{address}/"), thread)
        }
        let (url, thread) = serve("302 Found", "Location: /setup/start\r\n");
        assert_eq!(health(&url, "GET"), "setup_required");
        thread.join().unwrap();
        let (url, thread) = serve("401 Unauthorized", "");
        assert_eq!(health(&url, "HEAD"), "authentication_required");
        thread.join().unwrap();
        let (url, thread) = serve("302 Found", "Location: http://192.0.2.1/icon\r\n");
        let origin = reqwest::Url::parse(&url).unwrap();
        assert!(fetch_local(&http_client(500).unwrap(), &origin, origin.clone()).is_none());
        thread.join().unwrap();
    }
    #[test]
    fn legacy_reference_fixture_parity() {
        let expected: Value =
            serde_json::from_str(include_str!("../../../tests/telemetry-parity.json")).unwrap();
        let root = fixture();
        let z = root.join("zram0");
        fs::create_dir(&z).unwrap();
        fs::write(z.join("disksize"), "1048576").unwrap();
        fs::write(z.join("mm_stat"), "4096 1024 2048").unwrap();
        let (swap, zram) = swap_metrics(expected["swaps_text"].as_str().unwrap(), &root);
        assert_eq!(swap, expected["swap"]);
        assert_eq!(zram, expected["zram"]);
        assert_eq!(
            json!(validate_apps(&expected["app_input"]).unwrap()),
            expected["apps"]
        );
        fs::remove_dir_all(root).unwrap();
    }
    #[tokio::test]
    async fn real_router_returns_json_and_launch_requires_exact_query() {
        use tower::ServiceExt;
        let app = router();
        let response = app
            .clone()
            .oneshot(
                axum::http::Request::builder()
                    .uri("/api/private-service-ports")
                    .body(axum::body::Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(response.headers()["cache-control"], "no-store");
        let body = axum::body::to_bytes(response.into_body(), 65536)
            .await
            .unwrap();
        let payload: Value = serde_json::from_slice(&body).unwrap();
        assert!(payload["ports"].as_array().unwrap().contains(&json!(8765)));
        for route in ["/api/metrics", "/api/processes"] {
            let response = app
                .clone()
                .oneshot(
                    axum::http::Request::builder()
                        .uri(route)
                        .body(axum::body::Body::empty())
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::OK);
            let bytes = axum::body::to_bytes(response.into_body(), 2 * 1024 * 1024)
                .await
                .unwrap();
            let value: Value = serde_json::from_slice(&bytes).unwrap();
            if cfg!(target_os = "linux") {
                if route == "/api/metrics" {
                    assert_eq!(value["supported"], true);
                    assert!(value["memory"]["total"].as_u64().unwrap() > 0);
                } else {
                    assert_eq!(value["available"], true);
                    assert!(value["total"].as_u64().unwrap() > 0);
                }
            }
        }
        let response = app
            .oneshot(
                axum::http::Request::builder()
                    .uri("/api/apps/launch?name=other")
                    .body(axum::body::Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }
    #[test]
    fn counters_exclude_guest_and_reset_stale_samples() {
        let sample = "cpu  100 5 20 200 10 2 3 4 90 1\ncpu0 0";
        assert_eq!(cpu_counters(sample), (344, 210));
        let at = Instant::now();
        assert_eq!(cpu_usage(None, 100, 20, at), None);
        assert_eq!(
            cpu_usage(Some((100, 20, at)), 200, 70, at + Duration::from_secs(1)),
            Some(50.)
        );
        assert_eq!(
            cpu_usage(Some((300, 20, at)), 200, 70, at + Duration::from_secs(1)),
            None
        );
        assert_eq!(
            cpu_usage(Some((100, 20, at)), 200, 70, at + Duration::from_secs(31)),
            None
        );
    }
    #[test]
    fn process_stat_handles_spaces_and_parentheses_and_pid_identity() {
        let mut fields = vec!["0"; 20];
        fields[0] = "S";
        fields[11] = "40";
        fields[12] = "2";
        fields[19] = "123";
        assert_eq!(
            process_stat(&format!("7 (worker (job)) {}", fields.join(" "))),
            Some((42, 123, "worker (job)".into()))
        );
        assert!(process_stat("7 broken").is_none());
    }
    #[test]
    fn swaps_keep_compression_separate_from_swap_consumption() {
        let root = fixture();
        let z = root.join("zram0");
        fs::create_dir(&z).unwrap();
        fs::write(z.join("disksize"), "1048576").unwrap();
        fs::write(z.join("mm_stat"), "4096 1024 2048").unwrap();
        let (swap,zram)=swap_metrics("Filename Type Size Used Priority\n/swap file 100 10 -2\n/dev/zram0 partition 1024 4 100\nmalformed\n",&root);
        assert_eq!(swap["total"], 1124 * 1024);
        assert_eq!(swap["used"], 14 * 1024);
        assert_eq!(swap["disk_used"], 10 * 1024);
        assert_eq!(zram["physical_used"], 2048);
        assert_eq!(zram["used"], 4096);
        assert_eq!(zram["swap_used"], 4096);
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn physical_devices_ignore_virtual_and_identifiers() {
        let root = fixture();
        let disk = root.join("sda");
        fs::create_dir_all(disk.join("device")).unwrap();
        fs::create_dir(disk.join("queue")).unwrap();
        fs::write(disk.join("size"), "100").unwrap();
        fs::write(disk.join("device/model"), "  Example   disk\n").unwrap();
        fs::write(disk.join("queue/rotational"), "1").unwrap();
        fs::create_dir(root.join("loop0")).unwrap();
        let devices = physical_devices(&root);
        assert_eq!(
            devices,
            vec![json!({"name":"sda","model":"Example disk","kind":"HDD","size":51200})]
        );
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn app_validation_restricts_health_and_preserves_default_fields() {
        let app = json!({"name":" Example ","url":"https://example.org","health_url":"http://127.0.0.1:8888/status"});
        let result = validate_apps(&json!({"apps":[app]})).unwrap();
        assert_eq!(result[0]["name"], "Example");
        assert_eq!(result[0]["health_method"], "GET");
        let mut invalid = app.clone();
        invalid["health_url"] = json!("http://169.254.169.254/latest");
        assert!(validate_apps(&json!({"apps":[invalid]})).is_err());
        assert!(validate_apps(&json!({"apps":[app.clone(),app]})).is_err());
        for url in [
            "http://user:pass@localhost/",
            "http://@localhost/",
            "file:///etc/passwd",
            "http://localhost:0/",
        ] {
            assert!(valid_url(&json!(url)).is_none());
        }
    }
    #[test]
    fn launch_tokens_never_leave_allowed_authority() {
        let token = format!("/?token={}", "a".repeat(32));
        assert_eq!(
            launch_url(&token, "127.0.0.1:8765", &[]),
            Some(format!("http://127.0.0.1:3080{token}"))
        );
        assert!(launch_url(&token, "attacker.test:8765", &[]).is_none());
        assert!(launch_url(&token, "127.1:8765", &[]).is_none());
        assert!(launch_url(&token, "localhost:80", &[]).is_some());
        assert!(launch_url(&token, "127.0.0.1:8765@attacker.test", &[]).is_none());
        assert!(launch_url("/?token=short", "127.0.0.1:8765", &[]).is_none());
        assert!(launch_url(&token, "10.20.0.1:8765", &["10.20.0.1".into()]).is_some());
    }
    #[test]
    fn icon_parser_and_origin_reject_external_redirects() {
        assert_eq!(icon_links("<link rel='shortcut icon' href='/icon.png?x=1&amp;y=2'><link href=https://external.test rel=ICON>"),vec!["/icon.png?x=1&y=2","https://external.test"]);
        let origin = reqwest::Url::parse("http://127.0.0.1:3000/").unwrap();
        assert!(!same_origin(
            &origin,
            &origin.join("http://127.0.0.1:4000/icon").unwrap()
        ));
        assert!(!same_origin(
            &origin,
            &origin.join("http://user@127.0.0.1:3000/icon").unwrap()
        ));
    }
    #[test]
    fn atomic_registry_save_rejects_symlinks() {
        let root = fixture();
        let path = root.join("apps.json");
        fs::write(&path, "{\"apps\":[]}").unwrap();
        save_apps(&path, vec![]).unwrap();
        assert_eq!(read_json(&path), json!({"apps":[]}));
        let link = root.join("alias.json");
        std::os::unix::fs::symlink(&path, &link).unwrap();
        assert!(save_apps(&link, vec![]).is_err());
        fs::remove_dir_all(root).unwrap();
    }
}
