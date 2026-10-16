"""
Qoder Suite - Client Device Flow Automation
Automates OAuth 2.0 Device Authorization Flow (/device/selectAccounts)
to activate client-conditioned Pro Trial credits (14-day 300 Credits)
as described in client-device-flow-automation.
"""

import asyncio
import base64
import glob
import hashlib
import json
import os
import secrets
import subprocess
import time
import urllib.parse
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, Tuple

CLIENT_ID = "e883ade2-e6e3-4d6d-adf7-f92ceff5fdcb"
OPENAPI_BASE = "https://openapi.qoder.sh"
QODER_BASE = "https://qoder.com"

def get_runtime_machine_info() -> Dict[str, Any]:
    """Retrieve machine token and hardware identity from runtime-info binary."""
    bins = glob.glob(os.path.expanduser("~/.qoder/.bin/runtime-info-*"))
    if bins and os.access(bins[0], os.X_OK):
        try:
            out = subprocess.check_output([bins[0], "4"], timeout=5).decode("utf-8")
            return json.loads(out)
        except Exception:
            pass

    # Check cached UMID
    umid_path = os.path.expanduser("~/.qoder/umid-cache.json")
    if os.path.exists(umid_path):
        try:
            with open(umid_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("info", {})
        except Exception:
            pass

    return {
        "machineToken": "P1gAMrrY5ljO3DrX0sGbZ_DHIzydY4jJ8euXc9cIU7suBwRrqHOYVsdo57I_qIVyeaAIGH65ZHVVTUGLg_YXebQa",
        "machineType": "203b237291b55afbb0",
        "machineCode": "012de14a0044ef6cb1",
        "vmInfo": {"isVm": False, "brand": "None", "percentage": 0, "vmTypeCode": 91}
    }

def generate_device_auth_params() -> Tuple[str, str, str, str, str]:
    """
    Generate PKCE pair and device authorization query.
    Returns: (auth_url, poll_url, nonce, verifier, machine_id)
    """
    raw_bytes = secrets.token_bytes(45)
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    verifier = "".join([chars[b % len(chars)] for b in raw_bytes])
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).decode('ascii').rstrip('=')
    nonce = secrets.token_hex(16)
    machine_id = str(secrets.token_hex(16))

    info = get_runtime_machine_info()
    machine_token = info.get("machineToken", "")

    query = urllib.parse.urlencode({
        "challenge": challenge,
        "challenge_method": "S256",
        "nonce": nonce,
        "machine_id": machine_id,
        "client_id": CLIENT_ID,
        "machine_token": machine_token
    })

    auth_url = f"{QODER_BASE}/device/selectAccounts?{query}"
    poll_url = f"{OPENAPI_BASE}/api/v1/deviceToken/poll?nonce={nonce}&verifier={verifier}&challenge_method=S256"

    return auth_url, poll_url, nonce, verifier, machine_id

async def authorize_device_session(page, auth_url: str) -> bool:
    """Navigate to device auth URL on an already-authenticated page and click confirm."""
    try:
        await page.goto(auth_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        for btn in await page.query_selector_all("button"):
            txt = (await btn.inner_text()).strip()
            if any(k in txt.lower() for k in ["continue", "confirm", "authorize", "sign in", "确认", "登录"]):
                await btn.click()
                await page.wait_for_timeout(3500)
                return True
    except Exception:
        pass
    return False

def poll_device_token(poll_url: str, max_wait: int = 25, interval: float = 2.0) -> Optional[Dict[str, Any]]:
    """Poll openapi until device token is issued."""
    req = urllib.request.Request(poll_url, headers={
        "Accept": "application/json",
        "User-Agent": "qodercli/1.1.73"
    })
    t0 = time.time()
    while time.time() - t0 < max_wait:
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read().decode())
                if data and "token" in data:
                    return data
        except urllib.error.HTTPError as e:
            if e.code != 404:
                break
        except Exception:
            pass
        time.sleep(interval)
    return None

async def trigger_client_device_onboarding(page, console=None) -> Dict[str, Any]:
    """
    Perform end-to-end device flow on active page:
    1. Generate PKCE & device parameters
    2. Confirm device in browser
    3. Poll for issued device token
    4. Return status
    """
    if console:
        console.print("  [dim]Triggering Client Device Flow (/device/selectAccounts)...[/]")

    auth_url, poll_url, nonce, verifier, machine_id = generate_device_auth_params()

    approved = await authorize_device_session(page, auth_url)
    if not approved:
        if console:
            console.print("  [yellow]![/] Device authorization page did not display confirm button")
        return {"success": False, "reason": "confirm_button_missing"}

    # Poll for token in background
    token_data = await asyncio.to_thread(poll_device_token, poll_url, 15, 1.5)
    if token_data and "token" in token_data:
        if console:
            console.print("  [bold green]OK[/] Device token issued successfully (Client-Authorized)")
        return {
            "success": True,
            "device_token": token_data.get("token"),
            "machine_id": machine_id,
            "token_data": token_data
        }

    return {"success": False, "reason": "poll_timeout"}
