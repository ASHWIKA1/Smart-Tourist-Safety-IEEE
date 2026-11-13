"""Unit tests for Experiment C: Digital Identity security & ledger auditability."""

from datetime import datetime, timedelta, timezone

from tourist_safety.identity import (
    CredentialIssuer,
    CredentialVerifier,
    PermissionedIdentityLedger,
)


def _setup_ledger_and_vc():
    ledger = PermissionedIdentityLedger()
    issuer = CredentialIssuer("did:tourist:authority:tn-01")
    issuer.register_on_ledger(ledger)
    now = datetime(2026, 11, 12, 9, 0, 0, tzinfo=timezone.utc)
    vc = issuer.issue_credential(
        ledger=ledger,
        full_name="Ajay K",
        nationality="IN",
        passport_or_id_number="P99887766",
        emergency_contact_name="Geetha B",
        emergency_contact_phone="+91-9000000000",
        validity_days=10,
        now=now,
    )
    verifier = CredentialVerifier(ledger)
    return ledger, issuer, verifier, vc, now


def test_valid_credential_accepted_and_ledger_intact():
    ledger, _, verifier, vc, now = _setup_ledger_and_vc()
    res = verifier.verify(vc, presentation_nonce="nonce-1", now=now + timedelta(hours=1))
    assert res.valid is True
    assert res.reason == "verified"
    assert res.hash_match is True
    assert res.signature_valid is True
    assert ledger.chain_is_intact() is True


def test_modified_credential_rejected():
    _, _, verifier, vc, now = _setup_ledger_and_vc()
    tampered = vc.model_copy(deep=True)
    tampered.credential_subject.passport_or_id_number = "P00000000"
    res = verifier.verify(tampered, presentation_nonce="nonce-2", now=now)
    assert res.valid is False
    assert res.hash_match is False
    assert res.signature_valid is False


def test_expired_credential_rejected():
    _, _, verifier, vc, now = _setup_ledger_and_vc()
    res = verifier.verify(
        vc, presentation_nonce="nonce-3", now=now + timedelta(days=11)
    )
    assert res.valid is False
    assert res.not_expired is False
    assert res.reason == "credential_expired"


def test_revoked_credential_rejected():
    ledger, _, verifier, vc, now = _setup_ledger_and_vc()
    ledger.revoke_credential(vc.credential_id, reason="lost_device")
    res = verifier.verify(vc, presentation_nonce="nonce-4", now=now)
    assert res.valid is False
    assert res.not_revoked is False
    assert res.reason == "credential_revoked"


def test_rogue_issuer_signature_rejected():
    ledger, _, verifier, vc, now = _setup_ledger_and_vc()
    rogue = CredentialIssuer("did:tourist:authority:rogue")
    rogue_vc = rogue.issue_credential(
        ledger=PermissionedIdentityLedger(),  # not anchored on main ledger
        full_name="Mallory",
        nationality="XX",
        passport_or_id_number="X123",
        emergency_contact_name="Eve",
        emergency_contact_phone="+1-000",
        now=now,
    )
    res_unanchored = verifier.verify(rogue_vc, presentation_nonce="nonce-5", now=now)
    assert res_unanchored.valid is False

    # Also test forged signature on an anchored VC
    forged = vc.model_copy(deep=True)
    forged.proof_signature_b64 = "AAAA" + forged.proof_signature_b64[4:]
    res_bad_sig = verifier.verify(forged, presentation_nonce="nonce-6", now=now)
    assert res_bad_sig.valid is False
    assert res_bad_sig.signature_valid is False


def test_replayed_credential_presentation_rejected():
    _, _, verifier, vc, now = _setup_ledger_and_vc()
    first = verifier.verify(vc, presentation_nonce="nonce-replay-1", now=now)
    assert first.valid is True
    second = verifier.verify(vc, presentation_nonce="nonce-replay-1", now=now)
    assert second.valid is False
    assert second.not_replayed is False
    assert second.reason == "credential_presentation_replayed"
