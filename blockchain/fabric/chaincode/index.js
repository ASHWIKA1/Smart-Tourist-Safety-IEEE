"use strict";

const { Contract } = require("fabric-contract-api");

/**
 * Hyperledger Fabric Smart Contract for Smart Tourist Safety Digital Identity.
 *
 * Privacy-by-design: Personal Identifiable Information (PII) and full
 * Verifiable Credentials stay off-chain. Only the DID, SHA-256 credential
 * hash, trusted issuer DID, validity window, and revocation state are stored
 * on the permissioned ledger.
 */
class TouristIdentityContract extends Contract {
  async InitLedger(ctx) {
    return JSON.stringify({ initialized: true });
  }

  async RegisterTrustedIssuer(ctx, issuerDid, ed25519PublicKeyB64) {
    if (!issuerDid || !ed25519PublicKeyB64) {
      throw new Error("issuerDid and ed25519PublicKeyB64 are required");
    }
    const key = ctx.stub.createCompositeKey("ISSUER", [issuerDid]);
    const record = {
      docType: "trustedIssuer",
      issuerDid,
      ed25519PublicKeyB64,
      registeredAt: new Date(ctx.stub.getTxTimestamp().seconds.low * 1000).toISOString(),
    };
    await ctx.stub.putState(key, Buffer.from(JSON.stringify(record)));
    return JSON.stringify(record);
  }

  async AnchorCredential(ctx, credentialId, did, credentialHash, issuerDid, issuedAt, expiresAt) {
    const issuerKey = ctx.stub.createCompositeKey("ISSUER", [issuerDid]);
    const issuerBytes = await ctx.stub.getState(issuerKey);
    if (!issuerBytes || issuerBytes.length === 0) {
      throw new Error(`Untrusted issuer: ${issuerDid}`);
    }

    const credKey = ctx.stub.createCompositeKey("CREDENTIAL", [credentialId]);
    const existing = await ctx.stub.getState(credKey);
    if (existing && existing.length > 0) {
      throw new Error(`Credential already anchored: ${credentialId}`);
    }

    const record = {
      docType: "credentialAnchor",
      credentialId,
      did,
      credentialHash,
      issuerDid,
      issuedAt,
      expiresAt,
      revoked: false,
      revokedAt: null,
      revocationReason: null,
      txId: ctx.stub.getTxID(),
    };
    await ctx.stub.putState(credKey, Buffer.from(JSON.stringify(record)));
    ctx.stub.setEvent(
      "CredentialAnchored",
      Buffer.from(JSON.stringify({ credentialId, did, issuerDid }))
    );
    return JSON.stringify(record);
  }

  async RevokeCredential(ctx, credentialId, reason, revokedAt) {
    const credKey = ctx.stub.createCompositeKey("CREDENTIAL", [credentialId]);
    const data = await ctx.stub.getState(credKey);
    if (!data || data.length === 0) {
      throw new Error(`Credential not found: ${credentialId}`);
    }
    const record = JSON.parse(data.toString());
    record.revoked = true;
    record.revokedAt = revokedAt;
    record.revocationReason = reason || "revoked_by_authority";

    await ctx.stub.putState(credKey, Buffer.from(JSON.stringify(record)));
    ctx.stub.setEvent(
      "CredentialRevoked",
      Buffer.from(JSON.stringify({ credentialId, reason: record.revocationReason }))
    );
    return JSON.stringify(record);
  }

  async GetCredentialRecord(ctx, credentialId) {
    const credKey = ctx.stub.createCompositeKey("CREDENTIAL", [credentialId]);
    const data = await ctx.stub.getState(credKey);
    if (!data || data.length === 0) {
      throw new Error(`Credential not found: ${credentialId}`);
    }
    return data.toString();
  }

  async VerifyCredentialAnchor(ctx, credentialId, presentedHash, currentIsoTime) {
    const credKey = ctx.stub.createCompositeKey("CREDENTIAL", [credentialId]);
    const data = await ctx.stub.getState(credKey);
    if (!data || data.length === 0) {
      return JSON.stringify({ valid: false, reason: "credential_not_anchored" });
    }
    const record = JSON.parse(data.toString());
    const hashMatch = record.credentialHash === presentedHash;
    const notRevoked = !record.revoked;
    const notExpired = Date.parse(currentIsoTime) <= Date.parse(record.expiresAt);
    const valid = hashMatch && notRevoked && notExpired;

    return JSON.stringify({
      valid,
      did: record.did,
      issuerDid: record.issuerDid,
      hashMatch,
      notRevoked,
      notExpired,
      txId: record.txId,
    });
  }
}

module.exports.TouristIdentityContract = TouristIdentityContract;
module.exports.contracts = [TouristIdentityContract];
