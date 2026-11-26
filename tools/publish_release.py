#!/usr/bin/env python3
"""Uppdatera eller skapa GitHub-releasen för aktuell APP_VERSION och markera som Latest.

Hård regel i FolderForge:
- Arbeta aldrig mot `main`.
- Vid varje kodförändring måste releasen uppdateras så att releasens git-tagg
  pekar på aktuell commit-SHA och releasen är markerad som `Latest`, eftersom
  `updater.py` jämför `/releases/latest` -> `/commits/<tag>` -> SHA-256 `content_manifest`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import settings  # noqa: E402
import updater  # noqa: E402

REPO = updater.REPOSITORY


def run_cmd(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=check)


def extract_current_release_notes(tag: str) -> str:
    notes_path = ROOT / "RELEASE_NOTES.md"
    if not notes_path.is_file():
        return f"FolderForge {tag}"
    lines = notes_path.read_text(encoding="utf-8").splitlines()
    collected: list[str] = []
    for line in lines:
        if line.strip() == "---" and collected:
            break
        collected.append(line)
    return "\n".join(collected).strip() or f"FolderForge {tag}"


def ensure_not_main_and_clean(*, skip_clean_check: bool) -> tuple[str, str]:
    branch = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    if branch == "main":
        raise SystemExit("FEL (hård regel): Arbeta eller publicera aldrig direkt från `main`.")
    if not skip_clean_check:
        dirty = run_cmd(["git", "status", "--porcelain"]).stdout.strip()
        if dirty:
            raise SystemExit(f"FEL: Ocommittade ändringar i arbetskatalogen:\n{dirty}")
    return branch, run_cmd(["git", "rev-parse", "HEAD"]).stdout.strip()


def sync_standard_branch(active_branch: str) -> None:
    """Säkerställer standardbranch-disciplin (endast aktiv standardbranch kvar när API tillåter)."""
    info = run_cmd(["gh", "api", f"repos/{REPO}", "--jq", ".default_branch"], check=False)
    if info.returncode != 0:
        return
    default_branch = info.stdout.strip()
    if default_branch != active_branch:
        patched = run_cmd(
            ["gh", "api", "-X", "PATCH", f"repos/{REPO}", "-f", f"default_branch={active_branch}"],
            check=False,
        )
        if patched.returncode == 0:
            default_branch = active_branch
            print(f"Standardbranch på GitHub uppdaterad till: {active_branch}")
        else:
            print(
                f"OBS: GitHub-token saknar admin-rättighet att byta Default branch ({default_branch} -> {active_branch}). "
                f"Byt en gång under https://github.com/{REPO}/settings så raderas gamla sidobrancher automatiskt."
            )
    branches_res = run_cmd(["gh", "api", f"repos/{REPO}/branches", "--jq", ".[].name"], check=False)
    if branches_res.returncode == 0:
        for other in branches_res.stdout.splitlines():
            other = other.strip()
            if other and other != active_branch and other != default_branch:
                deleted = run_cmd(
                    ["gh", "api", "-X", "DELETE", f"repos/{REPO}/git/refs/heads/{other}"],
                    check=False,
                )
                if deleted.returncode == 0:
                    print(f"Tog bort överbliven sidobranch: {other}")


def sync_tag_and_release(target_sha: str) -> str:
    tag = f"v{settings.APP_VERSION.lstrip('v')}"
    notes = extract_current_release_notes(tag)
    title = f"FolderForge {tag}"

    # 1. Kontrollera om git-taggen redan finns på GitHub och pekar på target_sha
    tag_ref = run_cmd(["gh", "api", f"repos/{REPO}/git/refs/tags/{tag}"], check=False)
    if tag_ref.returncode == 0:
        current_sha = json.loads(tag_ref.stdout).get("object", {}).get("sha", "")
        if current_sha != target_sha:
            print(f"Flyttar tagg {tag}: {current_sha[:7]} -> {target_sha[:7]} ...")
            run_cmd([
                "gh", "api", "-X", "PATCH", f"repos/{REPO}/git/refs/tags/{tag}",
                "-f", f"sha={target_sha}", "-F", "force=true",
            ])
            run_cmd(["git", "tag", "-f", tag, target_sha], check=False)
    else:
        print(f"Skapar ny git-tagg {tag} -> {target_sha[:7]} ...")
        run_cmd([
            "gh", "api", "-X", "POST", f"repos/{REPO}/git/refs",
            "-f", f"ref=refs/tags/{tag}", "-f", f"sha={target_sha}",
        ])

    # 2. Skapa eller uppdatera GitHub-releasen och markera alltid som Latest
    rel_info = run_cmd(["gh", "api", f"repos/{REPO}/releases/tags/{tag}"], check=False)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as tmp:
        tmp.write(notes)
        notes_file = Path(tmp.name)
    try:
        if rel_info.returncode == 0:
            rel_id = json.loads(rel_info.stdout)["id"]
            print(f"Uppdaterar befintlig release {tag} (id={rel_id}) och markerar som Latest ...")
            run_cmd([
                "gh", "api", "-X", "PATCH", f"repos/{REPO}/releases/{rel_id}",
                "-f", f"tag_name={tag}",
                "-f", f"target_commitish={target_sha}",
                "-f", f"name={title}",
                "-F", "draft=false",
                "-F", "prerelease=false",
                "-f", "make_latest=true",
                "-f", f"body={notes}",
            ])
        else:
            print(f"Skapar ny release {tag} och markerar som Latest ...")
            run_cmd([
                "gh", "release", "create", tag,
                "--target", target_sha,
                "--title", title,
                "--latest",
                "--notes-file", str(notes_file),
            ])
    finally:
        notes_file.unlink(missing_ok=True)
    return tag


def verify_live_updater(tag: str, expected_sha: str) -> None:
    local_hashes = updater.content_manifest(ROOT)
    last_err: Exception | None = None
    for attempt in range(1, 5):
        try:
            with tempfile.TemporaryDirectory() as td:
                base = Path(td)
                (base / "data").mkdir()
                ok = updater.check_once(base, "0.0.1", force=True)
                state = updater.read_state(base)
                if not ok or state.get("pending") != tag:
                    raise AssertionError(f"Väntade pending={tag}, fick: {state}")
                if state.get("pending_revision") != expected_sha:
                    raise AssertionError(
                        f"Taggen har inte propagerat ännu ({state.get('pending_revision')} != {expected_sha})"
                    )
                if state.get("pending_hashes") != local_hashes:
                    diff = set(local_hashes.items()) ^ set((state.get("pending_hashes") or {}).items())
                    raise AssertionError(f"SHA-256-avvikelse mellan repo och live-release: {diff}")
                print(
                    f"OK: Live Latest-release {tag} ({expected_sha[:10]}) verifierad via updater.py "
                    f"({len(local_hashes)} SHA-256-filhashar matchar 100 %)."
                )
                return
        except Exception as exc:
            last_err = exc
            if attempt < 4:
                time.sleep(2 * attempt)
    raise SystemExit(f"FEL vid live-verifiering av releasen: {last_err}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", help="Explicit commit-SHA (används av CI workflow_run)")
    parser.add_argument("--skip-clean-check", action="store_true", help="Hoppa över git status-kontroll i CI")
    args = parser.parse_args()

    active_branch, detected_sha = ensure_not_main_and_clean(skip_clean_check=args.skip_clean_check)
    head_sha = args.sha or detected_sha
    sync_standard_branch(active_branch)
    tag = sync_tag_and_release(head_sha)
    verify_live_updater(tag, head_sha)


if __name__ == "__main__":
    main()
