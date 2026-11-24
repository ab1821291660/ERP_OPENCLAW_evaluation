#!/usr/bin/env python3
"""Version snapshot and rollback management for Evolution Engine."""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import shutil
import tarfile
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple


SNAPSHOT_PATHS = [
    "skills/",
    "MEMORY.md",
    "AGENTS.md",
    "SOUL.md",
    "IDENTITY.md",
    "USER.md",
    "TOOLS.md",
    "HEARTBEAT.md",
]


def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("version_manager")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


LOGGER = _setup_logger()


class VersionManager:
    """Manage evolution snapshots and restoration."""

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root).resolve()
        self.evolution_dir = self.workspace_root / "evolution"
        self.versions_dir = self.evolution_dir / "versions"
        self.versions_dir.mkdir(parents=True, exist_ok=True)

    def create_snapshot(self, description: str) -> str:
        """Create workspace snapshot and return version_id."""
        timestamp = datetime.now()
        version_id = f"v_{timestamp.strftime('%Y%m%d_%H%M%S')}"
        archive_path = self.versions_dir / f"{version_id}.tar.gz"
        metadata_path = self.versions_dir / f"{version_id}.metadata.json"

        files_hash = self._collect_hashes()
        include_paths = self._collect_existing_paths()

        with tarfile.open(archive_path, mode="w:gz") as tar:
            for rel in include_paths:
                src = self.workspace_root / rel
                arcname = str(Path("snapshot") / rel)
                tar.add(src, arcname=arcname)

        metadata = {
            "version_id": version_id,
            "timestamp": timestamp.isoformat(),
            "description": description,
            "archive": archive_path.name,
            "files_hash": files_hash,
            "snapshot_paths": SNAPSHOT_PATHS,
        }
        self._atomic_write_json(metadata_path, metadata)
        self._append_version_log(
            {
                "event": "snapshot_created",
                "version_id": version_id,
                "description": description,
                "timestamp": timestamp.isoformat(),
            }
        )
        return version_id

    def restore_snapshot(self, version_id: str) -> bool:
        """Rollback workspace to snapshot."""
        archive_path = self.versions_dir / f"{version_id}.tar.gz"
        metadata_path = self.versions_dir / f"{version_id}.metadata.json"

        if not archive_path.exists() or not metadata_path.exists():
            LOGGER.error(f"Snapshot missing for {version_id}")
            return False

        if not self._validate_snapshot(archive_path, metadata_path):
            LOGGER.error(f"Snapshot validation failed for {version_id}")
            return False

        with tempfile.TemporaryDirectory(prefix="evolution_restore_") as temp_dir:
            temp_root = Path(temp_dir)
            with tarfile.open(archive_path, mode="r:gz") as tar:
                tar.extractall(path=temp_root)

            extracted_root = temp_root / "snapshot"
            if not extracted_root.exists():
                LOGGER.error("Extracted snapshot root not found")
                return False

            py_errors = self._validate_python_files(extracted_root)
            if py_errors:
                LOGGER.error(f"Python syntax validation failed: {py_errors}")
                return False

            success = self._atomic_restore(extracted_root)
            if success:
                self._append_version_log(
                    {
                        "event": "snapshot_restored",
                        "version_id": version_id,
                        "timestamp": datetime.now().isoformat(),
                    }
                )
            return success

    def list_versions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List versions by newest first."""
        records: List[Dict[str, Any]] = []
        for item in self.versions_dir.glob("v_*.metadata.json"):
            try:
                data = json.loads(item.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    records.append(data)
            except Exception as exc:
                LOGGER.warning(f"Failed reading metadata {item}: {exc}")

        records.sort(key=lambda x: str(x.get("timestamp", "")), reverse=True)
        return records[:limit]

    def cleanup_old_versions(self, keep_days: int = 30) -> int:
        """Remove snapshots older than keep_days."""
        cutoff = datetime.now() - timedelta(days=keep_days)
        removed = 0

        for metadata_file in self.versions_dir.glob("v_*.metadata.json"):
            try:
                data = json.loads(metadata_file.read_text(encoding="utf-8"))
                ts = datetime.fromisoformat(str(data.get("timestamp", "")))
            except Exception:
                continue

            if ts >= cutoff:
                continue

            version_id = str(data.get("version_id", "")).strip()
            if not version_id:
                continue

            archive_path = self.versions_dir / f"{version_id}.tar.gz"
            try:
                if archive_path.exists():
                    archive_path.unlink()
                metadata_file.unlink()
                removed += 1
            except Exception as exc:
                LOGGER.warning(f"Failed removing {version_id}: {exc}")

        if removed > 0:
            self._append_version_log(
                {
                    "event": "cleanup",
                    "removed": removed,
                    "keep_days": keep_days,
                    "timestamp": datetime.now().isoformat(),
                }
            )
        return removed

    def get_current_version_id(self) -> str:
        """Return latest snapshot version id or empty string."""
        versions = self.list_versions(limit=1)
        if not versions:
            return ""
        return str(versions[0].get("version_id", ""))

    def _collect_existing_paths(self) -> List[str]:
        include_paths: List[str] = []
        for entry in SNAPSHOT_PATHS:
            rel = entry.rstrip("/")
            target = self.workspace_root / rel
            if target.exists():
                include_paths.append(rel)
        return include_paths

    def _collect_hashes(self) -> Dict[str, str]:
        hashes: Dict[str, str] = {}
        for rel in self._collect_existing_paths():
            full = self.workspace_root / rel
            if full.is_file():
                hashes[rel] = self._hash_file(full)
                continue

            for path in full.rglob("*"):
                if not path.is_file():
                    continue
                rel_file = path.relative_to(self.workspace_root)
                hashes[str(rel_file)] = self._hash_file(path)

        return dict(sorted(hashes.items(), key=lambda item: item[0]))

    def _hash_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _validate_snapshot(self, archive_path: Path, metadata_path: Path) -> bool:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("archive") != archive_path.name:
                return False
        except Exception:
            return False

        try:
            with tarfile.open(archive_path, mode="r:gz") as tar:
                members = tar.getmembers()
                if not members:
                    return False
        except Exception:
            return False

        return True

    def _validate_python_files(self, extracted_root: Path) -> List[str]:
        errors: List[str] = []
        for py_file in extracted_root.rglob("*.py"):
            try:
                source = py_file.read_text(encoding="utf-8")
                ast.parse(source)
            except Exception as exc:
                errors.append(f"{py_file}: {exc}")
        return errors

    def _atomic_restore(self, extracted_root: Path) -> bool:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backups: List[Tuple[Path, Path]] = []
        applied: List[Tuple[Path, Path]] = []

        try:
            for raw in SNAPSHOT_PATHS:
                rel = raw.rstrip("/")
                src = extracted_root / rel
                if not src.exists():
                    continue

                dst = self.workspace_root / rel
                backup = self.workspace_root / f"{rel}.bak.{timestamp}"
                backup.parent.mkdir(parents=True, exist_ok=True)

                if dst.exists():
                    shutil.move(str(dst), str(backup))
                    backups.append((dst, backup))

                if src.is_dir():
                    shutil.copytree(src, dst)
                else:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                applied.append((dst, backup))

            return True
        except Exception as exc:
            LOGGER.error(f"Restore apply failed: {exc}")
            for dst, _ in applied:
                try:
                    if dst.is_dir():
                        shutil.rmtree(dst)
                    elif dst.exists():
                        dst.unlink()
                except Exception:
                    continue

            for dst, backup in backups:
                try:
                    if backup.exists() and not dst.exists():
                        shutil.move(str(backup), str(dst))
                except Exception:
                    continue
            return False

    def _append_version_log(self, record: Dict[str, Any]) -> None:
        log_dir = self.evolution_dir / "log"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.md"

        line = f"- {json.dumps(record, ensure_ascii=False)}\n"
        if log_file.exists():
            content = log_file.read_text(encoding="utf-8")
            tmp = log_file.with_suffix(".md.tmp")
            tmp.write_text(f"{content}{line}", encoding="utf-8")
            os.replace(tmp, log_file)
            return

        tmp = log_file.with_suffix(".md.tmp")
        tmp.write_text(f"# Evolution Log {datetime.now().strftime('%Y-%m-%d')}\n\n{line}", encoding="utf-8")
        os.replace(tmp, log_file)

    def _atomic_write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent.parent.parent
    vm = VersionManager(str(root))
    version = vm.create_snapshot("Manual snapshot from version_manager.py")
    print(json.dumps({"ok": True, "version_id": version}, ensure_ascii=False, indent=2))
