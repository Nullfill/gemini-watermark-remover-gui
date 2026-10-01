"""
Automation script to package dist/WatermarkRemover into a ZIP and upload to GitHub Release.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request
import zipfile


def get_token():
    # Read from environment or git credential manager
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    try:
        proc = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n",
            capture_output=True,
            text=True,
            check=True
        )
        for line in proc.stdout.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1].strip()
    except Exception as e:
        print("Warning reading git credential:", e)
    return ""


GITHUB_TOKEN = get_token()
REPO = "Nullfill/gemini-watermark-remover-gui"
RELEASE_ID = 400818430
DIST_DIR = Path("dist/WatermarkRemover")
ZIP_NAME = "WatermarkRemover-v1.0.0-windows-x64.zip"
ZIP_PATH = Path(ZIP_NAME)


def sync_assets():
    print("[1/5] Synchronizing runtime assets into dist/WatermarkRemover...")
    # FFmpeg
    ffmpeg_dst = DIST_DIR / "ffmpeg"
    ffmpeg_dst.mkdir(parents=True, exist_ok=True)
    for f in ["ffmpeg.exe", "ffprobe.exe"]:
        src = Path("ffmpeg") / f
        if src.exists():
            shutil.copy2(src, ffmpeg_dst / f)

    # Torchvision C-extensions
    try:
        import torchvision
        tv_dir = Path(os.path.dirname(torchvision.__file__))
        tv_dst = DIST_DIR / "_internal" / "torchvision"
        if tv_dst.exists():
            for pyd in tv_dir.glob("*.pyd"):
                shutil.copy2(pyd, tv_dst / pyd.name)
            for dll in tv_dir.glob("*.dll"):
                shutil.copy2(dll, tv_dst / dll.name)
    except Exception as e:
        print("Torchvision sync notice:", e)

    # Models
    models_dst = DIST_DIR / "models"
    models_dst.mkdir(parents=True, exist_ok=True)
    for pth in Path("models").glob("*.pth"):
        shutil.copy2(pth, models_dst / pth.name)

    # Runtime directories (ensure clean)
    for d in ["input", "output", "temp", "logs"]:
        target = DIST_DIR / d
        target.mkdir(parents=True, exist_ok=True)
        # remove leftover scratch files
        for child in target.glob("*"):
            if child.is_file():
                try:
                    child.unlink()
                except Exception:
                    pass

    # Docs
    for doc in ["README.md", "LICENSE", "NOTICE_PROPAINTER.txt", "NOTICE_FFMPEG.txt"]:
        if Path(doc).exists():
            shutil.copy2(doc, DIST_DIR / doc)

    print("  -> Assets synchronized.")


def create_zip():
    print(f"[2/5] Creating {ZIP_NAME} (this may take a few seconds)...")
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
        for file_path in DIST_DIR.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(DIST_DIR.parent)
                zf.write(file_path, arcname)

    size_mb = ZIP_PATH.stat().st_size / (1024 * 1024)
    print(f"  -> ZIP created successfully: {size_mb:.2f} MB")
    return size_mb


def compute_sha256():
    print("[3/5] Calculating SHA256 checksum...")
    sha = hashlib.sha256()
    with open(ZIP_PATH, "rb") as f:
        while chunk := f.read(1024 * 1024):
            sha.update(chunk)
    digest = sha.hexdigest()
    checksum_file = Path("checksums.txt")
    checksum_file.write_text(f"{digest}  {ZIP_NAME}\n", encoding="utf-8")
    print(f"  -> SHA256: {digest}")
    return digest


def upload_asset(file_path: Path, content_type: str):
    asset_name = file_path.name
    print(f"Uploading {asset_name} to GitHub Release {RELEASE_ID}...")
    file_size = file_path.stat().st_size

    # Check if asset already exists and delete it if so
    list_url = f"https://api.github.com/repos/{REPO}/releases/{RELEASE_ID}/assets"
    req = urllib.request.Request(
        list_url,
        headers={"Authorization": f"Bearer {GITHUB_TOKEN}", "User-Agent": "PythonApp"}
    )
    with urllib.request.urlopen(req) as resp:
        assets = json.loads(resp.read().decode("utf-8"))
        for a in assets:
            if a["name"] == asset_name:
                del_req = urllib.request.Request(
                    a["url"],
                    headers={"Authorization": f"Bearer {GITHUB_TOKEN}", "User-Agent": "PythonApp"},
                    method="DELETE"
                )
                urllib.request.urlopen(del_req)
                print(f"  -> Deleted existing asset {asset_name}")

    upload_url = f"https://uploads.github.com/repos/{REPO}/releases/{RELEASE_ID}/assets?name={asset_name}"
    with open(file_path, "rb") as f:
        data = f.read()

    req = urllib.request.Request(
        upload_url,
        data=data,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "User-Agent": "PythonApp",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": content_type,
            "Content-Length": str(file_size)
        },
        method="POST"
    )

    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        download_url = res.get("browser_download_url")
        print(f"  -> Uploaded successfully: {download_url}")
        return download_url


def main():
    sync_assets()
    create_zip()
    compute_sha256()
    print("[4/5] Uploading checksums.txt...")
    upload_asset(Path("checksums.txt"), "text/plain")
    print("[5/5] Uploading release zip bundle...")
    url = upload_asset(ZIP_PATH, "application/zip")
    print("\n=======================================================")
    print("SUCCESS: Release v1.0.0 is live with portable bundle!")
    print("Download URL:", url)
    print("=======================================================")


if __name__ == "__main__":
    main()
