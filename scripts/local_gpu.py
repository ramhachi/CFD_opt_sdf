#!/usr/bin/env python3
"""LOCAL-GPU-01: locked WSL2 WaterLily tools. Never rewrites a rendered runner.

check-lock; render; run KERNEL --out DIR [--repeat N]; watch --out watchdog.csv;
bench --out bench.json. GPU commands are for the user's WSL2 machine only.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "infra/local_gpu"))
import capture_lock as C

WATCH_COLUMNS = ("elapsed_s", "clocks_sm_mhz", "temperature_gpu_c", "power_draw_w", "memory_used_mib", "driver_reset", "error", "reset_monitor_error")


def write_json(path, record):
    Path(path).write_bytes(C.canonical_bytes(record))


def check_lock(path=C.LOCK):
    lock = C.load_lock(path)
    config_path = lock["environment"].get("wsl", {}).get("settings", {}).get("wslconfig_path")
    options = {"wslconfig": config_path} if isinstance(config_path, str) else {}
    current = C.capture(julia=lock["environment"]["julia"]["executable"], **options)
    errors = C.required_errors(current)
    if errors:
        raise ValueError("; ".join(errors))
    if current["environment"] != lock["environment"]:
        changed = [key for key in sorted(set(current["environment"]) | set(lock["environment"]))
                   if current["environment"].get(key) != lock["environment"].get(key)]
        raise ValueError(f"environment differs from lock: {', '.join(changed)}; capture a new environment and gate")
    return lock


def query_values(fields):
    raw = C.probe(["nvidia-smi", "--query-gpu=" + ",".join(fields), "--format=csv,noheader,nounits"], timeout=10)
    if isinstance(raw, dict):
        return raw
    try:
        rows = list(csv.reader(raw.splitlines()))
        if len(rows) != 1 or len(rows[0]) != len(fields):
            raise ValueError("exactly one GPU telemetry row required")
        numbers = [float(value.strip()) for value in rows[0]]
        if not all(math.isfinite(value) for value in numbers):
            raise ValueError("non-finite GPU telemetry")
        return numbers
    except (ValueError, TypeError) as exc:
        return C.error(f"nvidia-smi telemetry: {exc}")


def query_memory():
    result = query_values(["memory.used"])
    return result if isinstance(result, dict) else result[0]


def query_watch():
    result = query_values(["clocks.sm", "temperature.gpu", "power.draw", "memory.used"])
    return result if isinstance(result, dict) else dict(zip(WATCH_COLUMNS[1:5], result))


def query_resets(started):
    """Observe Windows Display TDRs since start, through the WSL interop bridge.

    NoMatchingEventsFound is an observed empty set. An unavailable event log or
    interop bridge is not evidence of no reset. Scope is recorded in status.
    """
    since = started.replace("'", "")
    script = ("$ErrorActionPreference='Stop'; try { "
              f"$s=[DateTimeOffset]::Parse('{since}').UtcDateTime; "
              "$e=@(Get-WinEvent -FilterHashtable @{LogName='System';ProviderName='Display';Id=4101;StartTime=$s} -ErrorAction Stop); "
              "if($e.Count -gt 0){'RESET'}else{'NO_RESET'} "
              "} catch { if($_.FullyQualifiedErrorId -like 'NoMatchingEventsFound*'){'NO_RESET'}else{Write-Error $_;exit 1} }")
    result = C.probe(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], timeout=10)
    if isinstance(result, dict):
        return result
    if result not in ("RESET", "NO_RESET"):
        return C.error(f"unrecognized Windows reset observer response: {result}")
    return result == "RESET"


class Telemetry:
    """One worker, two fixed cadences; no third-party NVML dependency."""

    def __init__(self, csv_path, interval=60.0, memory_interval=10.0):
        self.path = Path(csv_path)
        self.interval, self.memory_interval = interval, memory_interval
        self.stop = threading.Event()
        self.started_utc = C.utc()
        self.started = time.monotonic()
        self.peak = C.error("no VRAM sample acquired")
        self.reset_errors = []
        self.reset_observations = 0
        self.telemetry_errors = []
        self.thread = threading.Thread(target=self.collect, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def collect(self):
        next_watch, next_memory = 0.0, 0.0
        try:
            with self.path.open("x", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=WATCH_COLUMNS)
                writer.writeheader()
                while not self.stop.is_set():
                    elapsed = time.monotonic() - self.started
                    if elapsed >= next_memory:
                        sample = query_memory()
                        if isinstance(sample, (int, float)) and math.isfinite(sample):
                            self.peak = max(self.peak, sample) if isinstance(self.peak, (int, float)) else sample
                        else:
                            self.telemetry_errors.append(sample)
                        next_memory += self.memory_interval
                    if elapsed >= next_watch:
                        sample, reset = query_watch(), query_resets(self.started_utc)
                        row = {"elapsed_s": f"{elapsed:.6f}", "driver_reset": "", "error": "", "reset_monitor_error": ""}
                        if "error" in sample:
                            row["error"] = sample["error"]
                            self.telemetry_errors.append(sample)
                        else:
                            row.update(sample)
                        if isinstance(reset, dict):
                            row["reset_monitor_error"] = reset["error"]
                            self.reset_errors.append(reset["error"])
                        else:
                            row["driver_reset"] = "true" if reset else "false"
                            self.reset_observations += 1
                        writer.writerow(row)
                        handle.flush()
                        next_watch += self.interval
                    self.stop.wait(min(max(0.01, min(next_watch, next_memory) - (time.monotonic() - self.started)), 1.0))
        except (OSError, ValueError, TypeError) as exc:
            self.telemetry_errors.append(C.error(exc))

    def finish(self, completed=True):
        self.stop.set()
        self.thread.join(timeout=35)
        ended = C.utc()
        record = {"schema_version": 1, "started_utc": self.started_utc, "finished_utc": ended,
                  "wall_seconds": time.monotonic() - self.started, "interval_s": self.interval,
                  "memory_interval_s": self.memory_interval, "completed": completed and not self.thread.is_alive(),
                  "driver_reset_monitor": {"available": self.reset_observations > 0 and not self.reset_errors,
                                           "source": "Windows System event 4101 (Display TDR), since started_utc",
                                           "errors": self.reset_errors}, "telemetry_errors": self.telemetry_errors,
                  "watchdog_sha256": C.sha(self.path) if self.path.is_file() else C.error("watchdog not created")}
        write_json(self.path.with_name("watchdog_status.json"), record)
        return record


@contextmanager
def dataset_mount(kernel, dataset):
    """Only needed by runners with absolute /kaggle/input paths, not harness v1.1."""
    if dataset is None:
        yield
        return
    metadata = C.jload(Path(kernel) / "kernel-metadata.json")
    sources = metadata.get("dataset_sources", [])
    if len(sources) != 1 or not re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_-]+", sources[0]):
        raise ValueError("--dataset requires exactly one owner/slug in kernel metadata; registered harness has no datasets")
    if not Path(dataset).is_dir():
        raise ValueError("dataset directory missing")
    import fcntl  # WSL2/Linux only; not used by the ordinary CAMPAIGN_WORK_ROOT path
    helper = ROOT / "infra/local_gpu/bind_dataset.sh"
    slug = sources[0].split("/")[1]
    # One absolute input namespace, so hold the lease for the entire child run.
    with Path("/tmp/cfd-local-gpu-input.lock").open("a") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        subprocess.run(["sudo", "-n", "sh", str(helper), "mount", str(Path(dataset).resolve()), slug], check=True)
        try:
            yield
        finally:
            subprocess.run(["sudo", "-n", "sh", str(helper), "unmount", str(Path(dataset).resolve()), slug], check=True)


def kernel_metadata(kernel):
    kernel = Path(kernel)
    record = C.jload(kernel / "local_kernel.json")
    if record.get("backend_profile") != C.PROFILE or record.get("used_gpu_count") != 1:
        raise ValueError("run requires a rendered local_rtx4070ti singleton kernel")
    if record.get("runner_sha256") != C.sha(kernel / "runner.py"):
        raise ValueError("runner SHA-256 differs from local render record")
    if not re.fullmatch(r"[0-9a-f]{40}", record.get("source_commit", "")):
        raise ValueError("kernel needs its pinned full source_commit")
    baked = C.literal_constants(kernel / "runner.py", ("PINS", "PROJECT", "SOURCE_COMMIT", "CAMPAIGN", "KERNEL", "SMOKE"))
    for key, value in (("SOURCE_COMMIT", record["source_commit"]), ("CAMPAIGN", record["campaign_path"]),
                       ("KERNEL", record["kernel"]), ("SMOKE", record["smoke"]), ("PROJECT", "julia/CFDSDFWaterLilyT4")):
        if type(baked.get(key)) is not type(value) or baked.get(key) != value:
            raise ValueError(f"rendered runner {key} differs from metadata/GPU project")
    pins = baked.get("PINS")
    paths = ["julia/CFDSDFWaterLilyT4/Manifest.toml", "julia/CFDSDFWaterLilyT4/Project.toml"]
    if not isinstance(pins, dict) or not all(isinstance(pins.get(path), str) and re.fullmatch(r"[0-9a-f]{64}", pins[path]) for path in paths):
        raise ValueError("rendered runner lacks GPU project runtime pins")
    record["runtime_project_pins"] = {path: pins[path] for path in paths}
    return record


def copy_resume(out, prior_record, checkpoint, lock_sha):
    prior_path, checkpoint = Path(prior_record).resolve(), Path(checkpoint).resolve()
    prior = C.jload(prior_path)
    if prior.get("done") is not False or not isinstance(prior.get("returncode"), int) or prior["returncode"] >= 0:
        raise ValueError("resume requires a recorded interrupted process (negative returncode, no DONE)")
    if prior.get("lock_sha256") != lock_sha:
        raise ValueError("resume environment lock differs")
    try:
        rel = checkpoint.relative_to(prior_path.parent).as_posix()
    except ValueError as exc:
        raise ValueError("checkpoint must belong to the prior run directory") from exc
    digest = C.sha(checkpoint)
    if prior.get("output_sha256", {}).get(rel) != digest:
        raise ValueError("checkpoint SHA differs from interrupted run record")
    dest = out / "resume_input"
    dest.mkdir()
    shutil.copy2(prior_path, dest / "prior_local_run.json")
    shutil.copy2(checkpoint, dest / "checkpoint.bin")
    if (prior_path.parent / "local_run.log").is_file():
        shutil.copy2(prior_path.parent / "local_run.log", dest / "prior_local_run.log")
    return {"resumed": True, "checkpoint_path": "resume_input/checkpoint.bin", "checkpoint_sha256": digest,
            "interrupted_run": "resume_input/prior_local_run.json", "interrupted_run_sha256": C.sha(dest / "prior_local_run.json"),
            "interrupted_checkpoint_path": rel}


def run(kernel, out, dataset=None, *, lock_path=C.LOCK, checkpoint_every=0, resume_from=None, resume_checkpoint=None, interrupt_after=None):
    kernel, out, lock_path = Path(kernel).resolve(), Path(out).resolve(), Path(lock_path).resolve()
    if out.exists():
        raise ValueError(f"refusing to overwrite existing run directory: {out}")
    meta = kernel_metadata(kernel)
    lock = check_lock(lock_path)
    for name in ("Manifest", "Project"):
        field = "manifest_sha256" if name == "Manifest" else "project_sha256"
        if meta["runtime_project_pins"][f"julia/CFDSDFWaterLilyT4/{name}.toml"] != lock["environment"]["project"].get(field):
            raise ValueError(f"rendered GPU {name} pin differs from environment lock; refusing to launch")
    if checkpoint_every < 0 or (interrupt_after is not None and interrupt_after <= 0):
        raise ValueError("checkpoint period must be nonnegative; interrupt delay must be positive")
    if bool(resume_from) != bool(resume_checkpoint):
        raise ValueError("--resume-from and --resume-checkpoint are required together")
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="0", CUDA_DEVICE_ORDER="PCI_BUS_ID", JULIA_NUM_THREADS="1",
               CAMPAIGN_WORK_ROOT=str(out), LOCAL_GPU_JULIA=lock["environment"]["julia"]["executable"],
               LOCAL_GPU_JULIA_SHA256=lock["environment"]["julia"]["sha256"],
               LOCAL_GPU_CHECKPOINT_PATH=str(out / "checkpoint.bin"), LOCAL_GPU_CHECKPOINT_EVERY=str(checkpoint_every))
    env.pop("LOCAL_GPU_RESUME_PATH", None)
    out.mkdir(parents=True)
    record = {"schema_version": 1, "backend_profile": C.PROFILE, "used_gpu_count": 1, "lock_sha256": C.sha(lock_path),
              "gpu_identity": lock["environment"]["gpu"], "cuda_visible_devices": "0", "cuda_device_order": "PCI_BUS_ID",
              "julia": lock["environment"]["julia"], "project": lock["environment"]["project"],
              "runtime_project_pins": meta["runtime_project_pins"],
              "runner_sha256": C.sha(kernel / "runner.py"), "wrapper_sha256": C.sha(__file__),
              "campaign_path": meta["campaign_path"], "source_commit": meta["source_commit"], "kernel": meta["kernel"], "smoke": meta["smoke"],
              "checkpoint_every": checkpoint_every, "started_utc": C.utc()}
    if resume_from:
        record["resume"] = copy_resume(out, resume_from, resume_checkpoint, record["lock_sha256"])
        env["LOCAL_GPU_RESUME_PATH"] = str(out / record["resume"]["checkpoint_path"])
    started = time.monotonic()
    stages = {"runner_startup": 0.0}
    stage_name, stage_started = "runner_startup", started
    telemetry = None
    process = None
    interrupted = False

    def log_child():
        nonlocal stage_name, stage_started
        with (out / "local_run.log").open("w") as handle:
            for line in process.stdout:
                handle.write(line)
                handle.flush()
                if line.startswith("RUN "):
                    now = time.monotonic()
                    stages[stage_name] = stages.get(stage_name, 0.0) + now - stage_started
                    stage_name = "instantiate" if "Pkg.instantiate" in line else "solver" if ".jl " in line else "gpu_probe"
                    stage_started = now

    def interrupt(signum, frame):
        nonlocal interrupted
        interrupted = True
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signum)

    old_handlers = {}
    code = 1
    try:
        with dataset_mount(kernel, dataset):
            telemetry = Telemetry(out / "watchdog.csv").start()
            process = subprocess.Popen([sys.executable, str(kernel / "runner.py")], cwd=out, env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", start_new_session=True)
            if threading.current_thread() is threading.main_thread():
                for sig in (signal.SIGTERM, signal.SIGINT):
                    old_handlers[sig] = signal.getsignal(sig)
                    signal.signal(sig, interrupt)
            reader = threading.Thread(target=log_child)
            reader.start()
            while process.poll() is None:
                if interrupt_after is not None and time.monotonic() - started >= interrupt_after and not interrupted:
                    interrupt(signal.SIGTERM, None)
                time.sleep(0.05)
            code = process.wait()
            reader.join()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        record["execution_error"] = str(exc)
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            code = process.wait()
        code = code or 1
    finally:
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
        now = time.monotonic()
        stages[stage_name] = stages.get(stage_name, 0.0) + now - stage_started
        status = telemetry.finish() if telemetry else {"error": "telemetry not started"}
        dones = sorted(out.rglob("DONE"))
        record.update(finished_utc=C.utc(), wall_seconds=time.monotonic() - started,
                      stage_wall_seconds=stages, stage_wall_definition="elapsed between runner RUN lines, including startup; not CUDA event timing",
                      peak_vram_mib=telemetry.peak if telemetry else C.error("telemetry not started"),
                      telemetry_status=status, returncode=code,
                      runner_returncode=process.returncode if process is not None else C.error("runner not started"),
                      interrupted=interrupted,
                      done=code == 0 and len(dones) == 1 and not list(out.rglob("ERROR.txt")),
                      kernel_output=dones[0].parent.relative_to(out).as_posix() if len(dones) == 1 else C.error("unique DONE not found"))
        # Hash after logs/telemetry are closed; local_run excludes itself.
        record["output_sha256"] = {p.relative_to(out).as_posix(): C.sha(p) for p in sorted(out.rglob("*")) if p.is_file()}
        write_json(out / "local_run.json", record)
    return code if code else (0 if record["done"] else 1)


def watch(out, duration=21600.0, interval=60.0):
    out = Path(out)
    if duration <= 0 or interval != 60.0:
        raise ValueError("watch duration must be positive and the R6 cadence is fixed at 60 seconds")
    if out.exists() or out.with_name("watchdog_status.json").exists():
        raise ValueError(f"refusing to overwrite watchdog output: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    telemetry = Telemetry(out, interval).start()
    completed = True
    try:
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            time.sleep(min(1.0, max(0.001, deadline - time.monotonic())))
    except KeyboardInterrupt:
        completed = False
    finally:
        result = telemetry.finish(completed=completed)
    return 0 if completed else 130


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("check-lock")
    c.add_argument("--lock", type=Path, default=C.LOCK)
    c = sub.add_parser("render")
    c.add_argument("campaign", type=Path)
    c.add_argument("--prepare-campaign", type=Path)
    c.add_argument("--job")
    c.add_argument("--source-commit")
    c.add_argument("--kernel")
    c.add_argument("--out", type=Path)
    c.add_argument("--smoke", action="store_true")
    c = sub.add_parser("run")
    c.add_argument("kernel", type=Path)
    c.add_argument("--out", type=Path, required=True)
    c.add_argument("--lock", type=Path, default=C.LOCK)
    c.add_argument("--dataset", type=Path)
    c.add_argument("--repeat", type=int, default=1)
    c.add_argument("--checkpoint-every", type=int, default=0)
    c.add_argument("--resume-from", type=Path)
    c.add_argument("--resume-checkpoint", type=Path)
    c.add_argument("--interrupt-after", type=float)
    c = sub.add_parser("watch")
    c.add_argument("--out", type=Path, required=True)
    c.add_argument("--duration", type=float, default=21600.0)
    c = sub.add_parser("bench")
    c.add_argument("--out", type=Path, required=True)
    c.add_argument("--lock", type=Path, default=C.LOCK)
    c.add_argument("--steps", type=int, default=100)
    c.add_argument("--warmup", type=int, default=10)
    c.add_argument("--host-label", default="wsl2")
    args = p.parse_args(argv)
    try:
        if args.command == "check-lock":
            check_lock(args.lock)
            print(C.canonical_bytes({"status": "MATCH", "lock_sha256": C.sha(args.lock)}).decode(), end="")
            return 0
        if args.command == "render":
            sys.path.insert(0, str(ROOT / "src"))
            from cfd_harness.backend_profiles import create_local_campaign, render_local
            if args.prepare_campaign:
                if args.out or args.source_commit or args.kernel:
                    raise ValueError("prepare-campaign and render are separate steps; commit/push the new campaign before rendering")
                result = create_local_campaign(args.campaign, args.prepare_campaign, job=args.job)
            else:
                if not all((args.out, args.source_commit, args.kernel)) or args.job:
                    raise ValueError("render needs --out --source-commit --kernel; --job applies only to prepare-campaign")
                result = render_local(args.campaign, args.source_commit, args.kernel, args.out, smoke=args.smoke)
            print(str(result))
            return 0
        if args.command == "watch":
            return watch(args.out, args.duration)
        if args.command == "bench":
            lock = check_lock(args.lock)
            if args.out.exists():
                raise ValueError(f"refusing to overwrite bench output: {args.out}")
            env = dict(os.environ, CUDA_VISIBLE_DEVICES="0", CUDA_DEVICE_ORDER="PCI_BUS_ID", JULIA_NUM_THREADS="1")
            return subprocess.run([lock["environment"]["julia"]["executable"], "--startup-file=no", f"--project={C.PROJECT}",
                                   str(ROOT / "scripts/local_gpu_bench.jl"), "--out", str(args.out), "--steps", str(args.steps),
                                   "--warmup", str(args.warmup), "--host-label", args.host_label], env=env).returncode
        if args.repeat <= 0 or args.repeat > 1 and (args.resume_from or args.interrupt_after):
            raise ValueError("repeat must be positive; interruption/resume requires a single run")
        group_watch = None
        if args.repeat > 1:
            if args.out.exists() and any(args.out.iterdir()):
                raise ValueError(f"refusing to overwrite existing repeat group: {args.out}")
            args.out.mkdir(parents=True, exist_ok=True)
            group_watch = Telemetry(args.out / "watchdog.csv").start()
        complete = False
        try:
            for number in range(1, args.repeat + 1):
                out = args.out if args.repeat == 1 else args.out / f"repeat_{number:03d}"
                code = run(args.kernel, out, args.dataset, lock_path=args.lock, checkpoint_every=args.checkpoint_every,
                           resume_from=args.resume_from, resume_checkpoint=args.resume_checkpoint, interrupt_after=args.interrupt_after)
                if code:
                    return code if code > 0 else 128 - code
            complete = True
        finally:
            if group_watch:
                group_watch.finish(completed=complete)
        return 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError) as exc:
        print(C.canonical_bytes({"status": "ERROR", "errors": [str(exc)]}).decode(), end="")
        return 2


if __name__ == "__main__":
    sys.exit(main())
