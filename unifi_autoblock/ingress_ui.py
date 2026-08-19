"""Read-only Home Assistant Ingress UI for UniFi Autoblock."""

from __future__ import annotations

import html
import json
import logging
import os
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import urlsplit


LOGGER = logging.getLogger("unifi_autoblock.ingress")


CSS = """
:root{color-scheme:light;--bg:#f3f6f9;--surface:#fff;--surface2:#edf3f7;--text:#17243a;--muted:#687b90;--line:#d8e2eb;--cyan:#058caf;--cyan-soft:#dff5fa;--good:#16845b;--amber:#e9a72f;--shadow:0 5px 22px #1e3a5f12}
html[data-theme=dark]{color-scheme:dark;--bg:#0d1420;--surface:#172235;--surface2:#202c41;--text:#e7edf5;--muted:#a4b2c6;--line:#30415d;--cyan:#52c9e6;--cyan-soft:#173b4a;--good:#50c895;--amber:#f0b84e;--shadow:none}
*{box-sizing:border-box}body{font:15px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:var(--bg);color:var(--text);margin:0}.app{max-width:1500px;margin:auto;padding:22px clamp(18px,2.8vw,48px) 40px}.header{display:flex;align-items:center;gap:20px;min-height:58px;margin-bottom:28px}.brand{display:flex;align-items:center;gap:11px;color:var(--cyan);font-size:24px;font-weight:800;letter-spacing:-.02em}.brand img{width:46px;height:46px;object-fit:contain;filter:drop-shadow(0 4px 8px #102a4330)}.brand b{font-size:12px;color:var(--muted);font-weight:650}.actions{display:flex;gap:8px;margin-left:auto}.toggle{color:var(--text);padding:9px 12px;border-radius:7px;background:var(--surface);border:1px solid var(--line);cursor:pointer;font:inherit}.pagehead{margin:4px 0 20px}.pagehead h1{font-size:29px;margin:0 0 5px;letter-spacing:-.025em}.pagehead p{margin:0;color:var(--muted)}.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:20px;box-shadow:var(--shadow)}.tablewrap{overflow:auto;border:1px solid var(--line);border-radius:10px}table{width:100%;border-collapse:collapse;white-space:nowrap}th,td{text-align:left;padding:11px 12px;border-bottom:1px solid var(--line)}th{font-size:12px;color:var(--muted);background:var(--surface2)}tr:last-child td{border:0}td.signature{white-space:normal;min-width:220px}.pill{display:inline-block;padding:3px 8px;border-radius:999px;background:var(--cyan-soft);color:var(--cyan);font-size:12px}.pill.expired{color:var(--amber)}.empty,.error{text-align:center;padding:45px 18px;color:var(--muted)}.error{color:#c43f55}@media(max-width:700px){.app{padding:16px}.header{align-items:flex-start}.brand span{display:grid}.card{padding:10px}.pagehead h1{font-size:25px}}
"""


JS = """
const base=document.querySelector('.app').dataset.base;
const storedLanguage=localStorage.getItem('uab-language'),browserLanguage=(navigator.language||'fr').slice(0,2);let language=['fr','en'].includes(storedLanguage)?storedLanguage:(browserLanguage==='en'?'en':'fr');
const text={fr:{title:'Historique',intro:"Dernières actions réalisées par UniFi Autoblock.",date:'Date',action:'Action',ip:'Adresse IP',signature:'Signature',severity:'Sévérité',region:'Région',destination:'Destination',protocol:'Protocole',empty:'Aucune action enregistrée.',error:"Impossible de charger l’historique.",blocked:'IP bannie',already_present:'IP déjà bannie',expired:'IP expirée'},en:{title:'History',intro:'Latest actions performed by UniFi Autoblock.',date:'Date',action:'Action',ip:'IP address',signature:'Signature',severity:'Severity',region:'Region',destination:'Destination',protocol:'Protocol',empty:'No recorded actions.',error:'Unable to load history.',blocked:'IP blocked',already_present:'IP already blocked',expired:'IP expired'}};
const esc=value=>String(value??'—').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
function labels(){const t=text[language];document.documentElement.lang=language;document.querySelector('h1').textContent=t.title;document.querySelector('.pagehead p').textContent=t.intro;document.querySelectorAll('th').forEach(th=>th.textContent=t[th.dataset.label]);document.querySelector('#language').textContent=language==='fr'?'EN':'FR'}
function date(value){try{return new Intl.DateTimeFormat(language,{dateStyle:'medium',timeStyle:'medium'}).format(new Date(value))}catch{return value||'—'}}
function render(entries){const t=text[language],body=document.querySelector('tbody'),empty=document.querySelector('.empty');empty.hidden=entries.length>0;empty.textContent=t.empty;body.innerHTML=entries.map(e=>`<tr><td>${esc(date(e.timestamp))}</td><td><span class="pill ${esc(e.action)}">${esc(t[e.action]||e.action)}</span></td><td>${esc(e.ip)}</td><td class="signature">${esc(e.signature)}</td><td>${esc(e.severity)}</td><td>${esc(e.region)}</td><td>${esc(e.destination)}${e.destination_port!=null?`:${esc(e.destination_port)}`:''}</td><td>${esc(e.protocol)}</td></tr>`).join('')}
let entries=[];async function load(){try{const response=await fetch(`${base}/api/history`,{cache:'no-store'});if(!response.ok)throw new Error();entries=(await response.json()).history||[];render(entries)}catch{const empty=document.querySelector('.empty');empty.hidden=false;empty.classList.add('error');empty.textContent=text[language].error}}
const languageButton=document.querySelector('#language');languageButton.onclick=()=>{language=language==='fr'?'en':'fr';localStorage.setItem('uab-language',language);labels();render(entries)};
const themeButton=document.querySelector('#theme'),setTheme=value=>{document.documentElement.dataset.theme=value;localStorage.setItem('uab-theme',value);themeButton.textContent=value==='dark'?'☀':'☾';themeButton.title=value==='dark'?'Light theme':'Dark theme'};setTheme(localStorage.getItem('uab-theme')||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'));themeButton.onclick=()=>setTheme(document.documentElement.dataset.theme==='dark'?'light':'dark');labels();load();
"""


class IngressHandler(BaseHTTPRequestHandler):
    server_version = "UniFiAutoblockIngress/1"

    def log_message(self, fmt: str, *args: Any) -> None:
        LOGGER.debug("HTTP %s - %s", self.address_string(), fmt % args)

    def send_body(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; frame-ancestors 'self'",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path.rstrip("/") or "/"
        if path == "/":
            prefix = self.headers.get("X-Ingress-Path", "").rstrip("/")
            safe_prefix = html.escape(prefix, quote=True)
            version = html.escape(os.environ.get("BUILD_VERSION", "dev"), quote=True)
            document = f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>UniFi Autoblock</title><link rel="stylesheet" href="{safe_prefix}/assets/app.css"></head><body><main class="app" data-base="{safe_prefix}"><header class="header"><div class="brand"><img src="{safe_prefix}/assets/icon.png" alt=""><span>UniFi Autoblock <b>v{version}</b></span></div><div class="actions"><button id="language" class="toggle" type="button">EN</button><button id="theme" class="toggle" type="button">☾</button></div></header><section class="pagehead"><h1>Historique</h1><p>Dernières actions réalisées par UniFi Autoblock.</p></section><section class="card"><div class="tablewrap"><table><thead><tr><th data-label="date">Date</th><th data-label="action">Action</th><th data-label="ip">Adresse IP</th><th data-label="signature">Signature</th><th data-label="severity">Sévérité</th><th data-label="region">Région</th><th data-label="destination">Destination</th><th data-label="protocol">Protocole</th></tr></thead><tbody></tbody></table></div><p class="empty">Chargement…</p></section></main><script src="{safe_prefix}/assets/app.js"></script></body></html>'''
            self.send_body(200, document.encode(), "text/html; charset=utf-8")
        elif path == "/api/history":
            body = json.dumps({"history": list(reversed(self.server.history_loader()))}).encode()
            self.send_body(200, body, "application/json")
        elif path == "/assets/app.css":
            self.send_body(200, CSS.encode(), "text/css; charset=utf-8")
        elif path == "/assets/app.js":
            self.send_body(200, JS.encode(), "text/javascript; charset=utf-8")
        elif path == "/assets/icon.png":
            with open(os.path.join(os.path.dirname(__file__), "icon.png"), "rb") as handle:
                self.send_body(200, handle.read(), "image/png")
        else:
            self.send_body(404, b'{"error":"not_found"}', "application/json")
