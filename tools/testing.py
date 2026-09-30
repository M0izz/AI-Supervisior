import asyncio
import re
from pathlib import Path
from tools.base import BaseTool, ToolResult


class RunTestsTool(BaseTool):
    name = "run_tests"
    description = "Run test suite and parse structured test results and failure signatures."

    async def execute(self, test_command: str = "python -m pytest tests/ -v") -> ToolResult:
        try:
            process = await asyncio.create_subprocess_shell(
                test_command,
                cwd=str(self.workspace_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=45)
            out_str = stdout.decode("utf-8", errors="replace")
            err_str = stderr.decode("utf-8", errors="replace")

            combined = out_str + "\n" + err_str
            passed, failed, error_sig = self._parse_test_summary(combined)

            success = (process.returncode == 0) and (failed == 0)
            return ToolResult(
                success=success,
                output=out_str,
                error=err_str if not success else None,
                metadata={
                    "passed": passed,
                    "failed": failed,
                    "error_signature": error_sig,
                    "returncode": process.returncode
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e), metadata={"passed": 0, "failed": 1, "error_signature": "TEST_RUNNER_EXCEPTION"})

    def _parse_test_summary(self, text: str):
        passed = 0
        failed = 0
        error_sig = None

        # Check pytest format: e.g. "43 passed, 2 failed"
        pass_match = re.search(r"(\d+)\s+passed", text)
        if pass_match:
            passed = int(pass_match.group(1))

        fail_match = re.search(r"(\d+)\s+failed", text)
        if fail_match:
            failed = int(fail_match.group(1))

        # Check for error signatures
        if "FAILED" in text or failed > 0:
            lines = [l for l in text.split("\n") if "FAILED" in l or "Error:" in l or "Mismatch" in l]
            if lines:
                error_sig = lines[0].strip()[:100]
            else:
                error_sig = "GENERIC_TEST_FAILURE"

        return passed, failed, error_sig
