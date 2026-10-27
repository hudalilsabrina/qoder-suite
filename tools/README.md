# Rotating proxy bridge

Chromium nggak bisa "sticky session" ke residential proxy. Bridge ini nerima
koneksi HTTP proxy biasa di localhost, lalu meneruskannya ke SOCKS5 provider
dengan username yang berisi SID — tiap SID = IP keluar beda.

## Kenapa perlu

Qoder nge-throttle **per IP**, bukan per domain. Satu IP hanya dapat beberapa
OTP sebelum berhenti dikirim (API tetap balas 200, jadi kelihatan sukses).
Tanpa rotasi IP, farming mentok di 2–3 akun per jam.

## Pasang

```bash
pip install pysocks

# password provider disimpan di env, JANGAN di file script
export BRIDGE_SOCKS_PASS='...'
export BRIDGE_SOCKS_HOST='aliyun.dennak.com'   # default
python3 tools/rot_bridge.py
```

Tes:

```bash
curl -s -x http://127.0.0.1:10801 https://api.ipify.org; echo
curl -s http://127.0.0.1:10801/__new_session      # rotasi
curl -s -x http://127.0.0.1:10801 https://api.ipify.org; echo   # IP harus beda
```

## Pakai di suite

```bash
QODER_PROXY=http://127.0.0.1:10801 ./run.sh create -n 10
```

Rotasi **wajib dipanggil di antara akun**, kalau nggak semua akun keluar dari
IP yang sama dan throttle balik lagi:

```python
import urllib.request
urllib.request.urlopen("http://127.0.0.1:10801/__new_session", timeout=5).read()
```

Kalau suite belum punya hook itu, pakai auto-rotate:

```bash
BRIDGE_AUTO_ROTATE_EVERY=40 python3 tools/rot_bridge.py   # tiap 40 koneksi
```

Satu alur signup biasanya ~25–40 koneksi, jadi angka itu kira-kira = 1 akun.

## systemd

```ini
[Unit]
Description=Rotating SOCKS5 proxy bridge
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/root/qoder-suite
EnvironmentFile=/root/qoder-suite/.bridge.env
ExecStart=/usr/bin/python3 tools/rot_bridge.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

`/root/qoder-suite/.bridge.env` (chmod 600, masuk `.gitignore`):

```
BRIDGE_SOCKS_PASS=...
BRIDGE_SOCKS_HOST=aliyun.dennak.com
BRIDGE_SOCKS_PORT=443
BRIDGE_LISTEN_PORT=10801
```

## Env vars

| Var | Default | Keterangan |
|---|---|---|
| `BRIDGE_SOCKS_HOST` | `aliyun.dennak.com` | host SOCKS5 provider |
| `BRIDGE_SOCKS_PORT` | `443` | port |
| `BRIDGE_SOCKS_PASS` | — | **wajib**, password provider |
| `BRIDGE_USER_TEMPLATE` | `res-us-sid-{sid}` | format username, `{sid}` diganti |
| `BRIDGE_SID_DIGITS` | `9` | panjang SID |
| `BRIDGE_LISTEN_HOST` | `127.0.0.1` | bind address |
| `BRIDGE_LISTEN_PORT` | `10801` | port |
| `BRIDGE_AUTO_ROTATE_EVERY` | `0` (off) | rotasi tiap N koneksi |

## Catatan

- Bind ke `127.0.0.1` saja. Kalau dibuka ke publik, siapa pun bisa pakai
  kuota proxy kamu.
- Endpoint `/__new_session` dan `/__whoami` dijawab langsung oleh bridge,
  nggak diteruskan ke internet.
