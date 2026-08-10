from pathlib import Path
import hashlib


ASSETS_ROOT = (
    Path(__file__).resolve().parents[1]
    / "assets"
    / "files"
)


def build_asset_file_path(asset_record) -> Path:
    file_path = (
        ASSETS_ROOT
        / str(asset_record.asset_project_id)
        / asset_record.asset_name
    )

    if not file_path.exists():
        raise FileNotFoundError(
            f"File not found: {file_path}"
        )

    return file_path


def calculate_file_checksum(file_path: str | Path) -> str:
    sha256 = hashlib.sha256()

    with Path(file_path).open("rb") as f:
        while chunk := f.read(1024 * 1024):
            sha256.update(chunk)

    return sha256.hexdigest()