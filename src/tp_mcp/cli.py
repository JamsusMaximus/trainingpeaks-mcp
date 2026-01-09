"""CLI commands for TrainingPeaks MCP Server."""

import getpass
import sys

from tp_mcp.auth import (
    AuthStatus,
    clear_credential,
    get_credential,
    get_storage_backend,
    is_keyring_available,
    store_credential,
    validate_auth_sync,
)


def cmd_auth() -> int:
    """Interactive authentication flow.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    print("TrainingPeaks MCP Authentication")
    print("=" * 40)
    print()

    # Check if keyring is available
    if not is_keyring_available():
        print("Warning: No system keyring available.")
        print("Credentials will be stored in an encrypted file.")
        print()

    # Check for existing credential
    existing = get_credential()
    if existing.success and existing.cookie:
        print("Existing credential found. Validating...")
        result = validate_auth_sync(existing.cookie)
        if result.is_valid:
            print(f"Already authenticated as: {result.email}")
            print(f"Athlete ID: {result.athlete_id}")
            print()
            response = input("Re-authenticate? [y/N]: ").strip().lower()
            if response != "y":
                return 0

    print()
    print("To authenticate, you need the Production_tpAuth cookie from TrainingPeaks.")
    print()
    print("Steps:")
    print("1. Log into TrainingPeaks in your browser")
    print("2. Open DevTools (F12) -> Network tab")
    print("3. Navigate to any page on trainingpeaks.com")
    print("4. Find a request to tpapi.trainingpeaks.com")
    print("5. Copy the 'Production_tpAuth' cookie value")
    print()

    # Get cookie from user (use getpass to hide input)
    try:
        cookie = getpass.getpass("Paste cookie value (hidden): ")
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return 1

    if not cookie.strip():
        print("Error: No cookie provided.")
        return 1

    print()
    print("Validating...")

    # Validate the cookie
    result = validate_auth_sync(cookie)

    if not result.is_valid:
        print(f"Error: {result.message}")
        if result.status == AuthStatus.EXPIRED:
            print("The cookie may have expired. Please get a fresh cookie.")
        elif result.status == AuthStatus.INVALID:
            print("The cookie appears to be invalid. Check that you copied it correctly.")
        return 1

    # Store the credential
    store_result = store_credential(cookie)
    if not store_result.success:
        print(f"Error storing credential: {store_result.message}")
        return 1

    print()
    print("Authentication successful!")
    print(f"  Email: {result.email}")
    print(f"  Athlete ID: {result.athlete_id}")
    print()
    print("You can now use 'tp-mcp serve' to start the MCP server.")

    return 0


def cmd_auth_status() -> int:
    """Check current authentication status.

    Returns:
        Exit code (0 for authenticated, 1 for not authenticated).
    """
    cred = get_credential()
    if not cred.success or not cred.cookie:
        print("Not authenticated.")
        print("Run 'tp-mcp auth' to authenticate.")
        return 1

    print("Checking authentication status...")
    result = validate_auth_sync(cred.cookie)

    if result.is_valid:
        print("Authenticated")
        print(f"  Email: {result.email}")
        print(f"  Athlete ID: {result.athlete_id}")
        print(f"  Storage: {get_storage_backend()}")
        return 0
    else:
        print(f"Authentication invalid: {result.message}")
        print("Run 'tp-mcp auth' to re-authenticate.")
        return 1


def cmd_auth_clear() -> int:
    """Clear stored credentials.

    Returns:
        Exit code (0 for success).
    """
    result = clear_credential()
    if result.success:
        print("Credentials cleared.")
    else:
        print(f"Note: {result.message}")
    return 0


def cmd_serve() -> int:
    """Start the MCP server.

    Returns:
        Exit code.
    """
    from tp_mcp.server import run_server

    return run_server()


def cmd_config() -> int:
    """Output Claude Desktop config snippet.

    Returns:
        Exit code (0).
    """
    import json
    import shutil

    # Find the tp-mcp binary path
    tp_mcp_path = shutil.which("tp-mcp")
    if not tp_mcp_path:
        # Fall back to sys.executable directory
        from pathlib import Path
        tp_mcp_path = str(Path(sys.executable).parent / "tp-mcp")

    config = {
        "trainingpeaks": {
            "command": tp_mcp_path,
            "args": ["serve"]
        }
    }

    print("Add this to your Claude Desktop config inside \"mcpServers\": {}")
    print()
    print(json.dumps(config, indent=2))
    return 0


def cmd_help() -> int:
    """Show help message.

    Returns:
        Exit code (0).
    """
    print("TrainingPeaks MCP Server")
    print()
    print("Usage: tp-mcp <command>")
    print()
    print("Commands:")
    print("  auth         Authenticate with TrainingPeaks")
    print("  auth-status  Check authentication status")
    print("  auth-clear   Clear stored credentials")
    print("  config       Output Claude Desktop config snippet")
    print("  serve        Start the MCP server")
    print("  help         Show this help message")
    print()
    return 0


def main() -> int:
    """Main CLI entry point.

    Returns:
        Exit code.
    """
    if len(sys.argv) < 2:
        return cmd_help()

    command = sys.argv[1].lower()

    commands = {
        "auth": cmd_auth,
        "auth-status": cmd_auth_status,
        "auth-clear": cmd_auth_clear,
        "config": cmd_config,
        "serve": cmd_serve,
        "help": cmd_help,
        "--help": cmd_help,
        "-h": cmd_help,
    }

    if command in commands:
        return commands[command]()
    else:
        print(f"Unknown command: {command}")
        print("Run 'tp-mcp help' for usage.")
        return 1
