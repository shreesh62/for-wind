"""Ch 33 — EvidenceRepository: queryable, indexed, signed evidence store.

Implements the append-only evidence repository described in FAS Ch 33.
Every EvidenceRecord is HMAC-SHA256 signed over its canonical JSON payload.
Records are indexed by goal_id and EvidenceKind for efficient querying.
There is NO update, NO delete — append-only enforced for audit integrity.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional

from friday.verification.evidence_law import (
    EvidenceArtifact,
    EvidenceKind,
    ExecutionEvidence,
    RequirementVerdict,
)


@dataclass(frozen=True)
class EvidenceRecord:
    """A single immutable evidence record in the repository.

    Fields are frozen to prevent mutation after creation.
    The signature covers all fields except itself.
    """

    record_id: str
    goal_id: str
    requirement: str
    artifact: EvidenceArtifact
    verdict_satisfied: Optional[bool]
    created_at: float
    signature: str


def _canonical_payload(record_id: str, goal_id: str, requirement: str,
                       artifact: EvidenceArtifact, verdict_satisfied: Optional[bool],
                       created_at: float) -> str:
    """Build the canonical JSON string for HMAC signing.

    Includes all record fields except the signature itself.
    Keys are sorted for deterministic output.
    """
    data = {
        "record_id": record_id,
        "goal_id": goal_id,
        "requirement": requirement,
        "artifact_kind": artifact.kind.value,
        "artifact_detail": artifact.detail,
        "artifact_value": artifact.value,
        "artifact_source": artifact.source,
        "verdict_satisfied": verdict_satisfied,
        "created_at": created_at,
    }
    return json.dumps(data, sort_keys=True)


def _sign(key: bytes, canonical: str) -> str:
    """Compute HMAC-SHA256 hex digest over the canonical payload."""
    return hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()


def _verify_record_signature(key: bytes, record: EvidenceRecord) -> bool:
    """Verify that a record's signature matches its contents."""
    canonical = _canonical_payload(
        record.record_id, record.goal_id, record.requirement,
        record.artifact, record.verdict_satisfied, record.created_at,
    )
    expected = _sign(key, canonical)
    return hmac.compare_digest(record.signature, expected)


class EvidenceRepository:
    """Queryable, indexed, signed store of evidence artifacts and verdicts.

    Ch 33 — Makes evidence auditable after the fact and tamper-evident.
    Append-only: no update or delete API exists.

    Indices:
        _by_goal[goal_id] -> list of indices in _records
        _by_kind[EvidenceKind] -> list of indices in _records
    """

    def __init__(self, signing_key: bytes = b"friday-evidence-default-key") -> None:
        self._signing_key = signing_key
        self._records: List[EvidenceRecord] = []
        self._by_goal: Dict[str, List[int]] = {}
        self._by_kind: Dict[EvidenceKind, List[int]] = {}

    def _append(self, record: EvidenceRecord) -> None:
        """Append a record and update indices."""
        idx = len(self._records)
        self._records.append(record)

        # Index by goal_id
        if record.goal_id not in self._by_goal:
            self._by_goal[record.goal_id] = []
        self._by_goal[record.goal_id].append(idx)

        # Index by artifact kind
        kind = record.artifact.kind
        if kind not in self._by_kind:
            self._by_kind[kind] = []
        self._by_kind[kind].append(idx)

    def _create_record(self, goal_id: str, artifact: EvidenceArtifact,
                       requirement: str = "",
                       verdict_satisfied: Optional[bool] = None) -> EvidenceRecord:
        """Create a signed EvidenceRecord."""
        record_id = str(uuid.uuid4())
        created_at = time.time()
        canonical = _canonical_payload(
            record_id, goal_id, requirement, artifact, verdict_satisfied, created_at,
        )
        signature = _sign(self._signing_key, canonical)
        return EvidenceRecord(
            record_id=record_id,
            goal_id=goal_id,
            requirement=requirement,
            artifact=artifact,
            verdict_satisfied=verdict_satisfied,
            created_at=created_at,
            signature=signature,
        )

    def add_artifact(self, goal_id: str, artifact: EvidenceArtifact,
                     requirement: str = "") -> str:
        """Append a raw evidence artifact (no verdict yet).

        Returns the record_id of the appended record.
        """
        record = self._create_record(goal_id, artifact, requirement, verdict_satisfied=None)
        self._append(record)
        return record.record_id

    def add_verdict(self, goal_id: str, verdict: RequirementVerdict) -> str:
        """Append a verdict record derived from a RequirementVerdict.

        Creates an EvidenceArtifact from the verdict's fields and stores
        the satisfied status. Returns the record_id.
        """
        # Map the verdict kind to an appropriate EvidenceKind
        kind_map = {
            "gather": EvidenceKind.GATHERED_INFO,
            "produce": EvidenceKind.GENERATED_CONTENT,
            "file": EvidenceKind.FILE_ARTIFACT,
            "navigate": EvidenceKind.NAVIGATION,
            "deliver": EvidenceKind.DELIVERY_CONFIRMATION,
            "generic": EvidenceKind.GATHERED_INFO,
        }
        evidence_kind = kind_map.get(verdict.kind.value, EvidenceKind.GATHERED_INFO)

        artifact = EvidenceArtifact(
            kind=evidence_kind,
            detail=verdict.evidence_detail or verdict.reason or "",
            value=0,
            source="verdict",
        )

        record = self._create_record(
            goal_id, artifact,
            requirement=verdict.description,
            verdict_satisfied=verdict.satisfied,
        )
        self._append(record)
        return record.record_id

    def query(self, goal_id: Optional[str] = None,
              kind: Optional[EvidenceKind] = None) -> List[EvidenceRecord]:
        """Return records matching the given filters (AND logic).

        If both goal_id and kind are specified, returns the intersection.
        If neither is specified, returns all records.
        """
        if goal_id is not None and kind is not None:
            # Intersection of both indices
            goal_indices = set(self._by_goal.get(goal_id, []))
            kind_indices = set(self._by_kind.get(kind, []))
            indices = sorted(goal_indices & kind_indices)
            return [self._records[i] for i in indices]

        if goal_id is not None:
            indices = self._by_goal.get(goal_id, [])
            return [self._records[i] for i in indices]

        if kind is not None:
            indices = self._by_kind.get(kind, [])
            return [self._records[i] for i in indices]

        # No filters — return all
        return list(self._records)

    def for_goal(self, goal_id: str) -> ExecutionEvidence:
        """Reconstruct an ExecutionEvidence from all valid artifacts for a goal.

        Only records that pass signature verification are included.
        Verdict-only records (verdict_satisfied is not None without real artifact
        value) are included as-is — they still carry an artifact.
        """
        evidence = ExecutionEvidence()
        indices = self._by_goal.get(goal_id, [])
        for idx in indices:
            record = self._records[idx]
            if _verify_record_signature(self._signing_key, record):
                evidence.add(record.artifact)
        return evidence

    def verify_integrity(self) -> bool:
        """Validate all HMAC signatures in the repository.

        Returns True if every record's signature is valid, False otherwise.
        """
        for record in self._records:
            if not _verify_record_signature(self._signing_key, record):
                return False
        return True
