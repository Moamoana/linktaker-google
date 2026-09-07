#!/usr/bin/env python3
"""Relay proxy CONNECT lokal — jembatan untuk proxy yang tidak mengirim
tantangan auth yang sah ke Chromium.

Kenapa ini ada: sebagian proxy (mis. proxycrawler.dashboard.nolimit.id) membalas
CONNECT tanpa kredensial dengan 407, tapi TANPA header `Proxy-Authenticate` yang
sah. curl tetap lolos karena dia menempelkan `Proxy-Authorization` duluan tanpa
menunggu tantangan resmi. Chromium menolak melakukan itu — dia mewajibkan header
tantangan yang sah sebelum mau kirim kredensial apa pun — sehingga selalu gagal
dengan ERR_PROXY_AUTH_UNSUPPORTED walau kredensialnya sendiri benar.

Relay ini jalan di localhost, menerima koneksi dari Chromium TANPA auth sama
sekali, lalu meneruskannya ke proxy asli dengan header Proxy-Authorization
Basic yang sudah ditempel duluan — persis seperti curl. Chromium tidak pernah
bicara langsung dengan proxy asli, jadi tidak pernah melihat balasan 407-nya
yang cacat itu.

Pakai:
    UPSTREAM_PROXY=http://user:pass@proxycrawler.dashboard.nolimit.id:2570 \\
    python3 deploy/proxy-relay.py

Lalu arahkan LinkTaker ke relay ini, TANPA kredensial:
    PROXY=http://127.0.0.1:8899 ./deploy/run-linktaker.sh

deploy/proxy-relay.sh membungkus ini — dia membaca UPSTREAM_PROXY dari
deploy/linktaker.env supaya kredensialnya tidak pernah tertulis di baris
perintah atau di file yang di-track git.
"""

import base64
import os
import socket
import sys
import threading
from urllib.parse import unquote, urlparse

RELAY_HOST = os.environ.get("RELAY_HOST", "127.0.0.1")
RELAY_PORT = int(os.environ.get("RELAY_PORT", "8899"))

UPSTREAM_PROXY = os.environ.get("UPSTREAM_PROXY", "").strip()
if not UPSTREAM_PROXY:
    print("UPSTREAM_PROXY belum diisi — contoh: "
          "http://user:pass@proxycrawler.dashboard.nolimit.id:2570", file=sys.stderr)
    sys.exit(1)

_parsed = urlparse(UPSTREAM_PROXY if "://" in UPSTREAM_PROXY else "http://" + UPSTREAM_PROXY)
UPSTREAM_HOST = _parsed.hostname
UPSTREAM_PORT = _parsed.port or 80
if not UPSTREAM_HOST:
    print(f"UPSTREAM_PROXY tidak valid: {UPSTREAM_PROXY!r}", file=sys.stderr)
    sys.exit(1)

AUTH_HEADER = None
if _parsed.username:
    user = unquote(_parsed.username)
    pw = unquote(_parsed.password or "")
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    AUTH_HEADER = f"Proxy-Authorization: Basic {token}\r\n"


def log(msg):
    print(msg, flush=True)


def pipe(src, dst):
    """Salin byte dari src ke dst sampai salah satu sisi tertutup."""
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _with_auth(head_text: str) -> str:
    """Tempel Proxy-Authorization ke blok header, kalau client belum kirim sendiri."""
    if AUTH_HEADER and "proxy-authorization:" not in head_text.lower():
        return head_text.rstrip("\r\n") + "\r\n" + AUTH_HEADER + "\r\n"
    return head_text + "\r\n"


def handle_client(client):
    upstream = None
    try:
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = client.recv(65536)
            if not chunk:
                return
            buf += chunk
            if len(buf) > 65536:
                return  # header permintaan tidak wajar besarnya — putuskan saja

        head, _, rest = buf.partition(b"\r\n\r\n")
        request_line = head.split(b"\r\n", 1)[0].decode(errors="replace")
        method = request_line.split(" ", 1)[0].upper()

        upstream = socket.create_connection((UPSTREAM_HOST, UPSTREAM_PORT), timeout=15)
        out = _with_auth(head.decode(errors="replace")).encode()

        if method == "CONNECT":
            upstream.sendall(out)

            resp = b""
            while b"\r\n\r\n" not in resp:
                chunk = upstream.recv(65536)
                if not chunk:
                    break
                resp += chunk
            client.sendall(resp)

            if not resp.startswith((b"HTTP/1.1 200", b"HTTP/1.0 200")):
                return  # upstream menolak — biarkan client melihat balasannya lalu putus

            t = threading.Thread(target=pipe, args=(client, upstream), daemon=True)
            t.start()
            pipe(upstream, client)
        else:
            # Permintaan HTTP polos — jarang dipakai (search engine di sini selalu
            # https), tapi ditangani juga supaya tidak diam-diam gagal.
            upstream.sendall(out + rest)
            t = threading.Thread(target=pipe, args=(upstream, client), daemon=True)
            t.start()
            pipe(client, upstream)
    except Exception as e:
        log(f"  error: {e}")
    finally:
        for s in (client, upstream):
            if s is not None:
                try:
                    s.close()
                except OSError:
                    pass


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((RELAY_HOST, RELAY_PORT))
    srv.listen(128)
    log(f"Relay proxy lokal: http://{RELAY_HOST}:{RELAY_PORT} -> "
        f"{UPSTREAM_HOST}:{UPSTREAM_PORT} (auth ditempel: {'ya' if AUTH_HEADER else 'tidak'})")
    while True:
        client, _addr = srv.accept()
        threading.Thread(target=handle_client, args=(client,), daemon=True).start()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
