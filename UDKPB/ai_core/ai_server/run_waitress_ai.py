"""
Waitress WSGI server for the AI server.

The server runs one process so the three AI models are loaded only once.
"""
import logging
import os
import socket
import sys

from waitress import serve

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ai_server.settings")

import django

django.setup()

from ai_server.wsgi import application
from api.model_services import ResNet18CrossedService, ResNet18XService, VietNameOCRService


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
        VietNameOCRService()
        print("model_vietnameocr loaded successfully")

        ResNet18XService()
        print("model_resnet18_x loaded successfully")

        ResNet18CrossedService()
        print("model_resnet18_crossed loaded successfully")
    except Exception as exc:
        print(f"Error loading models: {exc}")
        sys.exit(1)

    print("-" * 70)
    print("Process: 1 Threads: 4")
    print("Timeout: 300s")
    print()
    print("Access URLs:")
    print("   - Local:   http://127.0.0.1:8081")
    print(f"   - Network: http://{local_ip}:8081")
    print()

    serve(
        application,
        host="0.0.0.0",
        port=8081,
        threads=4,
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
