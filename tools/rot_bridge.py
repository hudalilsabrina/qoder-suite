"""Rotating HTTP->SOCKS5 bridge for residential proxies with sticky sessions.

Chromium can't speak "sticky session id" natively, so this exposes a plain
HTTP proxy on localhost and rewrites the SOCKS5 username per session. Each
distinct SID maps to a different residential exit IP.

    GET /__new_session   -> rotate SID, returns the new one
    GET /__whoami        -> show current SID

Config (all env vars, no secrets in the file):

    BRIDGE_SOCKS_HOST     default aliyun.dennak.com
    BRIDGE_SOCKS_PORT     default 443
    BRIDGE_SOCKS_PASS     required — provider password
    BRIDGE_USER_TEMPLATE  default "res-us-sid-{sid}"
    BRIDGE_SID_DIGITS     default 9
    BRIDGE_LISTEN_HOST    default 127.0.0.1
    BRIDGE_LISTEN_PORT    default 10801
    BRIDGE_AUTO_ROTATE_EVERY  rotate after N proxied connections (0 = off)

    pip install pysocks
    BRIDGE_SOCKS_PASS=xxx python3 rot_bridge.py
"""

from __future__ import annotations

import asyncio
import os
import random
import sys

try:
    import socks
except ImportError:
    sys.exit("pysocks belum terpasang — jalankan: pip install pysocks")

HOST = os.getenv("BRIDGE_SOCKS_HOST", "aliyun.dennak.com")
PORT = int(os.getenv("BRIDGE_SOCKS_PORT", "443"))
PASS = os.getenv("BRIDGE_SOCKS_PASS", "")
USER_TPL = os.getenv("BRIDGE_USER_TEMPLATE", "res-us-sid-{sid}")
SID_DIGITS = int(os.getenv("BRIDGE_SID_DIGITS", "9"))
LISTEN_HOST = os.getenv("BRIDGE_LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.getenv("BRIDGE_LISTEN_PORT", "10801"))
AUTO_ROTATE_EVERY = int(os.getenv("BRIDGE_AUTO_ROTATE_EVERY", "0"))

if not PASS:
    sys.exit("BRIDGE_SOCKS_PASS kosong — isi password proxy lewat env / EnvironmentFile")

LO, HI = 10 ** (SID_DIGITS - 1), 10**SID_DIGITS - 1
CURRENT_SID = str(random.randint(LO, HI))
CONN_COUNT = 0


def rotate_sid() -> str:
    global CURRENT_SID
    CURRENT_SID = str(random.randint(LO, HI))
    return CURRENT_SID


def current_user() -> str:
    return USER_TPL.format(sid=CURRENT_SID)


def create_socks5_connection(target_host: str, target_port: int):
    s = socks.socksocket()
    s.set_proxy(socks.SOCKS5, HOST, PORT, username=current_user(), password=PASS)
    s.settimeout(20)
    s.connect((target_host, target_port))
    s.setblocking(False)
    return s


async def pipe(reader, writer):
    try:
        while not reader.at_eof():
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


def _short_reply(writer, text: str):
    body = text.encode()
    return (
        b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
        + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
        + body
    )


async def handle_client(client_reader, client_writer):
    global CONN_COUNT
    try:
        req_line = await client_reader.readline()
        if not req_line:
            client_writer.close()
            return

        headers = []
        while True:
            line = await client_reader.readline()
            if not line or line == b"\r\n":
                break
            headers.append(line)

        parts = req_line.decode("latin1").strip().split(" ")
        if len(parts) < 2:
            client_writer.close()
            return
        method, target = parts[0], parts[1]

        # --- control endpoints (hit these directly, not through the tunnel) ---
        if "__new_session" in target:
            sid = rotate_sid()
            client_writer.write(_short_reply(client_writer, f"New SID: {sid}\n"))
            await client_writer.drain()
            client_writer.close()
            return

        if "__whoami" in target:
            client_writer.write(_short_reply(client_writer, f"{current_user()}\n"))
            await client_writer.drain()
            client_writer.close()
            return

        if ":" in target:
            target_host, port_s = target.rsplit(":", 1)
            try:
                target_port = int(port_s)
            except ValueError:
                target_port = 443
        else:
            target_host, target_port = target, 443

        sock = None
        loop = asyncio.get_running_loop()
        for _ in range(3):
            try:
                sock = await asyncio.wait_for(
                    loop.run_in_executor(None, create_socks5_connection, target_host, target_port),
                    timeout=25,
                )
                break
            except Exception:
                sock = None
                await asyncio.sleep(0.3)

        if sock is None:
            client_writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            await client_writer.drain()
            client_writer.close()
            return

        up_reader, up_writer = await asyncio.open_connection(sock=sock)

        if method.upper() == "CONNECT":
            client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await client_writer.drain()
        else:
            up_writer.write(req_line)
            for h in headers:
                up_writer.write(h)
            up_writer.write(b"\r\n")
            await up_writer.drain()

        CONN_COUNT += 1
        if AUTO_ROTATE_EVERY and CONN_COUNT % AUTO_ROTATE_EVERY == 0:
            rotate_sid()

        await asyncio.gather(
            pipe(client_reader, up_writer),
            pipe(up_reader, client_writer),
            return_exceptions=True,
        )
    except Exception:
        pass
    finally:
        try:
            client_writer.close()
        except Exception:
            pass


async def main():
    server = await asyncio.start_server(handle_client, LISTEN_HOST, LISTEN_PORT)
    print(
        f"[*] bridge http://{LISTEN_HOST}:{LISTEN_PORT} -> socks5://{HOST}:{PORT} "
        f"sid={CURRENT_SID} auto_rotate={AUTO_ROTATE_EVERY or 'off'}",
        flush=True,
    )
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
