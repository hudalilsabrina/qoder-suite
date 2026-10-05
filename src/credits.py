"""
Qoder Suite - Daily Credits Claim (100 Credits/hari)

Mekanisme (hasil reverse-engineering CLI resmi Qoder v1.1.65):
1. Campaign dicek via GET /sash/api/v1/me/campaigns (butuh session cookie web).
2. Jika showCampaign=true & claimable=true, kampanye dijalankan sebagai command
   dinamis di Qoder CLI (worker JS sandbox) — bukan endpoint HTTP statis.
3. Jalur paling andal: jalankan Qoder CLI dengan PAT lalu ketik /claim.

Modul ini menyediakan:
- check_campaign(session_cookie): cek ketersediaan campaign satu akun.
- claim_via_cli(pat): jalankan CLI /claim via PTY (butuh binary qodercli).
"""

import asyncio
import json
import os
import shutil
import subprocess
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List

from .utils import write_log, log_event

CAMPAIGNS_URL = "https://qoder.com/sash/api/v1/me/campaigns"


def check_campaign(cookie_header: str) -> Dict[str, Any]:
    """Cek campaign via session cookie. Return {showCampaign, claimable, campaigns, campaignUrl}."""
    try:
        req = urllib.request.Request(
            CAMPAIGNS_URL,
            headers={"Cookie": cookie_header, "User-Agent": "Mozilla/5.0",
                     "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
        return {
            "ok": True,
            "showCampaign": data.get("showCampaign"),
            "claimable": data.get("claimable"),
            "campaignUrl": data.get("campaignUrl"),
            "campaigns": data.get("campaigns") or [],
            "uid": data.get("uid"),
        }
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.read().decode()[:150]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}


def find_cli() -> Optional[str]:
    """Cari binary qodercli."""
    for p in ("/tmp/qodercli", os.path.expanduser("~/.qoder/bin/qodercli"),
              shutil.which("qodercli")):
        if p and os.path.exists(p) and os.access(p, os.X_OK):
            return p
    return None


def claim_via_cli(pat: str, cli_path: str = None, timeout: int = 120) -> Dict[str, Any]:
    """Jalankan Qoder CLI non-interaktif untuk cek/klaim campaign.

    Catatan: /claim di CLI hanya menampilkan campaign yang tersedia. Bila ada,
    CLI akan mengeksekusi command dinamisnya. Fungsi ini mengembalikan output teks.
    """
    cli = cli_path or find_cli()
    if not cli:
        return {"ok": False, "error": "qodercli tidak ditemukan"}

    env = {**os.environ, "QODER_PERSONAL_ACCESS_TOKEN": pat}
    try:
        # -p (print mode) dengan prompt /claim
        proc = subprocess.run(
            [cli, "-p", "/claim"],
            env=env, capture_output=True, text=True, timeout=timeout,
            cwd="/tmp",
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        available = "no campaign available" not in out.lower()
        log_event("claim_cli_run", pat_prefix=pat[:12], available=available)
        return {"ok": True, "available": available, "output": out.strip()[:800]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "CLI timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}


async def check_campaign_for_account(email: str, password: str,
                                     console=None) -> Dict[str, Any]:
    """Login browser + cek campaign untuk satu akun. Return dict hasil."""
    from rich.console import Console
    from playwright.async_api import async_playwright
    from .stealth import launch_stealth_browser, create_stealth_context
    from .captcha import solve_slider_local

    c = console or Console()
    async with async_playwright() as p:
        browser = await launch_stealth_browser(p, headless=True)
        ctx = await create_stealth_context(browser)
        page = await ctx.new_page()
        try:
            await page.goto("https://qoder.com/users/sign-in", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)
            await page.fill("#basic_email", email)
            await page.wait_for_timeout(400)
            b = await page.query_selector("button:has-text('Continue')")
            if b: await b.click()
            await page.wait_for_timeout(3500)
            await page.wait_for_selector("#password_password", state="visible", timeout=10000)
            await page.fill("#password_password", password)
            await page.wait_for_timeout(300)
            sb = await page.query_selector("button:has-text('Sign in')")
            if sb: await sb.click()
            await page.wait_for_timeout(3500)

            ve = await page.query_selector("#aliyunCaptcha-captcha-body")
            if not ve:
                ve = await page.query_selector("button:has-text('Click to verify')")
            if ve and await ve.is_visible():
                await ve.click()
                await page.wait_for_timeout(2500)
                await solve_slider_local(page, max_attempts=5, console=c)
                await page.wait_for_timeout(3500)

            data = await page.evaluate("""async () => {
                try {
                    const r = await fetch('/sash/api/v1/me/campaigns', {credentials:'include'});
                    return await r.json();
                } catch(e) { return {error: String(e)}; }
            }""")
            return {"email": email, "ok": True,
                    "showCampaign": data.get("showCampaign"),
                    "claimable": data.get("claimable"),
                    "campaignUrl": data.get("campaignUrl"),
                    "campaigns": data.get("campaigns")}
        except Exception as e:
            return {"email": email, "ok": False, "error": str(e)[:150]}
        finally:
            try:
                await ctx.close(); await browser.close()
            except Exception:
                pass
