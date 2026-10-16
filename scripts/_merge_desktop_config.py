"""Add or remove the tp-mcp server entry in Claude Desktop's config file.

Used by install-macos.command and uninstall-macos.command; standard library
only, so any Python 3.10+ can run it before or after the venv exists.

    python3 _merge_desktop_config.py add    <config.json> <tp-mcp executable>
    python3 _merge_desktop_config.py remove <config.json>

Rules:
- Every other key and server in the file is left exactly as it was.
- An existing file is copied to <config>.bak-<YYYYMMDD-HHMMSS> before any write.
- The write goes to a temporary file in the same folder, then is renamed over
  the original, so a crash never leaves a half-written config.
- A file that is not valid JSON (or whose top level is not an object) is never
  touched: exit code 2 and a one-line reason on stderr.
"""

import json
import os
import shutil
import sys
import tempfile
import time

SERVER_NAME = "trainingpeaks"
SERVE_ARGS = ["serve", "--read-only"]

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_INVALID = 2


class InvalidConfigError(Exception):
    pass


def _load(path: str) -> dict | None:
    """The parsed config, or None when the file does not exist or is empty."""
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if not text.strip():
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise InvalidConfigError(f"{path} is not valid JSON (line {e.lineno}, column {e.colno})") from None
    if not isinstance(data, dict):
        raise InvalidConfigError(f"{path} does not contain a JSON object")
    servers = data.get("mcpServers")
    if servers is not None and not isinstance(servers, dict):
        raise InvalidConfigError(f'{path}: "mcpServers" is not a JSON object')
    return data


def _backup(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    dest = f"{path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    n = 1
    while os.path.exists(dest):
        dest = f"{path}.bak-{time.strftime('%Y%m%d-%H%M%S')}-{n}"
        n += 1
    shutil.copy2(path, dest)
    return dest


def _write(path: str, data: dict) -> None:
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".claude_desktop_config.", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def add(path: str, command: str) -> str:
    data = _load(path) or {}
    entry = {"command": command, "args": list(SERVE_ARGS)}
    servers = data.get("mcpServers") or {}
    if servers.get(SERVER_NAME) == entry:
        return "unchanged"
    _backup(path)
    data["mcpServers"] = {**servers, SERVER_NAME: entry}
    _write(path, data)
    return "updated"


def remove(path: str) -> str:
    data = _load(path)
    if not data or SERVER_NAME not in (data.get("mcpServers") or {}):
        return "absent"
    _backup(path)
    servers = dict(data["mcpServers"])
    del servers[SERVER_NAME]
    data["mcpServers"] = servers
    _write(path, data)
    return "removed"


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[0] == "add":
        fn, args = add, (argv[1], argv[2])
    elif len(argv) == 2 and argv[0] == "remove":
        fn, args = remove, (argv[1],)
    else:
        print("usage: _merge_desktop_config.py add <config.json> <tp-mcp> | remove <config.json>",
              file=sys.stderr)
        return EXIT_USAGE
    try:
        print(fn(*args))
    except InvalidConfigError as e:
        print(str(e), file=sys.stderr)
        return EXIT_INVALID
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
