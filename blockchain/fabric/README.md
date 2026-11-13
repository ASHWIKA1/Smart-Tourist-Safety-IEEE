# Hyperledger Fabric Chaincode (Module 5)

`chaincode/index.js` implements `TouristIdentityContract` using `fabric-contract-api` for a permissioned Hyperledger Fabric network:

- `RegisterTrustedIssuer(issuerDid, ed25519PublicKeyB64)`
- `AnchorCredential(credentialId, did, credentialHash, issuerDid, issuedAt, expiresAt)`
- `RevokeCredential(credentialId, reason, revokedAt)`
- `GetCredentialRecord(credentialId)`
- `VerifyCredentialAnchor(credentialId, presentedHash, currentIsoTime)`

All Personal Identifiable Information (PII) and full Verifiable Credentials stay off-chain in `credentials_offchain` (PostgreSQL/SQLite), while only the DID, SHA-256 hash, issuer DID, validity window, and revocation status are anchored on-chain.

For local development and reproducible CI/IEEE tests without a Docker Fabric network, `src/tourist_safety/identity.py` provides the identical state-machine semantics via `PermissionedIdentityLedger` (hash-chained immutable blocks + Ed25519 signature + replay nonce enforcement).
