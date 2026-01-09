"""Browser cookie extraction for TrainingPeaks authentication."""

from dataclasses import dataclass


@dataclass
class BrowserCookieResult:
    """Result of browser cookie extraction."""

    success: bool
    cookie: str | None = None
    message: str = ""
    browser: str | None = None


SUPPORTED_BROWSERS = ["chrome", "firefox", "safari", "edge", "chromium", "brave", "opera"]


def extract_tp_cookie(browser: str | None = None) -> BrowserCookieResult:
    """Extract TrainingPeaks cookie from browser.

    Args:
        browser: Browser name (chrome, firefox, safari, edge, chromium, brave, opera).
                 If None, tries all browsers in order.

    Returns:
        BrowserCookieResult with cookie if found.
    """
    try:
        import browser_cookie3
    except ImportError:
        return BrowserCookieResult(
            success=False,
            message="browser-cookie3 not installed. Run: pip install tp-mcp[browser]",
        )

    # Map browser names to browser_cookie3 functions
    browser_funcs = {
        "chrome": browser_cookie3.chrome,
        "firefox": browser_cookie3.firefox,
        "safari": browser_cookie3.safari,
        "edge": browser_cookie3.edge,
        "chromium": browser_cookie3.chromium,
        "brave": browser_cookie3.brave,
        "opera": browser_cookie3.opera,
    }

    def try_browser(name: str) -> BrowserCookieResult:
        """Try to extract cookie from a specific browser."""
        func = browser_funcs.get(name)
        if not func:
            return BrowserCookieResult(success=False, message=f"Unknown browser: {name}")

        try:
            cj = func(domain_name=".trainingpeaks.com")
            for cookie in cj:
                if cookie.name == "Production_tpAuth" and cookie.value:
                    return BrowserCookieResult(
                        success=True,
                        cookie=cookie.value,
                        browser=name,
                        message=f"Found cookie in {name}",
                    )
            return BrowserCookieResult(success=False, message=f"No TrainingPeaks cookie in {name}")
        except PermissionError:
            return BrowserCookieResult(
                success=False,
                message=f"Permission denied reading {name} cookies. Close {name} and try again.",
            )
        except Exception as e:
            return BrowserCookieResult(success=False, message=f"Error reading {name}: {e}")

    # Try specific browser or all browsers
    if browser:
        browser = browser.lower()
        if browser not in browser_funcs:
            return BrowserCookieResult(
                success=False,
                message=f"Unknown browser: {browser}. Supported: {', '.join(SUPPORTED_BROWSERS)}",
            )
        return try_browser(browser)

    # Try all browsers in order
    errors = []
    for name in SUPPORTED_BROWSERS:
        result = try_browser(name)
        if result.success:
            return result
        errors.append(f"  {name}: {result.message}")

    return BrowserCookieResult(
        success=False,
        message="Could not find TrainingPeaks cookie in any browser.\n" + "\n".join(errors),
    )
