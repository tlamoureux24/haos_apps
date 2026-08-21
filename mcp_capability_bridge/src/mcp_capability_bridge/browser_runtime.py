"""Disposable Chromium runtime used only by the Lot 3A confinement gate."""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import WebDriverException

from mcp_capability_bridge.web_adapter import NetworkPolicy

BROWSER_ROOT=Path("/tmp/mcp-capability-bridge-browser")
DIAGNOSTIC_LIMIT=8192
logger=logging.getLogger("mcp_capability_bridge.browser")
logging.getLogger("selenium").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


def sanitize_diagnostic(value:str)->str:
    text=value.replace("\x00","")
    text=re.sub(r"(?i)\b(?:https?|wss?)://[^\s\"'<>]+","[REDACTED_URL]",text)
    text=re.sub(r"(?i)\b(authorization|cookie|set-cookie)\s*[:=]\s*[^\r\n]+",r"\1=[REDACTED]",text)
    text=re.sub(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+","Bearer [REDACTED]",text)
    text=re.sub(r"--(host-resolver-rules|user-data-dir)=[^\s\]]+",r"--\1=[REDACTED]",text)
    text="".join(character if character in "\n\t" or ord(character)>=32 else "?" for character in text)
    if len(text)>DIAGNOSTIC_LIMIT:text=text[:DIAGNOSTIC_LIMIT//2]+"\n[TRUNCATED]\n"+text[-DIAGNOSTIC_LIMIT//2:]
    return text.strip()


class BrowserRuntime:
    def __init__(self,root:Path=BROWSER_ROOT):self.root=root;self._active:set[asyncio.Task]=set();self._closing=False
    def prepare(self):
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():raise RuntimeError("unsafe_browser_root")
        for child in self.root.iterdir():
            if child.is_dir() and not child.is_symlink() and child.name.startswith("profile-"):shutil.rmtree(child)
    async def probe(self,configuration):
        if self._closing:raise RuntimeError("browser_runtime_stopping")
        policy=NetworkPolicy(configuration);await policy.verify_resolution();policy.authorize(configuration["base_url"],"navigation_origins")
        task=asyncio.create_task(asyncio.to_thread(self._probe_sync,configuration,policy));self._active.add(task)
        try:return await asyncio.wait_for(task,timeout=30)
        except asyncio.TimeoutError as exc:raise RuntimeError("browser_probe_timeout") from exc
        finally:self._active.discard(task)
    def _probe_sync(self,configuration,policy):
        profile=Path(tempfile.mkdtemp(prefix="profile-",dir=self.root));driver=None;diagnostic_path=profile/"chromedriver.log";diagnostic=diagnostic_path.open("w+",encoding="utf-8",errors="replace");service=Service("/usr/bin/chromedriver",service_args=["--log-level=WARNING"],log_output=diagnostic)
        try:
            parsed=urlparse(configuration["base_url"]);rules=", ".join([*(f"MAP {parsed.hostname} {address}" for address in policy.addresses),"MAP * ~NOTFOUND"])
            options=Options()
            for argument in ("--headless=new","--no-sandbox","--disable-dev-shm-usage","--disable-gpu","--disable-crash-reporter","--disable-breakpad","--disable-background-networking","--disable-sync","--disable-extensions","--disable-popup-blocking","--no-first-run","--no-default-browser-check","--remote-debugging-pipe",f"--host-resolver-rules={rules}",f"--user-data-dir={profile}"):options.add_argument(argument)
            options.add_experimental_option("excludeSwitches",["disable-popup-blocking"])
            options.add_experimental_option("prefs",{"download_restrictions":3,"download.default_directory":"/dev/null","profile.managed_default_content_settings":{"javascript":2,"popups":2},"profile.default_content_setting_values":{"notifications":2,"geolocation":2,"media_stream":2,"automatic_downloads":2}})
            if not configuration["verify_tls"]:options.add_argument("--ignore-certificate-errors")
            driver=webdriver.Chrome(service=service,options=options);driver.set_page_load_timeout(20);driver.get(configuration["base_url"])
            policy.authorize(driver.current_url,"navigation_origins")
            if len(driver.window_handles)!=1:raise RuntimeError("browser_popup_denied")
            return {"status":"reachable","origin":policy.base_origin}
        except WebDriverException as exc:
            logger.info("MCB_BROWSER_DIAG session_failed error=%s",type(exc).__name__)
            logger.debug("MCB_BROWSER_DIAG webdriver text=%s",sanitize_diagnostic(str(exc)))
            raise RuntimeError("browser_session_failed") from exc
        finally:
            if driver is not None:
                try:driver.quit()
                except Exception:pass
            process=getattr(service,"process",None)
            if process is not None and process.poll() is None:
                try:process.kill();process.wait(timeout=2)
                except (OSError,ProcessLookupError):pass
            diagnostic.flush();diagnostic.seek(0);captured=sanitize_diagnostic(diagnostic.read());diagnostic.close()
            if captured:logger.debug("MCB_BROWSER_DIAG chromedriver text=%s",captured)
            shutil.rmtree(profile,ignore_errors=True)
    async def close(self):
        self._closing=True
        for task in tuple(self._active):task.cancel()
        if self._active:await asyncio.gather(*self._active,return_exceptions=True)
        self.prepare()
