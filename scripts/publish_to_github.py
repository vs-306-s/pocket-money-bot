# -*- coding: utf-8 -*-
"""
Выкладывает проект на GitHub через HTTP API — git на компьютере НЕ нужен.

Как пользоваться:

  1) Создай токен доступа:
     GitHub → аватар → Settings → Developer settings →
     Personal access tokens → Tokens (classic) → Generate new token (classic)
     → отметь галочку «repo» → Generate token → скопируй (показывается один раз).

  2) Сохрани токен в файл `gh_token.txt` в папке проекта — одной строкой.
     Файл в .gitignore и на GitHub никогда не загружается.

  3) Запусти:
        python scripts/publish_to_github.py                  # приватный репозиторий
        python scripts/publish_to_github.py --public          # публичный
        python scripts/publish_to_github.py --dry-run         # только показать список файлов

Секреты (config.json, gh_token.txt, data/, .env) не загружаются никогда.
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path

import httpx

# Русская консоль часто в cp1251 — без этого print с эмодзи падает
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.github.com"

SKIP_DIRS = {".git", "data", "__pycache__", ".venv", "venv", "node_modules",
             ".pytest_cache", ".mypy_cache", ".idea", ".vscode", ".github"}
SKIP_FILES = {"config.json", "gh_token.txt", ".env", "probe.txt", "check.txt",
              "config.local.json"}
SKIP_SUFFIX = {".db", ".pyc", ".log", ".session", ".zip", ".exe", ".sqlite", ".xlsx"}
TEXT_SUFFIX = {".py", ".md", ".txt", ".json", ".ini", ".cfg", ".toml", ".yml", ".yaml",
               ".bat", ".vbs", ".cmd", ".example"}
ALLOW_NAMES = {"Dockerfile", "Procfile", "requirements.txt", ".gitignore",
               ".dockerignore", "LICENSE", "runtime.txt", ".env.example"}
MAX_SIZE = 1_000_000  # байт


def collect_files() -> dict[str, bytes]:
    """Собирает файлы проекта, кроме секретов и мусора."""
    files: dict[str, bytes] = {}
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if set(relative.parts[:-1]) & SKIP_DIRS:
            continue

        name = relative.name
        if name in SKIP_FILES or relative.suffix.lower() in SKIP_SUFFIX:
            continue
        if relative.parent == Path(".") and relative.suffix.lower() in {".txt", ".log"} \
                and name != "requirements.txt":
            continue
        if name.startswith(".") and name not in {".gitignore", ".dockerignore", ".env.example"}:
            continue
        if relative.suffix.lower() not in TEXT_SUFFIX and name not in ALLOW_NAMES:
            continue
        if path.stat().st_size > MAX_SIZE:
            continue

        files[relative.as_posix()] = path.read_bytes()
    return files


def api(client: httpx.Client, method: str, url: str, **kwargs) -> dict:
    response = client.request(method, url, **kwargs)
    if response.status_code >= 400:
        hint = ""
        if response.status_code == 401:
            hint = "\nТокен неверный или просрочен — создай новый (scope «repo»)."
        elif response.status_code == 403:
            hint = "\nУ токена нет нужных прав: нужен scope «repo»."
        raise SystemExit(f"❌ GitHub ответил {response.status_code}: {response.text[:300]}{hint}")
    if not response.text:
        return {}
    try:
        return response.json()
    except ValueError:
        return {}


def read_token() -> str:
    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if token:
        return token
    token_file = ROOT / "gh_token.txt"
    if token_file.exists():
        return token_file.read_text(encoding="utf-8").strip()
    return ""


def ensure_git_database(client: httpx.Client, owner: str, repo: str, branch: str,
                        files: dict[str, bytes]) -> None:
    """В пустом репозитории GitHub не даёт создавать blobs — делаем первый коммит."""
    ref = client.get(f"{API}/repos/{owner}/{repo}/git/ref/heads/{branch}")
    if ref.status_code == 200:
        return
    content = files.get(".gitignore", b"# init\n")
    api(client, "PUT", f"{API}/repos/{owner}/{repo}/contents/.gitignore", json={
        "message": f"init: создаю ветку {branch}",
        "content": base64.b64encode(content).decode("ascii"),
        "branch": branch,
    })
    print("   создал первый коммит (без него GitHub запрещает загрузку файлов)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Выложить проект на GitHub без git")
    parser.add_argument("repo", nargs="?", default=ROOT.name, help="имя репозитория")
    parser.add_argument("--public", action="store_true", help="сделать репозиторий публичным")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--message",
                        default="Telegram-бот «Карманные деньги по оценкам»: фото дневника → оценки → отчёт Excel")
    parser.add_argument("--description",
                        default="Telegram-бот: считает карманные деньги по оценкам из фото дневника "
                                "и собирает отчёт в Excel (ставки и коэффициенты настраиваются)")
    parser.add_argument("--dry-run", action="store_true", help="только показать, что будет загружено")
    args = parser.parse_args()

    files = collect_files()
    print(f"📦 Файлов к загрузке: {len(files)}")
    for name in files:
        print("   ", name)
    print("🚫 Пропущено (секреты и служебное): config.json, gh_token.txt, data/, .env, кеш")
    if args.dry_run:
        print("\nПробный прогон — ничего не отправлено.")
        return

    token = read_token()
    if not token:
        print("\n❌ Не нашёл токен GitHub.\n"
              "   Сохрани его в файл gh_token.txt (одной строкой) или задай GITHUB_TOKEN.")
        return

    with httpx.Client(timeout=60, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "pocket-money-bot-publisher",
    }) as client:
        user = api(client, "GET", f"{API}/user")
        owner = user.get("login") or user.get("name")
        print(f"\n👤 Аккаунт: {owner}")

        existing = client.get(f"{API}/repos/{owner}/{args.repo}")
        if existing.status_code == 404:
            print(f"🆕 Создаю репозиторий {owner}/{args.repo} "
                  f"({'публичный' if args.public else 'приватный'})…")
            api(client, "POST", f"{API}/user/repos", json={
                "name": args.repo,
                "description": args.description,
                "private": not args.public,
                "has_issues": True,
                "has_wiki": False,
                "auto_init": False,
            })
        else:
            print(f"📁 Репозиторий уже есть: {owner}/{args.repo} — обновляю его.")

        ensure_git_database(client, owner, args.repo, args.branch, files)

        print("⬆️ Загружаю файлы…")
        tree = []
        for index, (path, content) in enumerate(files.items(), 1):
            blob = api(client, "POST", f"{API}/repos/{owner}/{args.repo}/git/blobs",
                       json={"content": base64.b64encode(content).decode("ascii"),
                             "encoding": "base64"})
            tree.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
            print(f"   [{index}/{len(files)}] {path}")

        new_tree = api(client, "POST", f"{API}/repos/{owner}/{args.repo}/git/trees",
                       json={"tree": tree})

        parents: list[str] = []
        ref = client.get(f"{API}/repos/{owner}/{args.repo}/git/ref/heads/{args.branch}")
        if ref.status_code == 200:
            parents = [ref.json()["object"]["sha"]]

        commit = api(client, "POST", f"{API}/repos/{owner}/{args.repo}/git/commits",
                     json={"message": args.message, "tree": new_tree["sha"], "parents": parents})

        if parents:
            api(client, "PATCH", f"{API}/repos/{owner}/{args.repo}/git/refs/heads/{args.branch}",
                json={"sha": commit["sha"], "force": True})
        else:
            api(client, "POST", f"{API}/repos/{owner}/{args.repo}/git/refs",
                json={"ref": f"refs/heads/{args.branch}", "sha": commit["sha"]})

    link = f"https://github.com/{owner}/{args.repo}"
    print(f"\n✅ Готово: {link}")
    print(f"   Файлов в коммите: {len(files)}")


if __name__ == "__main__":
    main()
