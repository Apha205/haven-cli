/**
 * Access Control Provider — Strangler Pattern Abstraction
 *
 * Defines the stable interface that both Lit Protocol and TACo must implement.
 * Provider selection is controlled by the HAVEN_ACCESS_CONTROL_PROVIDER env var.
 *
 * Supported values:
 *   HAVEN_ACCESS_CONTROL_PROVIDER=lit   (default)
 *   HAVEN_ACCESS_CONTROL_PROVIDER=taco
 *
 * The bridge API (lit.connect, lit.encryptFile, etc.) is unchanged.
 * main.ts forwards all lit.* calls to whichever provider is active.
 */

import type { LitConnectResult, LitEncryptFileResult, LitDecryptFileResult, LitEncryptCidResult } from './types.ts';
import type { ProgressCallback } from './lit-wrapper.ts';

// ── Provider Interface ────────────────────────────────────────────────────────

/**
 * Stable interface for access control providers.
 * Both Lit Protocol and TACo implement this.
 * The method signatures match the existing lit.* bridge API exactly.
 */
export interface AccessControlProvider {
  readonly isConnected: boolean;
  connect(params: Record<string, unknown>): Promise<LitConnectResult>;
  disconnect(): Promise<void>;
  encryptFile(params: Record<string, unknown>, onProgress?: ProgressCallback): Promise<LitEncryptFileResult>;
  decryptFile(params: Record<string, unknown>, onProgress?: ProgressCallback): Promise<LitDecryptFileResult>;
  encryptCid(params: Record<string, unknown>): Promise<LitEncryptCidResult>;
}

// ── Factory ───────────────────────────────────────────────────────────────────

// Deno type declaration
declare const Deno: { env: { get(key: string): string | undefined } };

/**
 * Create the active access control provider.
 * Reads HAVEN_ACCESS_CONTROL_PROVIDER env var (default: 'lit').
 */
export async function createAccessControlProvider(): Promise<AccessControlProvider> {
  // Check both env var names (with and without HAVEN_ prefix)
  const providerName = (
    Deno.env.get('HAVEN_ACCESS_CONTROL_PROVIDER') ??
    Deno.env.get('ACCESS_CONTROL_PROVIDER') ??
    'lit'
  ).toLowerCase();

  // IMPORTANT: taco-wrapper.ts uses createRequire (Node.js CJS) and loads
  // @nucypher/nucypher-core (native WASM) which is incompatible with Deno.
  // When running under Deno (Synapse bridge), we must NEVER import taco-wrapper.ts.
  // TACo operations are handled by taco-node.mjs running under Node.js instead.
  if (providerName === 'taco') {
    // Check if we're running under Deno — if so, skip TACo (handled by Node.js bridge)
    // The Synapse bridge sets ACCESS_CONTROL_PROVIDER='' so this branch won't be reached.
    // But as a safety net, check if createRequire is available (Node.js only).
    try {
      const { createTacoProvider } = await import('./taco-wrapper.ts');
      console.error(`[access-control] Using TACo provider`);
      return createTacoProvider();
    } catch (e) {
      console.error(`[access-control] TACo provider failed to load (Deno incompatibility): ${e}`);
      console.error(`[access-control] Falling back to Lit Protocol`);
    }
  }

  // Default: Lit Protocol
  const { createLitWrapper } = await import('./lit-wrapper.ts');
  console.error(`[access-control] Using Lit Protocol provider`);
  return createLitWrapper();
}
