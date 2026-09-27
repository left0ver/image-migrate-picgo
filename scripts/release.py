# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Bump the version, tag it, and push to trigger the PyPI release workflow.

Usage:
    uv run scripts/release.py patch          # 0.1.0 -> 0.1.1
    uv run scripts/release.py minor          # 0.1.0 -> 0.2.0
    uv run scripts/release.py 1.0.0          # explicit version
    uv run scripts/release.py patch --dry-run
    uv run scripts/release.py patch --yes    # push without confirmation
"""

import argparse
import subprocess
import sys

BUMPS = ("major", "minor", "patch", "stable", "alpha", "beta", "rc", "post", "dev")
RELEASE_BRANCH = "main"


def run(*args: str) -> str:
    return subprocess.run(
        args, check=True, capture_output=True, text=True
    ).stdout.strip()


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def confirm(prompt: str) -> bool:
    try:
        return input(f"{prompt} [y/N] ").strip().lower() == "y"
    except EOFError:
        print()
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "version",
        help=f"one of {', '.join(BUMPS)}, or an explicit version such as 1.0.0",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show the new version without changing anything",
    )
    parser.add_argument(
        "-y", "--yes", action="store_true", help="push without asking for confirmation"
    )
    args = parser.parse_args()

    version_args = ["--bump", args.version] if args.version in BUMPS else [args.version]
    current = run("uv", "version", "--short")
    new = run("uv", "version", *version_args, "--dry-run", "--short")
    tag = f"v{new}"
    print(f"{current} -> {new}")
    if args.dry_run:
        return

    if run("git", "status", "--porcelain"):
        fail("working tree is not clean; commit or stash your changes first")
    branch = run("git", "branch", "--show-current")
    if branch != RELEASE_BRANCH:
        fail(
            f"releases must be made from '{RELEASE_BRANCH}', but the current branch is '{branch}'"
        )
    if run("git", "tag", "--list", tag):
        fail(f"tag {tag} already exists")

    print("Running unit tests...")
    subprocess.run(
        ["uv", "run", "--locked", "python", "-m", "unittest", "discover", "-s", "test"],
        check=True,
    )

    subprocess.run(["uv", "version", *version_args], check=True)
    subprocess.run(
        ["git", "commit", "-m", f"chore: 发布 {tag}", "pyproject.toml", "uv.lock"],
        check=True,
    )
    subprocess.run(["git", "tag", "-a", tag, "-m", tag], check=True)

    if not args.yes and not confirm(f"Push {tag} to origin and publish to PyPI?"):
        print(
            f"Not pushed. To publish later: git push --atomic origin {RELEASE_BRANCH} {tag}"
        )
        print(f"To undo: git tag -d {tag} && git reset --hard HEAD~1")
        return
    subprocess.run(
        ["git", "push", "--atomic", "origin", RELEASE_BRANCH, tag], check=True
    )
    print(f"Pushed {tag}. The release workflow will publish it to PyPI.")


if __name__ == "__main__":
    main()
