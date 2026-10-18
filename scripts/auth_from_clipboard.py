"""Validate and store a TrainingPeaks Production_tpAuth cookie from the macOS clipboard.

Usage:
    .venv/bin/python scripts/auth_from_clipboard.py

The script pauses FIRST, so you copy the cookie after the script is already
running. This avoids the trap where copying the command itself overwrites the
cookie on the clipboard.

The cookie is read from the clipboard so it is never typed, never echoed into
scrollback, and never pasted into a hidden prompt. It is validated against
TrainingPeaks before being written to the credential store.
"""

import subprocess
import sys

from tp_mcp.auth import store_credential
from tp_mcp.auth.validator import validate_auth_sync


def read_clipboard() -> str:
    return subprocess.run(["pbpaste"], capture_output=True, text=True).stdout.strip()


def main() -> int:
    print()
    print("=" * 60)
    print("  COPY THE COOKIE NOW - the clipboard is read after you continue.")
    print("=" * 60)
    print()
    print("  1. Switch to your browser, logged into app.trainingpeaks.com")
    print("  2. DevTools -> Application -> Cookies -> https://app.trainingpeaks.com")
    print("  3. Click the 'Production_tpAuth' row, copy the VALUE")
    print("     (use the detail panel at the bottom - the table view truncates)")
    print("  4. Come back here and press Return")
    print()

    try:
        input("Press Return once the cookie is copied... ")
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return 1

    cookie = read_clipboard()
    print(f"\nclipboard length: {len(cookie)}")

    if not cookie:
        print("ERROR: clipboard is empty.")
        return 1

    if any(ch in cookie for ch in ("\n", " ", "\t")):
        print("ERROR: clipboard contains whitespace - that is not a cookie value.")
        print(f"first 60 chars: {cookie[:60]!r}")
        return 1

    print("validating against TrainingPeaks...")
    result = validate_auth_sync(cookie)
    print(f"status: {result.status} | {result.message}")

    if not result.is_valid:
        print("Not stored.")
        return 1

    print(f"email:      {result.email}")
    print(f"athlete_id: {result.athlete_id}")
    print(f"user_id:    {result.user_id}")

    store_result = store_credential(cookie)
    print(f"store: {store_result.success} | {store_result.message}")
    return 0 if store_result.success else 1


if __name__ == "__main__":
    sys.exit(main())
