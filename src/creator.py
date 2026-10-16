import asyncio
import time
import random
from typing import Optional, Dict, Any
from playwright.async_api import Page, async_playwright
from rich.console import Console

from .config import QODER_BASE, ACCOUNTS_JSONL, OUTPUT_TXT, CAPTCHA_ATTEMPTS, REFERRAL_CODE
from .utils import write_log, generate_password, save_jsonl, append_account_txt, generate_machine_id, log_event
from .tempmail import TempikClient
from .proxy import ProxyPool
from .stealth import create_stealth_context, launch_stealth_browser
from .captcha import solve_slider_local
from .pat import PATManager
from .claim import CosyEngine
from .device import trigger_client_device_onboarding


def _referral_hook_js(code: str) -> str:
    """JS: paksa invitation_code + attribution di request POST /api/v1/users.

    Form web Qoder kadang tidak mengirim invitation_code walau URL punya
    ?referral_code= -> trial + 300 credits tidak diberikan. Hook ini
    menyuntikkan field tersebut ke body/query request registrasi.
    """
    return """(() => {
    const RC = %r;
    // 1) Simpan referral code agar bisa dibaca app
    try {
        const q = new URLSearchParams(location.search);
        if (!q.get('referral_code')) q.set('referral_code', RC);
        if (!q.get('invitation_code')) q.set('invitation_code', RC);
        // set localStorage attribution (dipakai beberapa jalur)
        try { localStorage.setItem('qoder_referral_code', RC); } catch(e){}
    } catch(e) {}

    // 2) Patch fetch: paksa invitation_code + attribution di /api/v1/users
    const _fetch = window.fetch;
    window.fetch = function(input, init) {
        try {
            const url = (typeof input === 'string') ? input : (input && input.url) || '';
            const method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
            if (url.indexOf('/api/v1/users') !== -1 && method === 'POST') {
                let body = (init && init.body) || '';
                // body bisa URLSearchParams / string / JSON
                let params = new URLSearchParams(typeof body === 'string' ? body : '');
                if (!params.get('invitation_code')) params.set('invitation_code', RC);
                if (!params.get('attribution')) params.set('attribution', JSON.stringify({invited_by_code: RC, url_referral_code: RC}));
                if (!params.get('channel_ref')) params.set('channel_ref', RC);
                init = init || {};
                init.body = params.toString();
                init.headers = Object.assign({}, init.headers, {'Content-Type': 'application/x-www-form-urlencoded'});
            }
        } catch(e) {}
        return _fetch.call(this, input, init);
    };

    // 3) Patch XHR juga (fallback)
    const _open = XMLHttpRequest.prototype.open;
    const _send = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function(m, u) { this.__m = m; this.__u = u; return _open.apply(this, arguments); };
    XMLHttpRequest.prototype.send = function(body) {
        try {
            if (this.__u && String(this.__u).indexOf('/api/v1/users') !== -1 && String(this.__m).toUpperCase() === 'POST') {
                let params = new URLSearchParams(typeof body === 'string' ? body : '');
                if (!params.get('invitation_code')) params.set('invitation_code', RC);
                if (!params.get('attribution')) params.set('attribution', JSON.stringify({invited_by_code: RC, url_referral_code: RC}));
                body = params.toString();
            }
        } catch(e) {}
        return _send.call(this, body);
    };
})()""" % code


class CreatorManager:
    """Manages full signup -> OTP -> PAT -> Claim flow."""

    def __init__(self, proxy_pool: Optional[ProxyPool] = None, headless: bool = True, console: Optional[Console] = None):
        self.proxy_pool = proxy_pool
        self.headless = headless
        self.console = console or Console()
        self.cosy = CosyEngine()

    async def create_account(self, idx: int = 1, auto_claim_bonus: bool = True, browser=None) -> Optional[Dict[str, Any]]:
        proxy = self.proxy_pool.next() if self.proxy_pool else None
        c = self.console

        c.print(f"\n[bold cyan]=== [Account #{idx}] Creating Qoder Account ===[/]")
        c.print("  [dim]Step 1: Mengambil disposable email dari Tempik...[/]")
        tempmail = TempikClient()
        try:
            # websurf.web.id has clean IP deliverability and delivers Qoder OTP within 2-3s
            email = tempmail.create_inbox(domain="websurf.web.id")
        except Exception as e:
            c.print(f"  [red]FAIL[/] Gagal mengambil temp mail: {e}")
            write_log(f"[{idx}] Tempmail error: {e}", "ERROR")
            return None

        password = generate_password()
        c.print(f"  [green]OK[/] Email   : [bold cyan]{email}[/]")
        c.print(f"  [green]OK[/] Password: [bold yellow]{password}[/]")

        async def _run_with_browser(b):
            c.print("  [dim]Step 2: Menggunakan stealth browser context...[/]")
            context = await create_stealth_context(b, proxy)

            if REFERRAL_CODE:
                await context.add_init_script(_referral_hook_js(REFERRAL_CODE))

            page = await context.new_page()

            try:
                # 3. Open signup
                c.print("  [dim]Step 3: Membuka form registrasi...[/]")
                signup_url = f"{QODER_BASE}/users/sign-up"
                if REFERRAL_CODE:
                    signup_url += f"?referral_code={REFERRAL_CODE}"
                    c.print(f"  [cyan]i[/] Pakai referral code: {REFERRAL_CODE[:12]}... (invitation_code dipaksa ke API)")
                await page.goto(signup_url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(4000)

                # 4. Fill name + email
                await page.fill("#basic_firstName", "Dev")
                await page.fill("#basic_lastName", "User")
                await page.fill("#basic_email", email)

                for cbox in await page.query_selector_all("input[type=checkbox]"):
                    try:
                        await cbox.check(force=True)
                    except Exception:
                        pass

                # Submit Step 1
                await page.locator("button[type='submit']").click()
                await page.wait_for_timeout(2000)

                # 5. Fill password
                pw = await page.wait_for_selector("#basic_password", state="visible", timeout=15000)
                await pw.fill(password)
                await page.wait_for_timeout(300)

                # Submit Step 2
                await page.locator("button[type='submit']").click()
                await page.wait_for_timeout(3000)

                # 6. Solve captcha
                c.print("  [yellow]![/] Menunggu tombol verifikasi captcha...")
                try:
                    v_btn = page.locator("text=Click to verify").or_(page.locator("#captcha-element")).or_(page.locator("#aliyunCaptcha-captcha-body"))
                    await v_btn.first.wait_for(timeout=8000)
                    await v_btn.first.click()
                    await page.wait_for_timeout(2000)
                    solved = await solve_slider_local(page, max_attempts=CAPTCHA_ATTEMPTS, console=c)
                    if not solved:
                        c.print("  [red]FAIL[/] Gagal menyelesaikan captcha")
                        return None
                    await page.wait_for_timeout(3500)
                except Exception as e:
                    c.print(f"  [red]DEBUG[/] Captcha wait error: {e}")
                    c.print(f"  [red]DEBUG[/] URL: {page.url}")

                # 7. OTP
                c.print("  [dim]Step 4: Menunggu kode OTP dari inbox...[/]")
                messages = await tempmail.wait_for_messages(email, max_wait=45, interval=2)
                if not messages:
                    c.print("  [red]FAIL[/] Timeout menunggu OTP")
                    return None

                otp = tempmail.extract_otp(messages)
                if not otp:
                    c.print("  [red]FAIL[/] OTP tidak ditemukan di email")
                    return None
                c.print(f"  [green]OK[/] Kode OTP didapat: [bold green]{otp}[/]")

                # Fill OTP
                otp_input = await page.wait_for_selector("input.ant-input, input.ant-otp-input, input[type='text']", timeout=15000)
                await otp_input.click()
                await page.keyboard.type(otp, delay=70)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(6000)

                # 8. Create PAT
                c.print("  [dim]Step 5: Generate Personal Access Token (PAT)...[/]")
                pat_response = await PATManager.create(page, "suite")
                pat_token = PATManager.extract_token(pat_response)
                if not pat_token:
                    c.print("  [yellow]![/] PAT gagal dibuat via session cookie, melanjutkan tanpa PAT...")
                    pat_token = ""

                c.print(f"  [green]OK[/] PAT Berhasil: [bold green]{pat_token[:16]}...[/]" if pat_token else "  [dim]PAT: (kosong)[/]")

                # Step 5b: Micro-dwell
                await page.wait_for_timeout(1500)

                # Step 5c: Client Device Flow (/device/selectAccounts)
                device_data = None
                try:
                    device_data = await trigger_client_device_onboarding(page, console=c)
                except Exception as e:
                    c.print(f"  [yellow]![/] Device onboarding notice: {e}")

                return pat_token, device_data
            finally:
                await context.close()

        try:
            if browser is not None:
                exec_res = await _run_with_browser(browser)
            else:
                async with async_playwright() as p:
                    b = await launch_stealth_browser(p, proxy, self.headless)
                    try:
                        exec_res = await _run_with_browser(b)
                    finally:
                        await b.close()
        except Exception as e:
            c.print(f"  [red]FAIL[/] Akun #{idx} error: {e}")
            write_log(f"[{idx}] Exception: {e}", "ERROR")
            return None

        if not exec_res:
            return None

        pat_token, device_data = exec_res

        # Step 6: Claim bonus jika aktif & PAT ada
        claim_data = None
        if auto_claim_bonus and pat_token:
            c.print("  [dim]Step 6: Auto-Claim Bonus Kuota Event (Cosy Engine)...[/]")
            mid = generate_machine_id()
            claim_data = self.cosy.auto_claim(pat_token, machine_id=mid)
            if claim_data.get("success"):
                c.print("  [green]OK[/] Auto-Claim & kuota scan selesai")
            else:
                c.print(f"  [dim]Auto-claim notice: {claim_data.get('error')}[/]")

        record = {
            "email": email,
            "password": password,
            "pat_token": pat_token,
            "pat_valid": bool(pat_token),
            "device_data": device_data,
            "claim_data": claim_data,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        save_jsonl(ACCOUNTS_JSONL, record)
        append_account_txt(OUTPUT_TXT, email, password, pat_token)
        log_event("account_created", email=email, has_pat=bool(pat_token),
                  domain=email.split("@")[-1] if "@" in email else "",
                  claim_ok=bool((claim_data or {}).get("success")))
        c.print(f"  [bold green]SUCCESS:[/] Akun tersimpan di [cyan]{OUTPUT_TXT.name}[/] [dim](format email:pass:pat)[/]")
        return record
