import argparse
import hashlib
import zipfile
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, default=Path("release"))
    return parser.parse_args()


def add_file(archive, source: Path, target: Path):
    archive.write(source, target.as_posix())


def main():
    args = parse_args()
    if not args.bundle.is_dir():
        raise SystemExit(f"Bundle directory does not exist: {args.bundle}")

    args.output.mkdir(parents=True, exist_ok=True)
    archive_name = f"kali-publish-{args.version}-{args.platform}.zip"
    archive_path = args.output / archive_name
    root = Path("kali-publish")

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source in sorted(args.bundle.rglob("*")):
            if source.is_file():
                add_file(archive, source, root / source.relative_to(args.bundle))
        add_file(archive, Path("README_RELEASE.md"), root / "README.md")
        add_file(archive, Path("LICENSE"), root / "LICENSE")

    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum_path = archive_path.with_suffix(archive_path.suffix + ".sha256")
    checksum_path.write_text(f"{digest}  {archive_name}\n", encoding="utf-8")
    print(archive_path)
    print(checksum_path)


if __name__ == "__main__":
    main()
