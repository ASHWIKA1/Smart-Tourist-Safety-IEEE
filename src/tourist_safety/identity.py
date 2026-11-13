"""W3C-inspired Digital Identity (DID / Verifiable Credential) and
permissioned ledger anchoring/verification module.

Implements:
- Off-chain personal credential storage (never placed on-chain)
- Canonical JSON serialization + SHA-256 hashing (paper Eq. 1)
- Asymmetric Ed25519 issuer digital signatures (tamper & rogue-issuer resistance)
- Permissioned ledger simulation (hash-chained immutable blocks with DID,
  credential hash, issuer DID, expiry, revocation status, and audit trail)
- Nonce/challenge replay detection for presented credentials
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import BaseModel, Field


def canonicalize_json(payload: dict[str, Any]) -> bytes:
    """Deterministic canonical JSON serialization (sorted keys, no whitespace)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class TouristCredentialSubject(BaseModel):
    did: str
    full_name: str
    nationality: str
    passport_or_id_number: str
    emergency_contact_name: str
    emergency_contact_phone: str


class VerifiableCredential(BaseModel):
    credential_id: str
    context: list[str] = Field(
        default_factory=lambda: ["https://www.w3.org/2018/credentials/v1"]
    )
    type: list[str] = Field(
        default_factory=lambda: ["VerifiableCredential", "TouristSafetyCredential"]
    )
    issuer_did: str
    issuance_date: datetime
    expiration_date: datetime
    credential_subject: TouristCredentialSubject
    proof_signature_b64: str = ""

    def canonical_body_bytes(self) -> bytes:
        body = self.model_dump(mode="json", exclude={"proof_signature_b64"})
        return canonicalize_json(body)

    def content_hash(self) -> str:
        return sha256_hex(self.canonical_body_bytes())


@dataclass
class LedgerRecord:
    did: str
    credential_id: str
    credential_hash: str
    issuer_did: str
    issued_at: datetime
    expires_at: datetime
    revoked: bool = False
    revoked_at: Optional[datetime] = None
    revocation_reason: Optional[str] = None


@dataclass
class LedgerBlock:
    index: int
    timestamp: datetime
    tx_type: str
    payload: dict[str, Any]
    prev_hash: str
    block_hash: str = ""


@dataclass
class VerificationResult:
    valid: bool
    reason: str
    did: str
    credential_id: str
    hash_match: bool
    signature_valid: bool
    issuer_trusted: bool
    not_expired: bool
    not_revoked: bool
    not_replayed: bool
    latency_ms: float


class PermissionedIdentityLedger:
    """Simulated permissioned blockchain ledger for credential anchoring & audit."""

    def __init__(self) -> None:
        self._trusted_issuers: dict[str, Ed25519PublicKey] = {}
        self._records: dict[str, LedgerRecord] = {}  # credential_id -> LedgerRecord
        self._blocks: list[LedgerBlock] = []
        self._seen_nonces: set[str] = set()
        self._append_block("GENESIS", {"note": "Tourist Safety Permissioned Ledger"})

    def _append_block(self, tx_type: str, payload: dict[str, Any]) -> LedgerBlock:
        prev_hash = self._blocks[-1].block_hash if self._blocks else "0" * 64
        idx = len(self._blocks)
        ts = datetime.now(timezone.utc)
        block_body = canonicalize_json(
            {
                "index": idx,
                "timestamp": ts.isoformat(),
                "tx_type": tx_type,
                "payload": payload,
                "prev_hash": prev_hash,
            }
        )
        block = LedgerBlock(
            index=idx,
            timestamp=ts,
            tx_type=tx_type,
            payload=payload,
            prev_hash=prev_hash,
            block_hash=sha256_hex(block_body),
        )
        self._blocks.append(block)
        return block

    def register_trusted_issuer(
        self, issuer_did: str, public_key: Ed25519PublicKey
    ) -> None:
        self._trusted_issuers[issuer_did] = public_key
        self._append_block("REGISTER_ISSUER", {"issuer_did": issuer_did})

    def anchor_credential(self, record: LedgerRecord) -> LedgerBlock:
        self._records[record.credential_id] = record
        return self._append_block(
            "ANCHOR_CREDENTIAL",
            {
                "did": record.did,
                "credential_id": record.credential_id,
                "credential_hash": record.credential_hash,
                "issuer_did": record.issuer_did,
                "expires_at": record.expires_at.isoformat(),
            },
        )

    def revoke_credential(
        self,
        credential_id: str,
        reason: str = "revoked_by_authority",
        revoked_at: Optional[datetime] = None,
    ) -> None:
        if credential_id not in self._records:
            raise KeyError(f"Credential {credential_id} not anchored on ledger.")
        rec = self._records[credential_id]
        rec.revoked = True
        rec.revoked_at = revoked_at or datetime.now(timezone.utc)
        rec.revocation_reason = reason
        self._append_block(
            "REVOKE_CREDENTIAL",
            {
                "credential_id": credential_id,
                "did": rec.did,
                "reason": reason,
            },
        )

    def get_record(self, credential_id: str) -> Optional[LedgerRecord]:
        return self._records.get(credential_id)

    def get_trusted_issuer_key(self, issuer_did: str) -> Optional[Ed25519PublicKey]:
        return self._trusted_issuers.get(issuer_did)

    def chain_is_intact(self) -> bool:
        for i, block in enumerate(self._blocks):
            expected_prev = self._blocks[i - 1].block_hash if i > 0 else "0" * 64
            if block.prev_hash != expected_prev:
                return False
            recomputed = sha256_hex(
                canonicalize_json(
                    {
                        "index": block.index,
                        "timestamp": block.timestamp.isoformat(),
                        "tx_type": block.tx_type,
                        "payload": block.payload,
                        "prev_hash": block.prev_hash,
                    }
                )
            )
            if recomputed != block.block_hash:
                return False
        return True

    def block_count(self) -> int:
        return len(self._blocks)

    def mark_presentation_nonce(self, nonce: str) -> bool:
        """Record presentation nonce. Returns False if already seen (replay)."""
        if nonce in self._seen_nonces:
            return False
        self._seen_nonces.add(nonce)
        return True


class CredentialIssuer:
    """Authorized tourism identity verifier and Ed25519 credential issuer."""

    def __init__(self, issuer_did: str = "did:tourist:authority:in-tn-01") -> None:
        self.issuer_did = issuer_did
        self._private_key = Ed25519PrivateKey.generate()
        self.public_key = self._private_key.public_key()

    def register_on_ledger(self, ledger: PermissionedIdentityLedger) -> None:
        ledger.register_trusted_issuer(self.issuer_did, self.public_key)

    def issue_credential(
        self,
        ledger: PermissionedIdentityLedger,
        full_name: str,
        nationality: str,
        passport_or_id_number: str,
        emergency_contact_name: str,
        emergency_contact_phone: str,
        validity_days: int = 30,
        now: Optional[datetime] = None,
    ) -> VerifiableCredential:
        issued_at = now or datetime.now(timezone.utc)
        expires_at = issued_at + timedelta(days=validity_days)
        did = f"did:tourist:{uuid.uuid4().hex[:16]}"
        cred_id = f"vc:tourist:{uuid.uuid4().hex[:16]}"

        subject = TouristCredentialSubject(
            did=did,
            full_name=full_name,
            nationality=nationality,
            passport_or_id_number=passport_or_id_number,
            emergency_contact_name=emergency_contact_name,
            emergency_contact_phone=emergency_contact_phone,
        )
        vc = VerifiableCredential(
            credential_id=cred_id,
            issuer_did=self.issuer_did,
            issuance_date=issued_at,
            expiration_date=expires_at,
            credential_subject=subject,
        )
        body_bytes = vc.canonical_body_bytes()
        signature = self._private_key.sign(body_bytes)
        vc.proof_signature_b64 = base64.b64encode(signature).decode("ascii")

        record = LedgerRecord(
            did=did,
            credential_id=cred_id,
            credential_hash=sha256_hex(body_bytes),
            issuer_did=self.issuer_did,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        ledger.anchor_credential(record)
        return vc


class CredentialVerifier:
    """Verifies presented Verifiable Credentials against the permissioned ledger."""

    def __init__(self, ledger: PermissionedIdentityLedger) -> None:
        self.ledger = ledger

    def verify(
        self,
        vc: VerifiableCredential,
        presentation_nonce: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> VerificationResult:
        import time

        t0 = time.perf_counter()
        check_time = now or datetime.now(timezone.utc)

        record = self.ledger.get_record(vc.credential_id)
        if record is None:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return VerificationResult(
                valid=False,
                reason="credential_not_anchored_on_ledger",
                did=vc.credential_subject.did,
                credential_id=vc.credential_id,
                hash_match=False,
                signature_valid=False,
                issuer_trusted=False,
                not_expired=False,
                not_revoked=False,
                not_replayed=True,
                latency_ms=latency_ms,
            )

        body_bytes = vc.canonical_body_bytes()
        presented_hash = sha256_hex(body_bytes)
        hash_match = presented_hash == record.credential_hash

        issuer_key = self.ledger.get_trusted_issuer_key(vc.issuer_did)
        issuer_trusted = issuer_key is not None and vc.issuer_did == record.issuer_did

        signature_valid = False
        if issuer_key is not None and vc.proof_signature_b64:
            try:
                sig_bytes = base64.b64decode(vc.proof_signature_b64.encode("ascii"))
                issuer_key.verify(sig_bytes, body_bytes)
                signature_valid = True
            except (InvalidSignature, ValueError):
                signature_valid = False

        not_expired = check_time <= vc.expiration_date and check_time <= record.expires_at
        not_revoked = not record.revoked

        not_replayed = True
        if presentation_nonce is not None:
            not_replayed = self.ledger.mark_presentation_nonce(presentation_nonce)

        valid = (
            hash_match
            and issuer_trusted
            and signature_valid
            and not_expired
            and not_revoked
            and not_replayed
        )

        if valid:
            reason = "verified"
        elif not issuer_trusted:
            reason = "untrusted_issuer"
        elif not signature_valid:
            reason = "invalid_issuer_signature"
        elif not hash_match:
            reason = "credential_hash_mismatch_tampered"
        elif not not_revoked:
            reason = "credential_revoked"
        elif not not_expired:
            reason = "credential_expired"
        else:
            reason = "credential_presentation_replayed"

        latency_ms = (time.perf_counter() - t0) * 1000.0
        return VerificationResult(
            valid=valid,
            reason=reason,
            did=vc.credential_subject.did,
            credential_id=vc.credential_id,
            hash_match=hash_match,
            signature_valid=signature_valid,
            issuer_trusted=issuer_trusted,
            not_expired=not_expired,
            not_revoked=not_revoked,
            not_replayed=not_replayed,
            latency_ms=latency_ms,
        )
