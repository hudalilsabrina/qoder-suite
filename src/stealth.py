"""
Qoder Creator - Browser Stealth
Anti-detection untuk Playwright: fingerprint evasion, navigator spoofing.

Fingerprint di-random PER AKUN (bukan statis) agar tiap akun terlihat
seperti device berbeda: timezone, locale, memory, cores, canvas, WebGL,
platform, fonts, screen, dsb.
"""

import random
from typing import Optional, Dict

# ================= PROFIL RANDOM =================
# Kombinasi realistis device (jangan kombinasi mustahil, mis. Mac + cores 2)
PROFILES = [
    # (platform, ua_platform, cores, memory, timezone, locale, screen)
    ("Win32", "Windows NT 10.0; Win64; x64", [4, 8, 12, 16], [4, 8, 16],
     ["America/New_York", "America/Chicago", "America/Los_Angeles", "Europe/London",
      "Europe/Berlin", "Asia/Singapore", "Asia/Tokyo", "Australia/Sydney"],
     ["en-US", "en-GB"], [1920, 1366, 1536, 2560, 1440]),
    ("MacIntel", "Macintosh; Intel Mac OS X 10_15_7", [8, 10, 12], [8, 16],
     ["America/New_York", "America/Los_Angeles", "Europe/London", "Asia/Singapore"],
     ["en-US", "en-GB"], [1440, 1512, 1680, 1920, 2560]),
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]

FONT_SETS = [
    ["Arial", "Calibri", "Cambria", "Consolas", "Segoe UI", "Tahoma", "Times New Roman", "Verdana"],
    ["Arial", "Courier New", "Georgia", "Helvetica", "Times New Roman", "Trebuchet MS", "Verdana"],
]


def random_user_agent() -> str:
    return random.choice(USER_AGENTS)


def make_profile() -> Dict:
    """Bikin profil fingerprint acak (konsisten: platform <-> cores <-> tz)."""
    plat, ua_plat, cores_opts, mem_opts, tz_opts, loc_opts, scr_opts = random.choice(PROFILES)
    cores = random.choice(cores_opts)
    memory = random.choice(mem_opts)
    # pick UA sesuai platform
    if plat == "MacIntel":
        ua = random.choice([u for u in USER_AGENTS if "Macintosh" in u])
    else:
        ua = random.choice([u for u in USER_AGENTS if "Windows" in u])
    screen_w = random.choice(scr_opts)
    screen_h = random.choice([1080, 1200, 1440, 900]) if screen_w >= 1920 else random.choice([768, 800, 900, 1080])
    return {
        "platform": plat,
        "ua_platform": ua_plat,
        "cores": cores,
        "memory": memory,
        "timezone": random.choice(tz_opts),
        "locale": random.choice(loc_opts),
        "user_agent": ua,
        "screen": (screen_w, screen_h),
        "viewport": (random.randint(1280, min(screen_w, 1600)), random.randint(720, min(screen_h, 900))),
        "fonts": random.choice(FONT_SETS),
        "scale": random.choice([1, 2]),
        # canvas noise seed
        "canvas_seed": random.randint(1, 999999),
        "webgl_vendor": random.choice([
            ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
            ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
            ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
            ("Apple Inc.", "Apple M1"),
            ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ]),
    }


def build_stealth_js(p: Dict) -> str:
    """Bangun STEALTH_JS sesuai profil (nilai di-inject, bukan statis)."""
    fonts = ",".join(f"'{f}'" for f in p["fonts"])
    vendor, renderer = p["webgl_vendor"]
    return """(() => {
    const P = __PROFILE__;

    // ---- navigator core ----
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'platform', { get: () => P.platform });
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => P.cores });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => P.memory });
    Object.defineProperty(navigator, 'languages', { get: () => [P.locale, 'en'] });
    Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const arr = [
                {name:'Chrome PDF Plugin', filename:'internal-pdf-viewer', description:'Portable Document Format'},
                {name:'Chrome PDF Viewer', filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai', description:''},
                {name:'Native Client', filename:'internal-nacl-plugin', description:''}
            ];
            arr.__proto__ = PluginArray.prototype;
            return arr;
        }
    });
    Object.defineProperty(navigator, 'mimeTypes', {
        get: () => { const a = []; a.__proto__ = MimeTypeArray.prototype; return a; }
    });

    // ---- chrome runtime ----
    window.chrome = {
        runtime: {},
        loadTimes: function() {},
        csi: function() {},
        app: { isInstalled: false, InstallState: { DISABLED: 'disabled' }, RunningState: { RUNNING: 'running' } }
    };

    // ---- permissions ----
    const origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            origQuery(parameters)
    );

    // ---- WebGL vendor/renderer spoof ----
    try {
        const patchGL = (proto) => {
            if (!proto) return;
            const gp = proto.getParameter;
            proto.getParameter = function(p) {
                if (p === 37445) return P.glVendor;    // UNMASKED_VENDOR_WEBGL
                if (p === 37446) return P.glRenderer;  // UNMASKED_RENDERER_WEBGL
                return gp.apply(this, arguments);
            };
        };
        patchGL(window.WebGLRenderingContext && WebGLRenderingContext.prototype);
        patchGL(window.WebGL2RenderingContext && WebGL2RenderingContext.prototype);
    } catch(e) {}

    // ---- Canvas noise (fingerprint unik per akun) ----
    try {
        const seed = P.canvasSeed;
        const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function() {
            const ctx = this.getContext('2d');
            if (ctx) {
                const w = this.width, h = this.height;
                if (w && h) {
                    const img = ctx.getImageData(0, 0, Math.min(w,50), Math.min(h,50));
                    for (let i = 0; i < img.data.length; i += 97) {
                        img.data[i] = (img.data[i] + (seed % 7)) % 256;
                    }
                    ctx.putImageData(img, 0, 0);
                }
            }
            return origToDataURL.apply(this, arguments);
        };
        const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
        CanvasRenderingContext2D.prototype.getImageData = function() {
            const d = origGetImageData.apply(this, arguments);
            for (let i = 0; i < d.data.length; i += 103) {
                d.data[i] = (d.data[i] + (seed % 5)) % 256;
            }
            return d;
        };
    } catch(e) {}

    // ---- AudioContext noise ----
    try {
        const origGain = AudioBuffer.prototype.getChannelData;
        AudioBuffer.prototype.getChannelData = function() {
            const d = origGain.apply(this, arguments);
            for (let i = 0; i < d.length; i += 250) d[i] += (P.canvasSeed % 3) * 1e-7;
            return d;
        };
    } catch(e) {}

    // ---- Fonts spoof ----
    try {
        const origCheck = document.fonts.check.bind(document.fonts);
        document.fonts.check = function(font, text) {
            const f = (font || '').toLowerCase();
            for (const known of P.fonts) {
                if (f.includes(known.toLowerCase())) return true;
            }
            return origCheck(font, text);
        };
    } catch(e) {}

    // ---- timezone offset (samakan dgn timezone_id) ----
    try {
        const off = P.tzOffset;
        Date.prototype.getTimezoneOffset = function() { return off; };
    } catch(e) {}

    // ---- hapus jejak automation ----
    delete window.__playwright;
    delete window.__pw_manual;
    delete window.__PW_inspect;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
})();""".replace("__PROFILE__", _js_profile(p, vendor, renderer, fonts))


def _js_profile(p: Dict, vendor: str, renderer: str, fonts: str) -> str:
    # offset menit: UTC-4 (NY) -> 240, dst. Cukup representatif
    tz_off = {
        "America/New_York": 240, "America/Chicago": 300, "America/Los_Angeles": 420,
        "Europe/London": 0, "Europe/Berlin": -60, "Asia/Singapore": -480,
        "Asia/Tokyo": -540, "Australia/Sydney": -600,
    }.get(p["timezone"], 0)
    import json as _json
    return _json.dumps({
        "platform": p["platform"], "cores": p["cores"], "memory": p["memory"],
        "locale": p["locale"], "glVendor": vendor, "glRenderer": renderer,
        "canvasSeed": p["canvas_seed"], "fonts": p["fonts"], "tzOffset": tz_off,
    })


# Default (backward compat)
STEALTH_JS = build_stealth_js(make_profile())

# Redirect interception JS (capture qoder:// URLs)
QODER_REDIRECT_JS = """(() => {
    (function() {
        const _origAssign = window.location.assign.bind(window.location);
        const _origReplace = window.location.replace.bind(window.location);
        window.location.assign = function(url) {
            if (typeof url === 'string' && url.startsWith('qoder://')) {
                window.__qoder_redirect_url = url;
                return;
            }
            return _origAssign(url);
        };
        window.location.replace = function(url) {
            if (typeof url === 'string' && url.startsWith('qoder://')) {
                window.__qoder_redirect_url = url;
                return;
            }
            return _origReplace(url);
        };
        const _origOpen = window.open;
        window.open = function(url) {
            if (typeof url === 'string' && url.startsWith('qoder://')) {
                window.__qoder_redirect_url = url;
                return null;
            }
            return _origOpen.apply(this, arguments);
        };
    })();
})()"""


# ================= BROWSER ARGS =================
CHROMIUM_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-popup-blocking",
]


# ================= CONTEXT HELPERS =================
async def create_stealth_context(browser, proxy: Dict[str, str] = None):
    """Create a browser context with PER-ACCOUNT random fingerprint."""
    p = make_profile()
    context_kwargs = {
        "viewport": {"width": p["viewport"][0], "height": p["viewport"][1]},
        "screen": {"width": p["screen"][0], "height": p["screen"][1]},
        "user_agent": p["user_agent"],
        "locale": p["locale"],
        "timezone_id": p["timezone"],
        "device_scale_factor": p["scale"],
        "has_touch": False,
        "is_mobile": False,
        "color_scheme": random.choice(["light", "dark"]),
        "extra_http_headers": {
            "Accept-Language": f"{p['locale']},en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        },
    }

    if proxy:
        context_kwargs["proxy"] = proxy

    context = await browser.new_context(**context_kwargs)

    # Inject PER-ACCOUNT stealth script
    await context.add_init_script(build_stealth_js(p))
    await context.add_init_script(QODER_REDIRECT_JS)

    return context


async def launch_stealth_browser(playwright, proxy: Dict[str, str] = None, headless: bool = True):
    """Launch a Chromium browser with stealth args + optional proxy."""
    launch_options = {
        "headless": headless,
        "args": CHROMIUM_ARGS.copy(),
    }

    if proxy and proxy.get("server"):
        launch_options["proxy"] = proxy

    browser = await playwright.chromium.launch(**launch_options)
    return browser
