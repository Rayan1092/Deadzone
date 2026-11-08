"""Exercise the launcher with PowerShell doubles only: never open a real tunnel."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHELL = shutil.which("powershell.exe") or shutil.which("pwsh")
pytestmark = pytest.mark.skipif(SHELL is None, reason="PowerShell not installed on this host")


def run_stub(stub):
    path = str(ROOT / "scripts/tunnel.ps1").replace("'", "''")
    return subprocess.run([SHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
                           stub + "; & '" + path + "'"], capture_output=True, text=True, timeout=15)


def test_prints_origin_phone_once_and_uses_exact_requested_arguments():
    result = run_stub('''function cloudflared {
        if (($args -join '|') -ne 'tunnel|--url|http://localhost:8000') { throw 'wrong arguments' }
        '2026 INF | https://example-d2.trycloudflare.com |'
        '2026 INF https://example-d2.trycloudflare.com'
        $global:LASTEXITCODE = 0
    }''')
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("HTTPS URL: https://example-d2.trycloudflare.com") == 1
    assert "Phone URL: https://example-d2.trycloudflare.com/phone" in result.stdout


def test_missing_cloudflared_fails_without_starting_any_process():
    result = run_stub("function Get-Command { return $null }")
    assert result.returncode == 1
    assert "FAIL cloudflared PATH: missing" in result.stdout


def test_normal_stderr_url_is_accepted_without_echoing_other_log_contents():
    result = run_stub('''function cloudflared {
        Write-Error 'fake-private-log-do-not-print'
        Write-Error '2026 INF | https://stderr-d2.trycloudflare.com |'
        $global:LASTEXITCODE = 0
    }''')
    assert result.returncode == 0, result.stderr
    assert "HTTPS URL: https://stderr-d2.trycloudflare.com" in result.stdout
    assert "fake-private-log-do-not-print" not in result.stdout + result.stderr


@pytest.mark.parametrize("stub", [
    "function cloudflared { 'no URL here'; $global:LASTEXITCODE = 0 }",
    "function cloudflared { 'https://example-d2.trycloudflare.com'; $global:LASTEXITCODE = 9 }",
])
def test_failed_child_or_missing_url_is_failure(stub):
    result = run_stub(stub)
    assert result.returncode == 1
    assert "FAIL tunnel:" in result.stdout


def test_script_is_immediately_before_phone_test_in_runbook():
    text = (ROOT / "docs/DEMO.md").read_text(encoding="utf-8")
    assert text.index("6. **Before the phone test") < text.index("scripts/tunnel.ps1") < text.index("7. **Test the phone:")
