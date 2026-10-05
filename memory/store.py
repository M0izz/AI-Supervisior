"""
Shared Project Memory Store (Phase 7).
Provides local-first, SQLite-backed, provenance-aware persistent memory across
agents, tasks, handoffs, watchdogs, and independent verification.
"""

import asyncio
from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from core.events.bus import EventBus
from core.events.schema import Event, EventType
from memory.models import (
    FactStatus,
    MemoryProvenance,
    MemoryQuery,
    MemoryRecord,
    MemoryStatus,
    MemoryType,
    ProjectMemoryContext,
    sanitize_text,
)
from storage.sqlite.repositories import MemoryRepository

logger = logging.getLogger("supervisor.memory.store")


def _normalize_content(text: str) -> str:
    """Normalize text for deterministic deduplication."""
    lowered = text.lower().strip()
    # Strip common punctuation and collapse spaces
    cleaned = re.sub(r'[^\w\s]', '', lowered)
    return re.sub(r'\s+', ' ', cleaned).strip()


class MemoryStore:
    """
    Authoritative local memory store with provenance tracking,
    strict project scoping, deterministic deduplication, and SQLite WAL persistence.
    """

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        repository: Optional[MemoryRepository] = None,
    ):
        self._records: Dict[str, MemoryRecord] = {}
        self._lock = asyncio.Lock()
        self.event_bus = event_bus
        self.repository = repository
        # Dedup index: (project_or_mission, memory_type, normalized_content) -> record_id
        self._dedup_index: Dict[Tuple[str, str, str], str] = {}

    async def add_record(
        self,
        mission_id: str,
        fact: str,
        source: str = "system_observation",
        created_by: str = "system",
        status: MemoryStatus = MemoryStatus.OBSERVED,
        confidence: float = 1.0,
        category: str = "fact",
        details: Optional[str] = None,
        project_id: str = "",
        task_id: Optional[str] = None,
        memory_type: MemoryType = MemoryType.FACT,
        source_id: str = "",
        evidence: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        superseded_by: Optional[str] = None,
        record_id: Optional[str] = None,
    ) -> MemoryRecord:
        """
        Add or update a memory record with full provenance and deterministic deduplication.
        """
        clean_fact = sanitize_text(fact)
        clean_details = sanitize_text(details) if details else None
        provenance = MemoryProvenance(
            source=source,
            source_id=source_id,
            created_by=created_by,
            evidence=evidence or [],
        )

        scope_key = project_id if project_id else mission_id
        normalized = _normalize_content(clean_fact)
        dedup_key = (scope_key, normalized)

        async with self._lock:
            existing_id = self._dedup_index.get(dedup_key)
            if existing_id and existing_id in self._records:
                existing_record = self._records[existing_id]

                # If the new record represents higher epistemic status (e.g. UNVERIFIED -> VERIFIED, or disproven -> REJECTED),
                # promote the existing record and preserve provenance.
                if self._should_promote(existing_record.status, status) or status == MemoryStatus.REJECTED:
                    old_status = existing_record.status
                    existing_record.status = status
                    existing_record.memory_type = memory_type
                    existing_record.confidence = max(existing_record.confidence, confidence)
                    existing_record.provenance = provenance
                    if clean_details:
                        existing_record.details = clean_details
                    existing_record.updated_at = datetime.now(timezone.utc)
                    if metadata:
                        existing_record.metadata.update(metadata)

                    if self.repository:
                        await self._persist_to_repo(existing_record)

                    if self.event_bus:
                        await self.event_bus.publish(
                            Event(
                                mission_id=mission_id,
                                task_id=task_id,
                                type=EventType.MEMORY_UPDATED,
                                payload={
                                    "record_id": existing_record.id,
                                    "action": "promoted",
                                    "old_status": old_status.value,
                                    "new_status": status.value,
                                    "fact": existing_record.content,
                                    "promoted_by": created_by,
                                },
                            )
                        )
                    return existing_record

                # If existing is already equal or higher status, return deduplicated record
                return existing_record

            # Create brand new record
            record = MemoryRecord(
                id=record_id or f"mem_{len(self._records) + 1}_{datetime.now(timezone.utc).strftime('%H%M%S%f')[:10]}",
                project_id=project_id,
                mission_id=mission_id,
                task_id=task_id,
                content=clean_fact,
                memory_type=memory_type,
                status=status,
                confidence=confidence,
                provenance=provenance,
                category=category,
                details=clean_details,
                metadata=metadata or {},
                superseded_by=superseded_by,
            )

            self._records[record.id] = record
            self._dedup_index[dedup_key] = record.id

            if self.repository:
                await self._persist_to_repo(record)

        # Publish memory updated event
        if self.event_bus:
            await self.event_bus.publish(
                Event(
                    mission_id=mission_id,
                    task_id=task_id,
                    type=EventType.MEMORY_UPDATED,
                    payload={
                        "record_id": record.id,
                        "project_id": record.project_id,
                        "fact": record.content,
                        "status": record.status.value,
                        "memory_type": record.memory_type.value,
                        "category": record.category,
                        "created_by": record.created_by,
                    },
                )
            )

        return record

    async def _persist_to_repo(self, record: MemoryRecord) -> None:
        """Helper to write record to SQLite repository."""
        if not self.repository:
            return
        try:
            await self.repository.save(
                record_id=record.id,
                project_id=record.project_id,
                mission_id=record.mission_id,
                task_id=record.task_id,
                category=record.category,
                content=record.content,
                memory_type=record.memory_type.value,
                status=record.status.value,
                confidence=record.confidence,
                source=record.provenance.source,
                source_id=record.provenance.source_id,
                created_by=record.provenance.created_by,
                superseded_by=record.superseded_by,
                metadata={
                    **record.metadata,
                    "details": record.details,
                    "evidence": record.provenance.evidence,
                },
                created_at=record.created_at.isoformat(),
                updated_at=record.updated_at.isoformat(),
            )
        except Exception as e:
            logger.warning(f"Error persisting memory record {record.id} to SQLite: {e}")

    @staticmethod
    def _should_promote(current: MemoryStatus, candidate: MemoryStatus) -> bool:
        """Determines if candidate status represents an epistemic upgrade."""
        hierarchy = {
            MemoryStatus.UNVERIFIED: 1,
            MemoryStatus.INFERRED: 2,
            MemoryStatus.OBSERVED: 3,
            MemoryStatus.DECIDED: 4,
            MemoryStatus.REJECTED: 5,
            MemoryStatus.VERIFIED: 6,
        }
        return hierarchy.get(candidate, 0) > hierarchy.get(current, 0)

    async def record_verified_fact(
        self,
        mission_id: str,
        content: str,
        source: str = "verification",
        source_id: str = "",
        created_by: str = "verifier",
        project_id: str = "",
        task_id: Optional[str] = None,
        evidence: Optional[List[str]] = None,
        details: Optional[str] = None,
    ) -> MemoryRecord:
        """Convenience method for creating or promoting an independently verified fact."""
        return await self.add_record(
            mission_id=mission_id,
            fact=content,
            source=source,
            created_by=created_by,
            status=MemoryStatus.VERIFIED,
            confidence=1.0,
            category="fact",
            project_id=project_id,
            task_id=task_id,
            memory_type=MemoryType.FACT,
            source_id=source_id,
            evidence=evidence or [],
            details=details,
        )

    async def record_unverified_claim(
        self,
        mission_id: str,
        content: str,
        source: str = "agent_event",
        source_id: str = "",
        created_by: str = "worker_agent",
        project_id: str = "",
        task_id: Optional[str] = None,
        details: Optional[str] = None,
    ) -> MemoryRecord:
        """Convenience method for storing an agent claim as strictly UNVERIFIED."""
        return await self.add_record(
            mission_id=mission_id,
            fact=content,
            source=source,
            created_by=created_by,
            status=MemoryStatus.UNVERIFIED,
            confidence=0.5,
            category="claim",
            project_id=project_id,
            task_id=task_id,
            memory_type=MemoryType.FACT,
            source_id=source_id,
            details=details,
        )

    async def record_rejected_approach(
        self,
        mission_id: str,
        content: str,
        source: str = "verification",
        source_id: str = "",
        created_by: str = "verifier",
        project_id: str = "",
        task_id: Optional[str] = None,
        details: Optional[str] = None,
        evidence: Optional[List[str]] = None,
    ) -> MemoryRecord:
        """Convenience method for registering a failed approach so no subsequent agent repeats it."""
        return await self.add_record(
            mission_id=mission_id,
            fact=content,
            source=source,
            created_by=created_by,
            status=MemoryStatus.REJECTED,
            confidence=1.0,
            category="rejected_approach",
            project_id=project_id,
            task_id=task_id,
            memory_type=MemoryType.REJECTED_APPROACH,
            source_id=source_id,
            details=details,
            evidence=evidence or [],
        )

    async def record_decision(
        self,
        mission_id: str,
        content: str,
        source: str = "system_observation",
        source_id: str = "",
        created_by: str = "supervisor",
        project_id: str = "",
        task_id: Optional[str] = None,
        details: Optional[str] = None,
    ) -> MemoryRecord:
        """Convenience method for registering an architectural or policy decision."""
        return await self.add_record(
            mission_id=mission_id,
            fact=content,
            source=source,
            created_by=created_by,
            status=MemoryStatus.DECIDED,
            confidence=1.0,
            category="decision",
            project_id=project_id,
            task_id=task_id,
            memory_type=MemoryType.DECISION,
            source_id=source_id,
            details=details,
        )

    async def get_by_mission(
        self,
        mission_id: str,
        category: Optional[str] = None,
        status: Optional[MemoryStatus] = None,
    ) -> List[MemoryRecord]:
        """Retrieve memory records belonging to a mission."""
        async with self._lock:
            # Sync from repository if memory store is empty or needs reload
            if not self._records and self.repository:
                await self._load_from_repository(mission_id=mission_id)

            records = [r for r in self._records.values() if r.mission_id == mission_id]
            if category:
                records = [r for r in records if r.category == category]
            if status:
                records = [r for r in records if r.status == status]
            return records

    async def get_by_project(
        self,
        project_id: str,
        memory_type: Optional[MemoryType] = None,
        status: Optional[MemoryStatus] = None,
    ) -> List[MemoryRecord]:
        """Retrieve memory records strictly scoped to a project."""
        async with self._lock:
            if not self._records and self.repository:
                await self._load_from_repository(project_id=project_id)

            records = [r for r in self._records.values() if r.project_id == project_id]
            if memory_type:
                records = [r for r in records if r.memory_type == memory_type]
            if status:
                records = [r for r in records if r.status == status]
            return records

    async def query(self, query: MemoryQuery) -> List[MemoryRecord]:
        """
        Deterministic, ranked query for scoped project memories.
        Enforces project boundary isolation and trust hierarchy scoring.
        """
        async with self._lock:
            # Reload from repository if in-memory cache is cold
            if not self._records and self.repository:
                await self._load_from_repository(
                    project_id=query.project_id,
                    mission_id=query.mission_id,
                )

            candidates: List[MemoryRecord] = []
            for r in self._records.values():
                # 1. Strict Project Isolation (Section 14)
                if query.project_id:
                    if r.project_id and r.project_id != query.project_id:
                        continue
                    # If record has no project_id, verify mission_id match if provided
                    if not r.project_id and query.mission_id and r.mission_id != query.mission_id:
                        continue

                # 2. Mission filter
                if query.mission_id and r.mission_id != query.mission_id:
                    continue

                # 3. Status filter
                if query.statuses and r.status not in query.statuses:
                    continue

                # 4. Memory type filter
                if query.memory_types and r.memory_type not in query.memory_types:
                    continue

                # 5. Supersession filter
                if query.exclude_superseded and r.superseded_by:
                    continue

                # 6. Source filter
                if query.sources and r.provenance.source not in query.sources:
                    continue

                candidates.append(r)

            # Deterministic Ranking
            scored: List[Tuple[float, MemoryRecord]] = []
            query_tokens = set()
            if query.keywords:
                for kw in query.keywords:
                    query_tokens.update(re.findall(r'\w+', kw.lower()))

            for cand in candidates:
                score = 0.0

                # A. Trust Hierarchy Weight (Section 17)
                trust_weights = {
                    MemoryStatus.VERIFIED: 5.0,
                    MemoryStatus.DECIDED: 4.0,
                    MemoryStatus.OBSERVED: 3.0,
                    MemoryStatus.INFERRED: 2.0,
                    MemoryStatus.UNVERIFIED: 1.0,
                    MemoryStatus.REJECTED: 0.5,
                }
                score += trust_weights.get(cand.status, 1.0)

                # B. Task Relevance Match
                if query.task_id and cand.task_id == query.task_id:
                    score += 3.0

                # C. Keyword Overlap
                if query_tokens:
                    cand_tokens = set(re.findall(r'\w+', cand.content.lower()))
                    if cand.details:
                        cand_tokens.update(re.findall(r'\w+', cand.details.lower()))
                    overlap = len(query_tokens.intersection(cand_tokens))
                    score += float(overlap) * 2.0

                # D. Confidence multiplier
                score *= cand.confidence

                scored.append((score, cand))

            # Deterministic sort: highest score first, then newest timestamp, then stable ID
            scored.sort(
                key=lambda item: (item[0], item[1].created_at.timestamp(), item[1].id),
                reverse=True,
            )

            return [item[1] for item in scored[:query.limit]]

    async def build_project_memory_context(
        self,
        mission_id: str,
        project_id: str = "",
        task_id: Optional[str] = None,
        task_objective: str = "",
        limit: int = 15,
    ) -> ProjectMemoryContext:
        """
        Generates a bounded, relevant ProjectMemoryContext package for an agent (Section 20).
        Categorizes items into verified facts, rejected approaches, decisions, constraints, and failures.
        """
        keywords = re.findall(r'\w+', task_objective.lower()) if task_objective else None

        records = await self.query(
            MemoryQuery(
                project_id=project_id if project_id else None,
                mission_id=mission_id,
                task_id=task_id,
                keywords=keywords,
                limit=limit * 2,
            )
        )

        facts: List[Dict[str, Any]] = []
        constraints: List[str] = []
        decisions: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []
        failures: List[Dict[str, Any]] = []
        verifications: List[Dict[str, Any]] = []

        for r in records:
            item = {
                "id": r.id,
                "fact": r.content,
                "status": r.status.value,
                "confidence": r.confidence,
                "source": r.provenance.source,
                "created_by": r.provenance.created_by,
                "details": r.details,
            }

            if r.status == MemoryStatus.REJECTED or r.memory_type == MemoryType.REJECTED_APPROACH:
                rejected.append({
                    "approach": r.content,
                    "reason": r.details or "Failed during verification",
                    "provenance": r.provenance.source,
                })
            elif r.memory_type == MemoryType.CONSTRAINT:
                constraints.append(r.content)
            elif r.memory_type == MemoryType.DECISION or r.status == MemoryStatus.DECIDED:
                decisions.append(item)
            elif r.memory_type == MemoryType.FAILURE:
                failures.append(item)
            elif r.memory_type == MemoryType.VERIFICATION_RESULT:
                verifications.append(item)
            else:
                # Active facts (VERIFIED, INFERRED, UNVERIFIED)
                facts.append(item)

        return ProjectMemoryContext(
            project_id=project_id,
            mission_id=mission_id,
            task_id=task_id,
            relevant_facts=facts[:limit],
            constraints=constraints[:limit],
            recent_decisions=decisions[:limit],
            rejected_approaches=rejected[:limit],
            relevant_failures=failures[:limit],
            verification_evidence=verifications[:limit],
        )

    async def get_structured_summary(self, mission_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """Provides categorized memory for Screen 05 (Memory Screen) and APIs."""
        all_records = await self.get_by_mission(mission_id)
        return {
            "verified_facts": [
                r.model_dump(mode="json") for r in all_records if r.status == MemoryStatus.VERIFIED
            ],
            "decisions": [
                r.model_dump(mode="json") for r in all_records if r.category == "decision" or r.memory_type == MemoryType.DECISION
            ],
            "rejected_approaches": [
                r.model_dump(mode="json")
                for r in all_records
                if r.status == MemoryStatus.REJECTED or r.category == "rejected_approach" or r.memory_type == MemoryType.REJECTED_APPROACH
            ],
            "known_issues": [
                r.model_dump(mode="json") for r in all_records if r.category == "known_issue" or r.memory_type == MemoryType.FAILURE
            ],
        }

    async def _load_from_repository(
        self,
        project_id: Optional[str] = None,
        mission_id: Optional[str] = None,
    ) -> None:
        """Populates in-memory cache from persistent SQLite WAL repository."""
        if not self.repository:
            return
        rows: List[Dict[str, Any]] = []
        if project_id:
            rows.extend(await self.repository.list_by_project(project_id))
        elif mission_id:
            rows.extend(await self.repository.list_by_mission(mission_id))

        for row in rows:
            rid = row.get("record_id", "")
            if rid and rid not in self._records:
                meta = row.get("metadata") or {}
                mem_type_str = row.get("memory_type", "FACT")
                try:
                    m_type = MemoryType(mem_type_str)
                except Exception:
                    m_type = MemoryType.FACT

                status_str = row.get("status", "OBSERVED")
                try:
                    m_status = MemoryStatus(status_str)
                except Exception:
                    m_status = MemoryStatus.OBSERVED

                prov = MemoryProvenance(
                    source=row.get("source", "system"),
                    source_id=row.get("source_id", ""),
                    created_by=row.get("created_by", "system"),
                    evidence=meta.get("evidence", []),
                )

                created_dt = datetime.fromisoformat(row["created_at"]) if "created_at" in row and row["created_at"] else datetime.now(timezone.utc)
                updated_dt = datetime.fromisoformat(row["updated_at"]) if "updated_at" in row and row["updated_at"] else created_dt

                rec = MemoryRecord(
                    id=rid,
                    project_id=row.get("project_id", ""),
                    mission_id=row.get("mission_id", ""),
                    task_id=row.get("task_id"),
                    content=row.get("content", ""),
                    memory_type=m_type,
                    status=m_status,
                    confidence=float(row.get("confidence", 1.0)),
                    provenance=prov,
                    category=row.get("category", "fact"),
                    details=meta.get("details"),
                    metadata=meta,
                    superseded_by=row.get("superseded_by"),
                    created_at=created_dt,
                    updated_at=updated_dt,
                )
                self._records[rid] = rec
                scope_key = rec.project_id if rec.project_id else rec.mission_id
                self._dedup_index[(scope_key, _normalize_content(rec.content))] = rid
