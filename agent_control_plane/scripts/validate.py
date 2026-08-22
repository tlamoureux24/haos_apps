#!/usr/bin/env python3
"""Validate Agent Control Plane repository invariants without third-party packages."""

from __future__ import annotations

import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parent


def yaml_leaf_keys(text: str, section: str) -> set[str]:
    lines = text.splitlines()
    keys: set[str] = set()
    in_section = False
    for line in lines:
        if line and not line.startswith(" "):
            in_section = line == f"{section}:"
            continue
        if in_section:
            match = re.match(r"^  ([^:#]+):\s*$", line)
            if match:
                keys.add(match.group(1))
    return keys


def main() -> int:
    config = (ROOT / "config.yaml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    launcher = (ROOT / "run.sh").read_text(encoding="utf-8")
    apparmor = (ROOT / "apparmor.txt").read_text(encoding="utf-8")
    application = (ROOT / "src/agent_control_plane/main.py").read_text(encoding="utf-8")
    admin_ui = (ROOT / "src/agent_control_plane/admin_ui.py").read_text(encoding="utf-8")
    package = (ROOT / "src/agent_control_plane/__init__.py").read_text(encoding="utf-8")
    fake_mcp = (ROOT / "scripts/fake_mcp_server.py").read_text(encoding="utf-8")
    root_readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")

    required_config = (
        'slug: "agent_control_plane"',
        'version: "0.46.13"',
        "  - aarch64",
        "  - amd64",
        "init: false",
        "stage: stable",
        "apparmor: true",
        "tmpfs: true",
        "backup: cold",
        "ingress: true",
        "ingress_port: 8099",
        "panel_admin: true",
        "homeassistant_api: true",
        "  8098/tcp: null",
    )
    for invariant in required_config:
        if invariant not in config:
            raise RuntimeError(f"Missing config invariant: {invariant}")
    if '__version__ = "0.46.13"' not in package:
        raise RuntimeError("Package and App metadata versions must remain synchronized")
    if "jsonschema[format-nongpl]==4.26.0" not in requirements:
        raise RuntimeError("MCP input schemas must retain the pinned reference validator")
    logging_config = ROOT / "src/agent_control_plane/uvicorn_logging.json"
    if not logging_config.is_file() or "%(asctime)s" not in logging_config.read_text(encoding="utf-8"):
        raise RuntimeError("Uvicorn logs must retain an explicit timestamp")
    if launcher.count("--log-config /app/src/agent_control_plane/uvicorn_logging.json") != 2:
        raise RuntimeError("Both Agent Control Plane listeners must use the timestamped logging configuration")
    if "FROM ghcr.io/home-assistant/base:latest" not in dockerfile:
        raise RuntimeError("Home Assistant base image must continue to follow latest")
    if "FROM ghcr.io/home-assistant/base:latest@" in dockerfile:
        raise RuntimeError("Base image traceability must not pin future App builds")
    if 'org.opencontainers.image.base.digest="${BASE_IMAGE_DIGEST}"' not in dockerfile:
        raise RuntimeError("Base image digest must be recorded in OCI metadata")
    if "ha_mcp" in config.lower():
        raise RuntimeError("No upstream MCP connector may be fixed in App configuration")
    if "document.querySelector(`#${name}`)" in admin_ui:
        raise RuntimeError("Admin navigation must reject an empty URL fragment before selecting a view")
    if 'name="ha_get_addon"' not in fake_mcp or '"read_only": True' not in fake_mcp:
        raise RuntimeError("The multi-connector acceptance server must expose its harmless duplicate tool")
    for document in (ROOT / "README.md", ROOT / "README.fr.md", ROOT / "DOCS.md"):
        if not document.is_file():
            raise RuntimeError(f"Missing Agent Control Plane documentation: {document.name}")
    if "agent_control_plane/README.fr.md" not in root_readme or "agent_control_plane/README.md" not in root_readme:
        raise RuntimeError("The repository README must link both Agent Control Plane languages")
    for invariant in ("navigator.language", "acp-language", "MutationObserver", "'Vue d’ensemble':'Overview'"):
        if invariant not in admin_ui:
            raise RuntimeError(f"Missing administration internationalization invariant: {invariant}")

    if "privileged:" in config or "host_network:" in config:
        raise RuntimeError("Agent Control Plane must not request privileged or host networking")
    if "hassio_role:" in config or "hassio_api:" in config:
        raise RuntimeError("Phase 0 must not request the Supervisor API")

    for language in ("fr", "en"):
        translation = ROOT / "translations" / f"{language}.yaml"
        if not translation.is_file():
            raise RuntimeError(f"Missing {language} translation")
    french = (ROOT / "translations/fr.yaml").read_text(encoding="utf-8")
    english = (ROOT / "translations/en.yaml").read_text(encoding="utf-8")
    for section in ("configuration", "network"):
        if yaml_leaf_keys(french, section) != yaml_leaf_keys(english, section):
            raise RuntimeError(f"Translation key mismatch in {section}")

    if "adduser -S -D -H" not in dockerfile:
        raise RuntimeError("Container must create an unprivileged runtime user")
    if "py3-cryptography" not in dockerfile:
        raise RuntimeError("Connector secrets require authenticated encryption support")
    if launcher.count("su-exec agent-control-plane:agent-control-plane") != 5:
        raise RuntimeError("Private bootstrap, schema initialization, and listeners must run unprivileged")
    if "python3 -m agent_control_plane.database initialize" not in launcher or launcher.count("python3 -m uvicorn") != 2:
        raise RuntimeError("Schema initialization and listeners must run as Python modules")
    if re.search(r"agent-control-plane:agent-control-plane uvicorn\b", launcher):
        raise RuntimeError("Launcher must not invoke Python console-script wrappers")
    if "alembic" in requirements.lower() or "sqlalchemy" in requirements.lower():
        raise RuntimeError("Development builds must not contain a migration framework")
    if "alembic.ini" in dockerfile or "COPY migrations" in dockerfile:
        raise RuntimeError("Container must package only the current direct schema")
    if not launcher.startswith("#!/usr/bin/with-contenv /bin/sh\n"):
        raise RuntimeError("Launcher must preserve the s6 environment with a POSIX shell")
    if "bashio" in launcher:
        raise RuntimeError("Launcher must not require the broad bashio runtime")
    if 'chown "${runtime_uid}:${runtime_gid}" /data' not in launcher:
        raise RuntimeError("Persistent data must belong to the runtime user")
    if "su-exec agent-control-plane:agent-control-plane install -d -m 0700 /data/private" not in launcher:
        raise RuntimeError("Private data must be initialized by the runtime user")
    if "su-exec agent-control-plane:agent-control-plane env PYTHONPATH=/app/src python3" not in launcher:
        raise RuntimeError("Credential pepper must be bootstrapped by the runtime user")
    if 'export AGENT_CONTROL_PLANE_CREDENTIAL_PEPPER_HEX="${pepper_hex}"' not in launcher:
        raise RuntimeError("Runtime processes must receive the bootstrapped pepper in memory")
    if "os.geteuid() != 1000" not in application:
        raise RuntimeError("Application must refuse to run under an unexpected UID")
    if "AGENT_CONTROL_PLANE_SURFACE=admin" not in launcher:
        raise RuntimeError("Missing isolated admin listener")
    if "AGENT_CONTROL_PLANE_SURFACE=public" not in launcher:
        raise RuntimeError("Missing isolated public listener")
    if "export PYTHONDONTWRITEBYTECODE=1" not in launcher:
        raise RuntimeError("Runtime must not attempt bytecode writes inside /app")
    if "capability sys_admin" in apparmor or "network raw" in apparmor:
        raise RuntimeError("AppArmor grants an excessive capability")
    if "complain" in apparmor:
        raise RuntimeError("The final AppArmor profile must enforce its rules")
    broad_execution_rules = (
        "/bin/** ix,",
        "/usr/bin/** ix,",
        "/usr/local/bin/** ix,",
        "/run/{s6,s6-rc*,service}/** ix,",
        "/package/** ix,",
        "/command/** ix,",
        "/etc/services.d/** rwix,",
        "/etc/cont-init.d/** rwix,",
        "/etc/cont-finish.d/** rwix,",
    )
    for broad_rule in broad_execution_rules:
        if broad_rule in apparmor:
            raise RuntimeError(f"AppArmor retains broad execution rule: {broad_rule}")
    if "/run/{,**} rwk," in apparmor:
        raise RuntimeError("AppArmor must restrict writable runtime data to s6 subtrees")
    exact_s6_runtime_trees = (
        "/run/ rw,",
        "/run/s6/{,**} rwk,",
        "/run/s6-rc rw,",
        "/run/s6-rc:s6-rc-init:*/{,**} rwk,",
        "/run/service/{,**} rwk,",
        "/run/s6-linux-init-container-results/{,**} rwk,",
    )
    for runtime_rule in exact_s6_runtime_trees:
        if runtime_rule not in apparmor:
            raise RuntimeError(f"Missing bounded s6 runtime rule: {runtime_rule}")
    if "/data/{,**} rwk," in apparmor or "/data/**" in apparmor:
        raise RuntimeError("AppArmor must restrict persistent data file by file")
    exact_runtime_files = (
        "/data/options.json r,",
        "/data/agent_control_plane.db rwlk,",
        "/data/agent_control_plane.db-{journal,shm,wal} rwlk,",
    )
    for runtime_rule in exact_runtime_files:
        if runtime_rule not in apparmor:
            raise RuntimeError(f"Missing exact runtime rule: {runtime_rule}")
    if "capability chown," not in apparmor:
        raise RuntimeError("AppArmor must allow ownership transfer of persistent data")
    if "capability fowner," in apparmor or "capability dac_override," in apparmor:
        raise RuntimeError("Clean private bootstrap must not require ownership bypass capabilities")
    if "/data/ rw," not in apparmor or "/data/private/ rw," not in apparmor:
        raise RuntimeError("AppArmor must allow the exact persistent data directories")
    if "/data/private/credential-pepper rwlk," not in apparmor:
        raise RuntimeError("AppArmor must allow the exact persistent credential pepper")
    if "/data/private/.credential-pepper.*.tmp rwlk," not in apparmor:
        raise RuntimeError("AppArmor must allow exact atomic pepper temporary files")
    if "/init rix," not in apparmor:
        raise RuntimeError("AppArmor must allow the shell to read and execute /init")
    if "/sbin/su-exec ix," not in apparmor:
        raise RuntimeError("AppArmor must allow the exact privilege-drop executable")
    if "/sbin/**" in apparmor:
        raise RuntimeError("AppArmor must not grant broad access to /sbin")
    audited_s6_executables = (
        "/package/admin/s6-2.15.0.0/command/s6-ipcclient ix,",
        "/package/admin/s6-2.15.0.0/command/s6-ipcserver-access ix,",
        "/package/admin/s6-2.15.0.0/command/s6-ipcserver-socketbinder ix,",
        "/package/admin/s6-2.15.0.0/command/s6-ipcserverd ix,",
        "/package/admin/s6-2.15.0.0/command/s6-sudo ix,",
        "/package/admin/s6-2.15.0.0/command/s6-sudoc ix,",
        "/package/admin/s6-2.15.0.0/command/s6-sudod ix,",
        "/package/admin/s6-2.15.0.0/command/s6-svc ix,",
        "/package/admin/s6-2.15.0.0/command/s6-svlisten ix,",
        "/package/admin/s6-2.15.0.0/command/s6-svscanctl ix,",
        "/package/admin/s6-linux-init-1.2.0.1/command/s6-linux-init-shutdown ix,",
    )
    for executable_rule in audited_s6_executables:
        if executable_rule not in apparmor:
            raise RuntimeError(f"Missing audited s6 executable rule: {executable_rule}")
    audited_generated_scripts = (
        "/run/s6/basedir/bin/halt rix,",
        "/run/s6-rc:s6-rc-init:*/servicedirs/s6rc-oneshot-runner/run rix,",
        "/run/service/s6-linux-init-shutdownd/run rix,",
        '"/run/service/s6-linux-init-shutdownd/stage 4" rix,',
        "/run/service/.s6-svscan/SIGTERM rix,",
        "/run/service/.s6-svscan/finish rix,",
        "/run/service/.s6-svscan/crash rix,",
    )
    for script_rule in audited_generated_scripts:
        if script_rule not in apparmor:
            raise RuntimeError(f"Missing audited generated s6 script rule: {script_rule}")
    if "/package/admin/s6-overlay-*/libexec/preinit rix," not in apparmor:
        raise RuntimeError("AppArmor must allow the shell to read the s6-overlay preinit script")
    if "/package/admin/s6-overlay-*/libexec/stage0 rix," not in apparmor:
        raise RuntimeError("AppArmor must allow the shell to read the s6-overlay stage0 script")
    if "/package/admin/s6-overlay-*/etc/s6-linux-init/skel/rc.init r," not in apparmor:
        raise RuntimeError("AppArmor must allow reading the s6-overlay rc.init template")
    if "/package/admin/s6-overlay-*/etc/s6-linux-init/skel/rc.shutdown r," not in apparmor:
        raise RuntimeError("AppArmor must allow reading the s6-overlay rc.shutdown template")
    packaged_s6_sources = (
        "/package/admin/s6-overlay-*/etc/s6-rc/sources/ r,",
        "/package/admin/s6-overlay-*/etc/s6-rc/sources/base/type r,",
        "/package/admin/s6-overlay-*/etc/s6-rc/sources/fix-attrs/up r,",
        "/package/admin/s6-overlay-*/etc/s6-rc/sources/legacy-cont-init/up r,",
        "/package/admin/s6-overlay-*/etc/s6-rc/sources/legacy-services/up r,",
        "/package/admin/s6-overlay-*/etc/s6-rc/sources/top/contents.d/user2 r,",
    )
    for source_rule in packaged_s6_sources:
        if source_rule not in apparmor:
            raise RuntimeError(f"Missing exact packaged s6 source rule: {source_rule}")
    packaged_s6_scripts = (
        "/package/admin/s6-overlay-*/etc/s6-rc/scripts/ r,",
        "/package/admin/s6-overlay-*/etc/s6-rc/scripts/cont-finish rix,",
        "/package/admin/s6-overlay-*/etc/s6-rc/scripts/cont-init rix,",
        "/package/admin/s6-overlay-*/etc/s6-rc/scripts/fix-attrs rix,",
        "/package/admin/s6-overlay-*/etc/s6-rc/scripts/services-down rix,",
        "/package/admin/s6-overlay-*/etc/s6-rc/scripts/services-up rix,",
    )
    for script_rule in packaged_s6_scripts:
        if script_rule not in apparmor:
            raise RuntimeError(f"Missing exact packaged s6 script rule: {script_rule}")
    if "/command/printcontenv rix," not in apparmor:
        raise RuntimeError("AppArmor must allow the shell to read printcontenv")
    if "/package/admin/s6-overlay-*/command/printcontenv rix," not in apparmor:
        raise RuntimeError("AppArmor must allow reading the canonical printcontenv target")
    if "/usr/bin/with-contenv rix," not in apparmor:
        raise RuntimeError("AppArmor must allow execlineb to read the with-contenv link")
    if "/package/admin/s6-overlay-*/command/with-contenv rix," not in apparmor:
        raise RuntimeError("AppArmor must allow reading the canonical with-contenv target")
    if "/etc/s6-overlay/s6-rc.d/ r," not in apparmor:
        raise RuntimeError("AppArmor must allow s6-rc-compile to enumerate its source directory")
    if "/etc/s6-overlay/s6-rc.d/user/ r," not in apparmor:
        raise RuntimeError("AppArmor must allow s6-rc-compile to enumerate the user bundle directory")
    if "/etc/s6-overlay/s6-rc.d/user/type r," not in apparmor:
        raise RuntimeError("AppArmor must allow reading the s6 user bundle type")
    if "/etc/s6-overlay/s6-rc.d/user/contents.d/ r," not in apparmor:
        raise RuntimeError("AppArmor must allow enumerating the s6 user bundle contents directory")
    if "/etc/s6-overlay/s6-rc.d/user2/ r," not in apparmor:
        raise RuntimeError("AppArmor must allow enumerating the s6 user2 bundle directory")
    if "/etc/s6-overlay/s6-rc.d/user2/type r," not in apparmor:
        raise RuntimeError("AppArmor must allow reading the s6 user2 bundle type")
    if "/etc/s6-overlay/s6-rc.d/user2/contents.d/ r," not in apparmor:
        raise RuntimeError("AppArmor must allow enumerating the s6 user2 bundle contents directory")
    if "/package/** rix," in apparmor or "/package/admin/s6-overlay-*/libexec/** rix," in apparmor or "/package/admin/s6-overlay-*/etc/s6-rc/sources/** r," in apparmor or "/package/admin/s6-overlay-*/etc/s6-rc/scripts/** rix," in apparmor:
        raise RuntimeError("AppArmor must grant read access to s6-overlay scripts file by file")
    if "/command/** rix," in apparmor or "/etc/s6-overlay/** r" in apparmor or "/etc/s6-overlay/s6-rc.d/user/** r" in apparmor:
        raise RuntimeError("AppArmor must not grant broad read access to command or s6-overlay trees")

    ignored_documents = (
        "/agent_control_plane/PROJECT_BRIEF.md",
        "/agent_control_plane/docs/adr/0001-control-plane-foundation.md",
    )
    ignore = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")
    for document in ignored_documents:
        if document not in ignore:
            raise RuntimeError(f"Local design document is not ignored: {document}")

    print("Validated Agent Control Plane repository invariants")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as err:
        print(f"Validation failed: {err}", file=sys.stderr)
        raise SystemExit(1) from err
