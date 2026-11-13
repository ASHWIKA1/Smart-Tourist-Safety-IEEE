import { useState } from "react";
import { fetchLedgerBlocks, revokeCredential, verifyCredential } from "../api";
import type { LedgerResponse, VerificationResult } from "../types";

interface CredentialPanelProps {
  token: string;
}

export function CredentialPanel({ token }: CredentialPanelProps) {
  const [vcJson, setVcJson] = useState("");
  const [nonce, setNonce] = useState("");
  const [result, setResult] = useState<VerificationResult | null>(null);
  const [revokeId, setRevokeId] = useState("");
  const [revokeReason, setRevokeReason] = useState("lost_device");
  const [ledger, setLedger] = useState<LedgerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  async function handleVerify(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setStatusMsg(null);
    try {
      const parsed = JSON.parse(vcJson);
      const res = await verifyCredential(token, parsed, nonce.trim() || undefined);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to verify credential");
    }
  }

  async function handleRevoke(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setStatusMsg(null);
    try {
      const res = await revokeCredential(token, revokeId.trim(), revokeReason);
      setStatusMsg(`Credential ${res.credential_id} revoked on permissioned ledger.`);
      setRevokeId("");
      const updated = await fetchLedgerBlocks(token);
      setLedger(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Revocation failed");
    }
  }

  async function handleLoadLedger() {
    setError(null);
    try {
      setLedger(await fetchLedgerBlocks(token));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load ledger");
    }
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Blockchain Credential Verification & Ledger Audit</h2>
        <button type="button" className="btn-secondary" onClick={handleLoadLedger}>
          Inspect Ledger Blocks
        </button>
      </div>

      {error && <p className="alert-error">{error}</p>}
      {statusMsg && <p className="alert-ok">{statusMsg}</p>}

      <div className="two-col">
        <form onSubmit={handleVerify} className="stack">
          <label htmlFor="vc-input">Presented Verifiable Credential (JSON)</label>
          <textarea
            id="vc-input"
            rows={6}
            placeholder='Paste JSON from /api/v1/credentials/issue or /credentials/me'
            value={vcJson}
            onChange={(e) => setVcJson(e.target.value)}
            required
          />
          <label htmlFor="vc-nonce">Presentation Challenge Nonce (optional replay check)</label>
          <input
            id="vc-nonce"
            type="text"
            placeholder="e.g. gate-check-001"
            value={nonce}
            onChange={(e) => setNonce(e.target.value)}
          />
          <button type="submit" className="btn-primary">
            Verify Signature, Hash & Ledger Status
          </button>
        </form>

        <div className="stack">
          {result && (
            <div className={`verify-card ${result.valid ? "valid" : "invalid"}`}>
              <strong>{result.valid ? "VERIFIED" : "REJECTED"}</strong> — {result.reason}
              <ul>
                <li>DID: <code>{result.did}</code></li>
                <li>SHA-256 Hash Match: {String(result.hash_match)}</li>
                <li>Ed25519 Signature Valid: {String(result.signature_valid)}</li>
                <li>Trusted Issuer: {String(result.issuer_trusted)}</li>
                <li>Not Expired: {String(result.not_expired)}</li>
                <li>Not Revoked: {String(result.not_revoked)}</li>
                <li>Not Replayed: {String(result.not_replayed)}</li>
                <li>Latency: {result.latency_ms} ms</li>
              </ul>
            </div>
          )}

          <form onSubmit={handleRevoke} className="stack revoke-box">
            <h3>Revoke Credential</h3>
            <input
              type="text"
              placeholder="Credential ID (e.g. vc:tourist:...)"
              value={revokeId}
              onChange={(e) => setRevokeId(e.target.value)}
              required
            />
            <input
              type="text"
              placeholder="Revocation reason"
              value={revokeReason}
              onChange={(e) => setRevokeReason(e.target.value)}
              required
            />
            <button type="submit" className="btn-danger">
              Revoke on Ledger
            </button>
          </form>
        </div>
      </div>

      {ledger && (
        <div className="ledger-box">
          <p>
            <strong>Blocks:</strong> {ledger.block_count} |{" "}
            <strong>Hash Chain Intact:</strong> {String(ledger.chain_intact)}
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Tx Type</th>
                  <th>Timestamp</th>
                  <th>Block Hash</th>
                </tr>
              </thead>
              <tbody>
                {ledger.blocks.slice(-8).reverse().map((b) => (
                  <tr key={b.index}>
                    <td>{b.index}</td>
                    <td>{b.tx_type}</td>
                    <td>{new Date(b.timestamp).toLocaleString()}</td>
                    <td><code>{b.block_hash.slice(0, 18)}...</code></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
