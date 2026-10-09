# Runtime performance sample

This is a first low-load sample from the live Debian target on 2026-10-09. It is a baseline for later comparisons, not a claim that every performance acceptance test is complete.

## Environment and method

- Hardware: Dell OptiPlex Micro 7010, Intel Core i5-13500T, 16 GiB RAM, NVMe storage.
- The dashboard and OpenCode Web services were active. OpenCode had no provider login or coding workload. The dashboard was open in a browser.
- Host CPU busy percentage was sampled from `/proc/stat` across 10 seconds.
- Service memory came from systemd `MemoryCurrent` for each service cgroup.
- API timings were five consecutive local loopback `curl` requests per endpoint. These omit SSH tunnel and browser rendering time.
- Swap counters were compared across a separate 10-second idle interval.

## Observations

| Measurement | Result |
| --- | ---: |
| Host CPU busy, 10 seconds | 0.69% |
| Available system memory | about 13 GiB |
| Dashboard service memory | 24,256,512 bytes (23.1 MiB) |
| OpenCode Web service memory | 239,628,288 bytes (228.4 MiB) |
| Dashboard `/api/health`, median of 5 | 0.76 ms |
| Dashboard `/api/metrics`, warm median of 4 | 5.52 ms |
| Dashboard `/api/metrics`, first request | 95.29 ms |
| Dashboard `/api/apps`, median of 5 | 17.37 ms |
| Disk swap used | about 4 GiB of 15 GiB |
| Swap-in / swap-out counter change over 10 seconds | none |

The first metrics request was slower than the next four; this small sample cannot determine whether that is repeatable cold-start work. The nonzero swap allocation did not change during the sample. With 13 GiB available and no observed swap traffic, adding ZRAM is not justified by this baseline.

## Still to measure

- Initial page load and navigation interaction time through the SSH tunnel, with repeated runs.
- CPU and memory with the dashboard open versus closed over longer samples.
- File upload and download throughput, including a test larger than available RAM, through Cockpit Files after the owner signs in.
- VPN latency and throughput; direct VPN browser access is disabled by the SSH-only access choice.
- Provider request latency and memory under authenticated LiteLLM / OmniRoute traffic.

Repeat the measurements after material changes and record the exact commit, target state, sample length, and whether the browser was open.
