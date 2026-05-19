"""
Waitress WSGI server for the AI server.

The server runs one process so enabled AI models are loaded only once.
"""
import argparse
import logging
import os
import socket
import sys

from waitress import serve


ALL_MODEL_KEYS = ("model_vietnameocr", "model_resnet18_x", "model_resnet18_crossed")


def _parse_args():
    parser = argparse.ArgumentParser(description="Run the AI Waitress server")
    parser.add_argument(
        "--models",
        default=os.getenv("AI_ENABLED_MODELS", "all"),
        help="Comma-separated models to load, or 'all'.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("AI_SERVER_PORT", "8081")),
        help="Port for the AI server.",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=int(os.getenv("AI_SERVER_THREADS", "4")),
        help="Waitress worker threads.",
    )
    args, _unknown = parser.parse_known_args()
    return args


def _normalize_models(raw_models):
    raw_models = (raw_models or "all").strip()
    if raw_models.lower() in {"all", "*"}:
        return list(ALL_MODEL_KEYS)

    models = [item.strip() for item in raw_models.split(",") if item.strip()]
    invalid_models = [model for model in models if model not in ALL_MODEL_KEYS]
    if invalid_models:
        raise SystemExit(f"Invalid model(s): {', '.join(invalid_models)}")
    return models


BOOT_ARGS = _parse_args()
ENABLED_MODELS = _normalize_models(BOOT_ARGS.models)
os.environ["AI_ENABLED_MODELS"] = ",".join(ENABLED_MODELS)
os.environ["AI_SERVER_PORT"] = str(BOOT_ARGS.port)
os.environ["AI_SERVER_THREADS"] = str(BOOT_ARGS.threads)
os.environ["DJANGO_SETTINGS_MODULE"] = "ai_server.settings"

import django

django.setup()

from ai_server.wsgi import application
from api.model_services import MODEL_SERVICE_CLASSES


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%d/%b/%Y %H:%M:%S",
    stream=sys.stdout,
)


if __name__ == "__main__":
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)

    try:
        for model_key in ENABLED_MODELS:
            MODEL_SERVICE_CLASSES[model_key]()
            print(f"{model_key} loaded successfully")
    except Exception as exc:
        print(f"Error loading models: {exc}")
        sys.exit(1)

    print("-" * 70)
    print(f"Enabled models: {', '.join(ENABLED_MODELS) or 'none'}")
    print(f"Process: 1 Threads: {BOOT_ARGS.threads}")
    print("Timeout: 300s")
    print()
    print("Access URLs:")
    print(f"   - Local:   http://127.0.0.1:{BOOT_ARGS.port}")
    print(f"   - Network: http://{local_ip}:{BOOT_ARGS.port}")
    print()

    serve(
        application,
        host="0.0.0.0",
        port=BOOT_ARGS.port,
        threads=BOOT_ARGS.threads,
        channel_timeout=300,
        backlog=256,
        connection_limit=100,
        recv_bytes=65536,
        send_bytes=65536,
        cleanup_interval=30,
        asyncore_use_poll=True,
        expose_tracebacks=True,
        clear_untrusted_proxy_headers=False,
    )
