import ctypes
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from django.conf import settings


MODEL_VIETNAMEOCR = "model_vietnameocr"
MODEL_YOLO_X = "model_yolo_x"

MODEL_KEYS = (MODEL_VIETNAMEOCR, MODEL_YOLO_X)

MODEL_ENDPOINTS = {
    MODEL_VIETNAMEOCR: "/api/model_vietnameocr/recognize/",
    MODEL_YOLO_X: "/api/model_yolo_x/detect/",
}

MODEL_BASE_URL_SETTINGS = {
    MODEL_VIETNAMEOCR: "AI_VIETNAMEOCR_BASE_URL",
    MODEL_YOLO_X: "AI_YOLO_X_BASE_URL",
}

COMPONENTS = {
    "upload_worker": {
        "id": "upload_worker",
        "label": "Upload worker",
        "description": "Xu ly upload, lam phang anh va cat o phieu bau.",
        "kind": "celery",
        "queue": "upload_queue",
        "hostname": "upload_worker@%h",
        "default_concurrency": 1,
        "concurrency_label": "Concurrency",
    },
    "counting_worker": {
        "id": "counting_worker",
        "label": "Counting worker",
        "description": "Xu ly kiem phieu tu dong tu counting_queue.",
        "kind": "celery",
        "queue": "counting_queue",
        "hostname": "counting_worker1@%h",
        "default_concurrency": 1,
        "concurrency_label": "Concurrency",
    },
    MODEL_VIETNAMEOCR: {
        "id": MODEL_VIETNAMEOCR,
        "label": "Model VietNameOCR",
        "description": "Nhan dien ten ung vien.",
        "kind": "ai_model",
        "model_key": MODEL_VIETNAMEOCR,
        "port": 8081,
        "default_concurrency": 4,
        "concurrency_label": "Threads",
    },
    MODEL_YOLO_X: {
        "id": MODEL_YOLO_X,
        "label": "Yolo_x",
        "description": "Nhan dien dau X tren o dong y/khong dong y.",
        "kind": "ai_model",
        "model_key": MODEL_YOLO_X,
        "port": 8082,
        "default_concurrency": 4,
        "concurrency_label": "Threads",
    },
}

MODEL_COMPONENT_IDS = {
    component["model_key"]: component_id
    for component_id, component in COMPONENTS.items()
    if component["kind"] == "ai_model"
}


def runtime_dir() -> Path:
    return Path(settings.BASE_DIR) / "runtime"


def logs_dir() -> Path:
    return runtime_dir() / "logs"


def state_file() -> Path:
    return runtime_dir() / "system_config_state.json"


def ai_server_dir() -> Path:
    return Path(settings.BASE_DIR).parent / "ai_core" / "ai_server"


def ensure_runtime_dirs():
    logs_dir().mkdir(parents=True, exist_ok=True)


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_state() -> dict:
    ensure_runtime_dirs()
    path = state_file()
    if not path.exists():
        return {"components": {}}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"components": {}}


def save_state(state: dict):
    ensure_runtime_dirs()
    path = state_file()
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def normalize_concurrency(value, default: int) -> int:
    try:
        concurrency = int(value)
    except (TypeError, ValueError):
        concurrency = default
    return max(1, min(concurrency, 32))


def component_log_path(component_id: str) -> Path:
    if component_id not in COMPONENTS:
        raise ValueError("Unknown component")
    return logs_dir() / f"{component_id}.log"


def _pid_is_running_windows(pid: int) -> bool:
    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False

    exit_code = ctypes.c_ulong()
    try:
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def pid_is_running(pid) -> bool:
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False

    if pid <= 0:
        return False

    if os.name == "nt":
        return _pid_is_running_windows(pid)

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _component_cwd(component: dict) -> Path:
    if component["kind"] == "ai_model":
        return ai_server_dir()
    return Path(settings.BASE_DIR)


def _component_env(component: dict) -> dict:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    if component["kind"] == "ai_model":
        env["DJANGO_SETTINGS_MODULE"] = "ai_server.settings"
        env["AI_ENABLED_MODELS"] = component["model_key"]
        env["AI_SERVER_PORT"] = str(component["port"])
    else:
        env["DJANGO_SETTINGS_MODULE"] = "kiem_phieu_bau.settings"

    return env


def _component_command(component: dict, concurrency: int) -> list[str]:
    if component["kind"] == "ai_model":
        return [
            sys.executable,
            "run_waitress_ai.py",
            "--models",
            component["model_key"],
            "--port",
            str(component["port"]),
            "--threads",
            str(concurrency),
        ]

    return [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "kiem_phieu_bau",
        "worker",
        "-Q",
        component["queue"],
        "--pool=gevent",
        f"--concurrency={concurrency}",
        f"--hostname={component['hostname']}",
        "-l",
        "info",
    ]


def _creation_kwargs() -> dict:
    kwargs = {"stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return kwargs


def get_component_status(component_id: str) -> dict:
    if component_id not in COMPONENTS:
        raise ValueError("Unknown component")

    state = load_state()
    component_state = state.get("components", {}).get(component_id, {})
    pid = component_state.get("pid")
    running = pid_is_running(pid)
    component = COMPONENTS[component_id]

    return {
        **component,
        "pid": pid,
        "running": running,
        "started_at": component_state.get("started_at"),
        "stopped_at": component_state.get("stopped_at"),
        "concurrency": component_state.get("concurrency", component["default_concurrency"]),
        "command": component_state.get("command", ""),
        "log_file": str(component_log_path(component_id)),
        "base_url": get_model_base_url(component["model_key"]) if component["kind"] == "ai_model" else "",
    }


def get_all_component_statuses() -> list[dict]:
    return [get_component_status(component_id) for component_id in COMPONENTS]


def start_component(component_id: str, concurrency=None) -> tuple[bool, str]:
    if component_id not in COMPONENTS:
        return False, "Thanh phan khong hop le."

    status = get_component_status(component_id)
    if status["running"]:
        return False, f"{status['label']} dang chay voi PID {status['pid']}."

    component = COMPONENTS[component_id]
    concurrency = normalize_concurrency(concurrency, component["default_concurrency"])
    command = _component_command(component, concurrency)
    log_path = component_log_path(component_id)
    cwd = _component_cwd(component)

    if not cwd.exists():
        return False, f"Khong tim thay thu muc chay: {cwd}"

    with log_path.open("ab") as log_handle:
        header = f"\n\n===== START {component['label']} at {now_text()} =====\n"
        header += f"CWD: {cwd}\n"
        header += f"COMMAND: {' '.join(command)}\n\n"
        log_handle.write(header.encode("utf-8"))
        log_handle.flush()

        try:
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                env=_component_env(component),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                **_creation_kwargs(),
            )
        except Exception as exc:
            return False, f"Khong the bat {component['label']}: {exc}"

    time.sleep(0.4)
    exited_early = process.poll()

    state = load_state()
    state.setdefault("components", {})[component_id] = {
        "pid": process.pid,
        "started_at": now_text(),
        "stopped_at": None,
        "concurrency": concurrency,
        "command": " ".join(command),
        "port": component.get("port"),
    }
    save_state(state)

    if exited_early is not None:
        return False, f"{component['label']} vua thoat voi ma {exited_early}. Hay xem log."

    return True, f"Da bat {component['label']} voi PID {process.pid}."


def _terminate_pid(pid: int):
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return

    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except Exception:
        os.kill(pid, signal.SIGTERM)


def stop_component(component_id: str) -> tuple[bool, str]:
    if component_id not in COMPONENTS:
        return False, "Thanh phan khong hop le."

    state = load_state()
    component_state = state.setdefault("components", {}).setdefault(component_id, {})
    pid = component_state.get("pid")
    component = COMPONENTS[component_id]

    if not pid_is_running(pid):
        component_state["stopped_at"] = now_text()
        save_state(state)
        return False, f"{component['label']} khong dang chay."

    _terminate_pid(int(pid))
    time.sleep(0.5)
    component_state["stopped_at"] = now_text()
    save_state(state)

    return True, f"Da tat {component['label']}."


def restart_component(component_id: str, concurrency=None) -> tuple[bool, str]:
    stop_component(component_id)
    return start_component(component_id, concurrency)


def tail_log(component_id: str, max_lines: int = 200, max_bytes: int = 200_000) -> str:
    log_path = component_log_path(component_id)
    if not log_path.exists():
        return "Chua co log."

    size = log_path.stat().st_size
    with log_path.open("rb") as fh:
        if size > max_bytes:
            fh.seek(size - max_bytes)
        data = fh.read()

    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return "\n".join(lines[-max_lines:]) if lines else "Log rong."


def _settings_model_base_url(model_key: str) -> str:
    setting_name = MODEL_BASE_URL_SETTINGS.get(model_key)
    base_url = getattr(settings, setting_name, None) if setting_name else None
    return (base_url or settings.AI_SERVER_BASE_URL).rstrip("/")


def get_managed_model_base_url(model_key: str) -> str | None:
    component_id = MODEL_COMPONENT_IDS.get(model_key)
    if not component_id:
        return None

    state = load_state()
    component_state = state.get("components", {}).get(component_id, {})
    if not pid_is_running(component_state.get("pid")):
        return None

    component = COMPONENTS[component_id]
    return f"http://127.0.0.1:{component['port']}"


def get_model_base_url(model_key: str) -> str:
    return get_managed_model_base_url(model_key) or _settings_model_base_url(model_key)


def get_model_api_url(model_key: str) -> str:
    endpoint = MODEL_ENDPOINTS[model_key]
    return f"{get_model_base_url(model_key)}{endpoint}"


def get_model_health_url(model_key: str) -> str:
    return f"{get_model_base_url(model_key)}/api/health/"


def get_ai_model_health_statuses(timeout=None) -> dict:
    import requests

    statuses = {}
    timeout = settings.AI_SERVER_HEALTH_TIMEOUT if timeout is None else timeout
    for model_key in MODEL_KEYS:
        try:
            response = requests.get(get_model_health_url(model_key), timeout=timeout)
            response.raise_for_status()
            data = response.json()
            statuses[model_key] = bool(data.get("services", {}).get(model_key))
        except Exception:
            statuses[model_key] = False
    return statuses

