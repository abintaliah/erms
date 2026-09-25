#!/usr/bin/env python3
"""Verify required PostgreSQL 18 text-search objects in an isolated disposable cluster."""

from __future__ import annotations

import json
import shutil
import socket as socket_module
import subprocess
import tempfile
import uuid
from pathlib import Path


PG_BIN = Path("/opt/homebrew/opt/postgresql@18/bin")
OUTPUT = Path(__file__).resolve().parent / "phase0-postgresql18-results.json"


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True, **kwargs)


def main() -> None:
    database = f"erms_fts_phase0_{uuid.uuid4().hex[:12]}"
    root = Path(tempfile.mkdtemp(prefix="erms-fts-pg18-"))
    cluster = root / "cluster"
    socket = root / "socket"
    socket.mkdir(mode=0o700)
    with socket_module.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = str(probe.getsockname()[1])
    cleanup = {"database_dropped": False, "server_stopped": False, "temporary_directory_removed": False}
    result: dict = {"database": database, "postgres_bin": str(PG_BIN), "cleanup": cleanup}
    started = False
    created = False
    error: Exception | None = None
    try:
        run([str(PG_BIN / "initdb"), "-D", str(cluster), "--no-locale", "--encoding=UTF8", "--auth=trust"])
        run([
            str(PG_BIN / "pg_ctl"), "-D", str(cluster), "-l", str(root / "postgres.log"),
            "-o", f"-k {socket} -p {port}", "-w", "start",
        ])
        started = True
        common = ["-h", str(socket), "-p", port]
        run([str(PG_BIN / "createdb"), *common, database])
        created = True
        sql = r"""
SELECT current_setting('server_version');
SELECT 'pg_catalog.simple'::regconfig::text,
       'pg_catalog.english'::regconfig::text,
       'pg_catalog.arabic'::regconfig::text;
SELECT cfg.cfgname, dict.dictname
FROM pg_ts_config cfg
JOIN pg_namespace n ON n.oid = cfg.cfgnamespace
JOIN pg_ts_config_map map ON map.mapcfg = cfg.oid
JOIN pg_ts_dict dict ON dict.oid = map.mapdict
WHERE n.nspname = 'pg_catalog' AND cfg.cfgname = 'arabic'
ORDER BY map.maptokentype, map.mapseqno
LIMIT 5;
SELECT to_tsvector('pg_catalog.arabic', 'الميزانية المعتمدة والمصروفات') @@
       websearch_to_tsquery('pg_catalog.arabic', 'الميزانية');
SELECT to_tsvector('pg_catalog.arabic', 'الميزانية المعتمدة والمصروفات')::text;
SELECT to_tsvector('pg_catalog.english', 'approved budgets and expenditures') @@
       websearch_to_tsquery('pg_catalog.english', 'approved budget');
"""
        query = run([str(PG_BIN / "psql"), *common, "-d", database, "-v", "ON_ERROR_STOP=1", "-At", "-c", sql])
        lines = query.stdout.splitlines()
        result.update({
            "server_version": lines[0],
            "required_configurations": lines[1].split("|"),
            "arabic_dictionary_rows": [line for line in lines[2:] if "arabic" in line and "|" in line],
            "arabic_match": "t" in lines,
            "english_match": lines[-1] == "t",
            "raw_output": lines,
        })
    except Exception as exc:
        error = exc
        result["error"] = repr(exc)
        if isinstance(exc, subprocess.CalledProcessError):
            result["error_stderr"] = exc.stderr
    finally:
        if started and created:
            dropped = subprocess.run(
                [str(PG_BIN / "dropdb"), "-h", str(socket), "-p", port, "--if-exists", database],
                capture_output=True,
                text=True,
            )
            cleanup["database_dropped"] = dropped.returncode == 0
        if started:
            stopped = subprocess.run(
                [str(PG_BIN / "pg_ctl"), "-D", str(cluster), "-m", "fast", "-w", "stop"],
                capture_output=True,
                text=True,
            )
            cleanup["server_stopped"] = stopped.returncode == 0
        shutil.rmtree(root, ignore_errors=False)
        cleanup["temporary_directory_removed"] = not root.exists()
        OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not all(cleanup.values()):
        if error is not None:
            raise error
        raise SystemExit(f"cleanup failed: {cleanup}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
