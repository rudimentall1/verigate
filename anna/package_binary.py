from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import stat
import sys
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXECUTA_DIR = ROOT / "anna" / "executas" / "verigate-authority"
DIST = EXECUTA_DIR / "dist"

# The platform-minted ID is the identity of this published Executa. The
# local development ID in executa.json is intentionally different.
PLATFORM_TOOL_ID = "tool-rinat-verigate-authority-2um8gwhw"
DISPLAY_NAME = "Verigate Authority"
ZIP_MIN_EPOCH = 315532800  # 1980-01-01T00:00:00Z, the earliest ZIP timestamp.
ZIP_MAX_EPOCH = 4354819198  # 2107-12-31T23:59:58Z, the latest ZIP timestamp.


def build_package_manifest(version: str, description: str, entrypoint: str, windows: bool) -> dict:
    binary_runtime = {"entrypoint": {"default": entrypoint}}
    if not windows:
        binary_runtime["permissions"] = {entrypoint: "0o755"}
    return {
        "name": PLATFORM_TOOL_ID,
        "display_name": DISPLAY_NAME,
        "version": version,
        "description": description,
        "runtime": {"binary": binary_runtime},
    }


def source_date_epoch() -> int:
    """Return the stable build timestamp shared by PyInstaller and the archive packager."""
    raw = os.environ.get("SOURCE_DATE_EPOCH", "0")
    try:
        epoch = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("SOURCE_DATE_EPOCH must be a non-negative integer") from exc
    if epoch < 0:
        raise ValueError("SOURCE_DATE_EPOCH must be a non-negative integer")
    return epoch


def _zip_datetime(epoch: int) -> tuple[int, int, int, int, int, int]:
    # ZIP timestamps have a lower bound of 1980 and two-second resolution.
    safe_epoch = min(max(epoch, ZIP_MIN_EPOCH), ZIP_MAX_EPOCH)
    return datetime.fromtimestamp(safe_epoch, tz=timezone.utc).timetuple()[:6]


def _zip_info(name: str, mode: int, epoch: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=_zip_datetime(epoch))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | mode) << 16
    info.internal_attr = 0
    info.extra = b""
    info.comment = b""
    info.flag_bits = 0
    return info


def _tar_info(name: str, payload: bytes, mode: int, epoch: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.REGTYPE
    info.size = len(payload)
    info.mode = mode
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = epoch
    info.pax_headers = {}
    return info


def write_reproducible_archive(
    archive: Path,
    binary: Path,
    manifest_bytes: bytes,
    entrypoint: str,
    *,
    windows: bool,
    epoch: int | None = None,
) -> None:
    """Write a ZIP/TAR.GZ whose metadata does not depend on the runner clock or file mtimes."""
    build_epoch = source_date_epoch() if epoch is None else epoch
    if isinstance(build_epoch, bool) or not isinstance(build_epoch, int) or build_epoch < 0:
        raise ValueError("epoch must be a non-negative integer")

    binary_bytes = binary.read_bytes()
    if windows:
        with zipfile.ZipFile(
            archive, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as packaged:
            packaged.writestr(
                _zip_info(entrypoint, 0o755, build_epoch),
                binary_bytes,
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )
            packaged.writestr(
                _zip_info("manifest.json", 0o644, build_epoch),
                manifest_bytes,
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )
        return

    # gzip's header timestamp and both TAR member timestamps are explicitly
    # pinned; ownership and file modes are stable across runner accounts.
    with archive.open("wb") as raw_archive:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw_archive,
            compresslevel=9,
            mtime=build_epoch,
        ) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as packaged:
                packaged.addfile(
                    _tar_info(entrypoint, binary_bytes, 0o755, build_epoch),
                    io.BytesIO(binary_bytes),
                )
                packaged.addfile(
                    _tar_info("manifest.json", manifest_bytes, 0o644, build_epoch),
                    io.BytesIO(manifest_bytes),
                )


def verify_archive(archive: Path, entrypoint: str, windows: bool) -> None:
    """Fail packaging unless the archive has exactly the expected files and manifest."""
    if windows:
        with zipfile.ZipFile(archive) as packaged:
            names = packaged.namelist()
            if len(names) != 2 or set(names) != {"manifest.json", entrypoint}:
                raise SystemExit(f"invalid archive layout: {names}")
            manifest = json.loads(packaged.read("manifest.json").decode("utf-8"))
    else:
        with tarfile.open(archive, "r:gz") as packaged:
            names = packaged.getnames()
            if len(names) != 2 or set(names) != {"manifest.json", entrypoint}:
                raise SystemExit(f"invalid archive layout: {names}")
            member = packaged.extractfile("manifest.json")
            if member is None:
                raise SystemExit("archive manifest.json could not be read")
            manifest = json.loads(member.read().decode("utf-8"))
            binary_member = next((item for item in packaged.getmembers() if item.name == entrypoint), None)
            if binary_member is None or not (binary_member.mode & 0o111):
                raise SystemExit("Unix binary entrypoint is not executable in the archive")

    configured = manifest.get("runtime", {}).get("binary", {}).get("entrypoint", {}).get("default")
    if configured != entrypoint:
        raise SystemExit(f"manifest entrypoint mismatch: expected {entrypoint!r}, got {configured!r}")
    if not manifest.get("version") or not manifest.get("name") or not manifest.get("description"):
        raise SystemExit("distribution manifest is missing name, version, or description")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: python anna/package_binary.py <target> <version>")
    target, version = sys.argv[1], sys.argv[2]
    tool = json.loads((EXECUTA_DIR / "executa.json").read_text(encoding="utf-8"))
    expected = tool["version"]
    if version != expected:
        raise SystemExit(f"version mismatch: workflow={version}, executa.json={expected}")

    windows = target == "windows-x86_64"
    if target not in {"darwin-arm64", "darwin-x86_64", "linux-x86_64", "windows-x86_64"}:
        raise SystemExit(f"unsupported target: {target}")

    binary = DIST / ("verigate-authority.exe" if windows else "verigate-authority")
    if not binary.is_file():
        raise SystemExit(f"built binary not found: {binary}")

    archive_name = (
        f"verigate-authority-{version}-{target}.zip"
        if windows
        else f"verigate-authority-{version}-{target}.tar.gz"
    )
    archive = DIST / archive_name
    if archive.exists():
        archive.unlink()

    entrypoint = binary.name
    package_manifest = build_package_manifest(
        version=version,
        description=(
            "Evaluates an agent action against Verigate's deterministic policy and returns "
            "a signed ALLOW/WARN/BLOCK decision and capability-bound authorization. It does not "
            "hold wallet keys, sign a wallet transaction, broadcast, or execute a blockchain transaction."
        ),
        entrypoint=entrypoint,
        windows=windows,
    )
    manifest_bytes = (json.dumps(package_manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

    epoch = source_date_epoch()
    write_reproducible_archive(
        archive,
        binary,
        manifest_bytes,
        entrypoint,
        windows=windows,
        epoch=epoch,
    )

    verify_archive(archive, entrypoint, windows)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")

    print(f"Verified package: {archive}")
    print("Archive root: manifest.json, " + entrypoint)
    print(f"SOURCE_DATE_EPOCH: {epoch}")
    print(f"SHA-256: {digest}")
    print(f"Size: {archive.stat().st_size} bytes")


if __name__ == "__main__":
    main()
