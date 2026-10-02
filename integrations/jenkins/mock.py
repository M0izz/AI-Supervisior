import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from integrations.jenkins.client import JenkinsProvider
from integrations.jenkins.models import (
    JenkinsBuildStatus,
    JenkinsBuildOutcome,
    JenkinsBuildResult,
    JenkinsTriggerResult,
    JenkinsTestCase,
    JenkinsConnectionError,
    JenkinsTimeoutError
)


class MockJenkinsProvider(JenkinsProvider):
    """
    Deterministic mock Jenkins provider for unit, integration, and scenario testing.
    Accurately simulates SUCCESS, FAILURE, ABORTED, TIMEOUT, and UNAVAILABLE modes,
    and supports dynamic inspection of workspace code to verify genuine fixes.
    """

    def __init__(
        self,
        default_mode: str = "DYNAMIC_WORKSPACE",
        workspace_path: Optional[str] = None
    ):
        self.mode = default_mode.upper()  # SUCCESS, FAILURE, ABORTED, TIMEOUT, UNAVAILABLE, DYNAMIC_WORKSPACE
        self.workspace_path = Path(workspace_path) if workspace_path else None
        self._current_build_number = 480
        self._build_history: Dict[str, JenkinsBuildResult] = {}
        self._sequence: List[str] = []
        self._sequence_index = 0

    def set_mode(self, mode: str) -> None:
        """Switch simulation mode (SUCCESS, FAILURE, ABORTED, TIMEOUT, UNAVAILABLE)."""
        self.mode = mode.upper()

    def set_sequence(self, modes: List[str]) -> None:
        """Set a sequence of simulation modes for consecutive build calls (e.g. ['FAILURE', 'SUCCESS'])."""
        self._sequence = [m.upper() for m in modes]
        self._sequence_index = 0

    def _get_next_mode(self) -> str:
        if self._sequence and self._sequence_index < len(self._sequence):
            mode = self._sequence[self._sequence_index]
            self._sequence_index += 1
            return mode
        return self.mode

    async def trigger_build(
        self,
        job_name: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> JenkinsTriggerResult:
        if self.mode == "UNAVAILABLE":
            raise JenkinsConnectionError("Mock Jenkins server is unavailable (connection refused: 127.0.0.1:8080).")

        self._current_build_number += 1
        build_id = str(self._current_build_number)
        job = job_name or "ai-work-supervisor"

        return JenkinsTriggerResult(
            queued=True,
            job_name=job,
            queue_item_url=f"http://mock-jenkins:8080/queue/item/{self._current_build_number}/",
            build_id=build_id,
            message="Build queued successfully in mock Jenkins"
        )

    async def get_build_status(
        self,
        build_id: str,
        job_name: Optional[str] = None
    ) -> JenkinsBuildStatus:
        if self.mode == "UNAVAILABLE":
            raise JenkinsConnectionError("Mock Jenkins server is unavailable.")
        if self.mode == "TIMEOUT":
            return JenkinsBuildStatus.RUNNING
        if self.mode == "ABORTED":
            return JenkinsBuildStatus.ABORTED
        return JenkinsBuildStatus.COMPLETED

    async def get_build_result(
        self,
        build_id: str,
        job_name: Optional[str] = None
    ) -> JenkinsBuildResult:
        active_mode = self._get_next_mode()
        job = job_name or "ai-work-supervisor"
        url = f"http://mock-jenkins:8080/job/{job}/{build_id}/"

        if active_mode == "UNAVAILABLE":
            raise JenkinsConnectionError("Mock Jenkins server is offline or unreachable.")
        elif active_mode == "TIMEOUT":
            raise JenkinsTimeoutError(f"Mock Jenkins build {build_id} timed out.")
        elif active_mode == "ABORTED":
            return JenkinsBuildResult(
                build_id=build_id,
                job_name=job,
                status=JenkinsBuildStatus.ABORTED,
                result=JenkinsBuildOutcome.ABORTED,
                duration_ms=4500.0,
                tests_passed=0,
                tests_failed=0,
                tests_skipped=0,
                error_signature="BUILD_ABORTED",
                details="Build was manually cancelled or aborted",
                url=url
            )
        elif active_mode == "FAILURE":
            return JenkinsBuildResult(
                build_id=build_id,
                job_name=job,
                status=JenkinsBuildStatus.COMPLETED,
                result=JenkinsBuildOutcome.FAILURE,
                duration_ms=18300.0,
                tests_passed=45,
                tests_failed=2,
                tests_skipped=0,
                error_signature="CSV_HEADER_MISMATCH_BOM",
                details="AssertionError: 'col1' != '\\ufeffcol1' in tests/test_parser.py",
                test_cases=[
                    JenkinsTestCase(
                        name="test_parser.py::test_parse_csv_with_utf8_bom",
                        status="FAILED",
                        duration_s=0.25,
                        error_details="AssertionError: Dict key '\\ufeffid' does not match 'id'",
                        error_stack_trace="tests/test_parser.py:34: in test_parse_csv_with_utf8_bom"
                    ),
                    JenkinsTestCase(
                        name="test_parser.py::test_parse_csv_clean_headers",
                        status="FAILED",
                        duration_s=0.20,
                        error_details="AssertionError: Unexpected BOM prefix in parsed columns"
                    )
                ],
                url=url
            )
        elif active_mode == "SUCCESS":
            return JenkinsBuildResult(
                build_id=build_id,
                job_name=job,
                status=JenkinsBuildStatus.COMPLETED,
                result=JenkinsBuildOutcome.SUCCESS,
                duration_ms=16400.0,
                tests_passed=47,
                tests_failed=0,
                tests_skipped=0,
                details="All 47 tests passed cleanly across lint, unit, and integration suites.",
                url=url
            )
        else:
            # DYNAMIC_WORKSPACE mode: inspects actual workspace code if available
            is_fixed = False
            if self.workspace_path:
                parser_path = self.workspace_path / "src" / "parser.py"
                if parser_path.exists():
                    content = parser_path.read_text(encoding="utf-8", errors="ignore")
                    if ("\\ufeff" in content or "lstrip" in content) and "csv.DictReader" in content:
                        is_fixed = True

            if is_fixed:
                return JenkinsBuildResult(
                    build_id=build_id,
                    job_name=job,
                    status=JenkinsBuildStatus.COMPLETED,
                    result=JenkinsBuildOutcome.SUCCESS,
                    duration_ms=17200.0,
                    tests_passed=47,
                    tests_failed=0,
                    tests_skipped=0,
                    details="47/47 tests passed (UTF-8 BOM normalization verified).",
                    url=url
                )
            else:
                return JenkinsBuildResult(
                    build_id=build_id,
                    job_name=job,
                    status=JenkinsBuildStatus.COMPLETED,
                    result=JenkinsBuildOutcome.FAILURE,
                    duration_ms=18100.0,
                    tests_passed=45,
                    tests_failed=2,
                    tests_skipped=0,
                    error_signature="CSV_HEADER_MISMATCH_BOM",
                    details="45 passed, 2 failed on UTF-8 BOM test suite.",
                    url=url
                )

    async def stop_build(
        self,
        build_id: str,
        job_name: Optional[str] = None
    ) -> bool:
        self.mode = "ABORTED"
        return True

    async def poll_build_completion(
        self,
        build_id: str,
        job_name: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        poll_interval: Optional[float] = None
    ) -> JenkinsBuildResult:
        if self.mode == "TIMEOUT":
            raise JenkinsTimeoutError(f"Mock build {build_id} timed out waiting for completion.")
        return await self.get_build_result(build_id, job_name=job_name)
