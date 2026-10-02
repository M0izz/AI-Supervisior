import asyncio
import re
from pathlib import Path
from typing import Optional
from tools.base import BaseTool, ToolResult
from execution.manager import ExecutionManager
from execution.models import ExecutionRequest, ExecutionStatus


class RunTestsTool(BaseTool):
    name = "run_tests"
    description = "Run test suite and parse structured test results and failure signatures."

    def __init__(self, workspace_root: Path, execution_manager: Optional[ExecutionManager] = None):
        super().__init__(workspace_root)
        self.execution_manager = execution_manager or ExecutionManager()

    async def execute(self, test_command: str = "python -m pytest tests/ -v", timeout: int = 45) -> ToolResult:
        try:
            req = ExecutionRequest(
                command=test_command,
                workspace_root=self.workspace_root,
                timeout_seconds=timeout
            )
            res = await self.execution_manager.execute(req)

            out_str = res.stdout or ""
            err_str = res.stderr or ""
            combined = out_str + "\n" + err_str
            passed, failed, error_sig = self._parse_test_summary(combined)

            success = (res.exit_code == 0) and (failed == 0) and (passed > 0)
            return ToolResult(
                success=success,
                output=out_str,
                error=err_str if not success else None,
                metadata={
                    "passed": passed,
                    "failed": failed,
                    "error_signature": error_sig,
                    "returncode": res.exit_code,
                    "backend": res.backend,
                    "container_id": res.container.container_id if res.container else None
                }
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
                metadata={"passed": 0, "failed": 1, "error_signature": "TEST_RUNNER_EXCEPTION"}
            )

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
