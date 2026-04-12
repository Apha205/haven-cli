/**
 * TACo Access Control Provider
 *
 * Implements AccessControlProvider using TACo threshold encryption.
 * Drop-in replacement for Lit Protocol — same interface, same metadata schema.
 *
 * Key differences from Lit:
 * - Provider RPC: Polygon Amoy (TACo Coordinator) instead of Lit nodes
 * - Key wrapping: TACo threshold BLS instead of Lit BLS-IBE
 * - Auth: EIP-4361 SIWE via EIP4361AuthProvider instead of Lit AuthSig
 * - Condition format: TACo ContractCondition instead of Lit AccessControlCondition
 *
 * Metadata schema: reuses HybridEncryptionMetadata (hybrid-v1) with
 * encryptedKey = base64(TACo messageKit bytes) for backwards compat.
 *
 * Environment variables:
 *   HAVEN_PRIVATE_KEY or PRIVATE_KEY  — wallet private key
 *   TACO_DOMAIN                        — TACo domain (default: lynx)
 *   TACO_RITUAL_ID                     — ritual ID (default: 27)
 *   TACO_RPC_URL                       — Polygon Amoy RPC
 *   TACO_NFT_CONTRACT                  — ERC20/ERC721 contract for access condition
 *   TACO_NFT_CHAIN_ID                  — chain ID for condition (default: 11155111)
 *   TACO_TOKEN_TYPE                    — ERC20 or ERC721 (default: ERC20)
 */

import type { AccessControlProvider } from './access-control-provider.ts';
import type {
  LitConnectResult,
  LitEncryptFileResult,
  LitDecryptFileResult,
  LitEncryptCidResult,
  HybridEncryptionMetadata,
} from './types.ts';
import type { ProgressCallback } from './lit-wrapper.ts';

// Use createRequire to load TACo via CJS build.
// The TACo alpha packages have broken ES module builds (bare directory imports
// like `from './conditions'` that Deno's strict ESM resolver rejects).
// The CJS build works correctly — createRequire forces Node.js CJS resolution.
import { createRequire } from 'node:module';
const _require = createRequire(import.meta.url);

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const tacoSdk: any = _require('@nucypher/taco');
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const tacoAuth: any = _require('@nucypher/taco-auth');
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const nucypherCore: any = _require('@nucypher/nucypher-core');
// Load ethers using a require instance rooted at TACo's own package location.
// This guarantees we get the SAME ethers instance that TACo uses internally,
// so instanceof checks inside TACo pass correctly.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const tacoMainPath: string = _require.resolve('@nucypher/taco');
const _requireFromTaco = createRequire(tacoMainPath);
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ethersLib: any = _requireFromTaco('ethers');

// ethers v5 CJS exports: { ethers: { providers, Wallet, ... } } or flat
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ethers: any = ethersLib.ethers ?? ethersLib;
const JsonRpcProvider: any = ethers.providers?.JsonRpcProvider ?? ethers.JsonRpcProvider;
const Wallet: any = ethers.Wallet ?? ethers.default?.Wallet;

if (!JsonRpcProvider || !Wallet) {
  throw new Error('[taco] Unsupported ethers module shape; expected JsonRpcProvider and Wallet exports');
}

const { initialize, encrypt, decrypt, domains, conditions } = tacoSdk;
const { EIP4361AuthProvider } = tacoAuth;
const { ThresholdMessageKit } = nucypherCore;

// Deno type declaration
declare const Deno: {
  env: { get(key: string): string | undefined };
  readFile(path: string): Promise<Uint8Array>;
  writeFile(path: string, data: Uint8Array): Promise<void>;
};

const { ContractCondition } = conditions.base.contract;
const { ConditionContext } = conditions.context;

// ── Config helpers ────────────────────────────────────────────────────────────

function getPrivateKey(): string {
  const key = Deno.env.get('HAVEN_PRIVATE_KEY') ?? Deno.env.get('PRIVATE_KEY') ?? '';
  if (!key) throw new Error('[taco] HAVEN_PRIVATE_KEY not set');
  return key.startsWith('0x') ? key : `0x${key}`;
}

function getTacoConfig() {
  const domainName = Deno.env.get('TACO_DOMAIN') ?? 'lynx';
  const ritualId = parseInt(Deno.env.get('TACO_RITUAL_ID') ?? '27', 10);
  const rpcUrl = Deno.env.get('TACO_RPC_URL') ?? 'https://rpc-amoy.polygon.technology';
  const nftContract = Deno.env.get('TACO_NFT_CONTRACT') ?? Deno.env.get('TACO_NFT_CONTRACT_ADDRESS') ?? '';
  const chainId = parseInt(Deno.env.get('TACO_NFT_CHAIN_ID') ?? '11155111', 10);
  const tokenType = (Deno.env.get('TACO_TOKEN_TYPE') ?? 'ERC20') as 'ERC20' | 'ERC721';

  // Map domain name to TACo SDK domain constant
  const domainMap: Record<string, string> = {
    lynx: 'lynx', 'datil-dev': 'lynx',
    tapir: 'tapir', 'datil-test': 'tapir',
    datil: 'datil', mainnet: 'datil',
  };
  const resolvedDomain = domainMap[domainName] ?? domainName;
  const tacoDomain = (domains as Record<string, string>)[resolvedDomain.toUpperCase()] ?? resolvedDomain;

  return { tacoDomain, resolvedDomain, ritualId, rpcUrl, nftContract, chainId, tokenType };
}

function buildCondition(nftContract: string, chainId: number, tokenType: 'ERC20' | 'ERC721'): Record<string, unknown> {
  if (tokenType === 'ERC721') {
    return {
      conditionType: 'contract',
      chain: chainId,
      contractAddress: nftContract,
      standardContractType: 'ERC721',
      method: 'balanceOf',
      parameters: [':userAddress'],
      returnValueTest: { comparator: '>=', value: 1 },
    };
  }
  return {
    conditionType: 'contract',
    chain: chainId,
    contractAddress: nftContract,
    standardContractType: 'ERC20',
    method: 'balanceOf',
    parameters: [':userAddress'],
    returnValueTest: { comparator: '>=', value: 1 },
  };
}

// ── TACo encrypt/decrypt helpers ──────────────────────────────────────────────

async function tacoEncryptBytes(
  plaintext: Uint8Array,
  conditionProps: Record<string, unknown>,
  tacoDomain: string,
  ritualId: number,
  rpcUrl: string,
  privateKey: string,
): Promise<Uint8Array> {
  await initialize();
  const provider = new JsonRpcProvider(rpcUrl);
  const wallet = new Wallet(privateKey, provider);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const conditionObj = new ContractCondition(conditionProps as any);
  const messageKit = await encrypt(provider, tacoDomain, plaintext, conditionObj, ritualId, wallet);
  return messageKit.toBytes();
}

async function tacoDecryptBytes(
  messageKitBytes: Uint8Array,
  tacoDomain: string,
  rpcUrl: string,
  privateKey: string,
): Promise<Uint8Array> {
  await initialize();
  const provider = new JsonRpcProvider(rpcUrl);
  const wallet = new Wallet(privateKey, provider);
  const messageKit = ThresholdMessageKit.fromBytes(messageKitBytes);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const conditionObj = new ContractCondition((messageKit as any).acp.conditions);
  const conditionContext = new ConditionContext(conditionObj);
  const authProvider = new EIP4361AuthProvider(provider, wallet);
  conditionContext.addAuthProvider(':userAddress', authProvider);
  return await decrypt(provider, tacoDomain, messageKit, conditionContext);
}

// ── TACo Provider Implementation ──────────────────────────────────────────────

class TacoProvider implements AccessControlProvider {
  private _connected = false;
  private _network = '';

  get isConnected(): boolean {
    return this._connected;
  }

  async connect(params: Record<string, unknown>): Promise<LitConnectResult> {
    await initialize();
    const cfg = getTacoConfig();
    this._network = cfg.resolvedDomain;
    this._connected = true;
    console.error(`[taco] Connected — domain=${cfg.tacoDomain}, ritual=${cfg.ritualId}`);
    return { connected: true, network: cfg.resolvedDomain, nodeCount: 1 };
  }

  async disconnect(): Promise<void> {
    this._connected = false;
    this._network = '';
  }

  async encryptFile(
    params: Record<string, unknown>,
    onProgress?: ProgressCallback,
  ): Promise<LitEncryptFileResult> {
    if (!this._connected) throw new Error('[taco] Not connected');

    const filePath = params.filePath as string;
    const chain = (params.chain as string) ?? 'ethereum';
    if (!filePath) throw new Error('[taco] Missing filePath');

    const privateKey = getPrivateKey();
    const cfg = getTacoConfig();

    onProgress?.(5, 'Reading file...', 0, 0);
    const fileData = await Deno.readFile(filePath);

    // Build condition — use params.accessControlConditions if provided, else env config
    const conditionProps = cfg.nftContract
      ? buildCondition(cfg.nftContract, cfg.chainId, cfg.tokenType)
      : (params.accessControlConditions as Record<string, unknown>[] | undefined)?.[0] ?? {};

    onProgress?.(20, 'Encrypting with TACo...', 0, fileData.length);

    // TACo encrypts the raw file bytes directly (no separate AES key wrapping needed)
    const messageKitBytes = await tacoEncryptBytes(
      fileData,
      conditionProps,
      cfg.tacoDomain,
      cfg.ritualId,
      cfg.rpcUrl,
      privateKey,
    );

    // Write encrypted file
    const encryptedFilePath = `${filePath}.encrypted`;
    await Deno.writeFile(encryptedFilePath, messageKitBytes);

    // Build metadata in hybrid-v1 schema for backwards compat
    // encryptedKey = base64(messageKit bytes) — TACo's equivalent of Lit's encrypted AES key
    const messageKitB64 = btoa(String.fromCharCode(...messageKitBytes));
    const metadata: HybridEncryptionMetadata = {
      version: 'hybrid-v1',
      encryptedKey: messageKitB64,
      keyHash: await sha256Hex(messageKitBytes),
      iv: '',           // Not used — TACo handles IV internally
      algorithm: 'AES-GCM',
      keyLength: 256,
      accessControlConditions: [],  // TACo conditions are embedded in messageKit
      chain,
    };

    // Write metadata
    const metadataPath = `${encryptedFilePath}.meta.json`;
    const metadataJson = JSON.stringify({ ...metadata, provider: 'taco', conditionProps });
    await Deno.writeFile(metadataPath, new TextEncoder().encode(metadataJson));

    onProgress?.(100, 'Encryption complete', fileData.length, fileData.length);

    return {
      encryptedFilePath,
      metadataPath,
      metadata,
      originalSize: fileData.length,
      encryptedSize: messageKitBytes.length,
    };
  }

  async decryptFile(
    params: Record<string, unknown>,
    onProgress?: ProgressCallback,
  ): Promise<LitDecryptFileResult> {
    if (!this._connected) throw new Error('[taco] Not connected');

    const encryptedFilePath = params.encryptedFilePath as string;
    const metadataPath = (params.metadataPath as string) ?? `${encryptedFilePath}.meta.json`;
    const outputPath = params.outputPath as string;
    if (!encryptedFilePath || !outputPath) throw new Error('[taco] Missing encryptedFilePath or outputPath');

    const privateKey = getPrivateKey();
    const cfg = getTacoConfig();

    onProgress?.(5, 'Reading encrypted file...', 0, 0);
    const encryptedData = await Deno.readFile(encryptedFilePath);

    // Read metadata to get the domain (may differ from current config)
    const metaBytes = await Deno.readFile(metadataPath);
    const meta = JSON.parse(new TextDecoder().decode(metaBytes));
    const tacoDomain = meta.tacoDomain ?? cfg.tacoDomain;

    onProgress?.(20, 'Decrypting with TACo...', 0, encryptedData.length);

    const decryptedData = await tacoDecryptBytes(encryptedData, tacoDomain, cfg.rpcUrl, privateKey);

    await Deno.writeFile(outputPath, decryptedData);

    onProgress?.(100, 'Decryption complete', decryptedData.length, decryptedData.length);

    return {
      outputPath,
      size: decryptedData.length,
      integrityCheck: true,
    };
  }

  async encryptCid(params: Record<string, unknown>): Promise<LitEncryptCidResult> {
    if (!this._connected) throw new Error('[taco] Not connected');

    const cid = params.cid as string;
    const chain = (params.chain as string) ?? 'ethereum';
    if (!cid) throw new Error('[taco] Missing cid');

    const privateKey = getPrivateKey();
    const cfg = getTacoConfig();

    const conditionProps = cfg.nftContract
      ? buildCondition(cfg.nftContract, cfg.chainId, cfg.tokenType)
      : (params.accessControlConditions as Record<string, unknown>[] | undefined)?.[0] ?? {};

    const cidBytes = new TextEncoder().encode(cid);
    const messageKitBytes = await tacoEncryptBytes(
      cidBytes,
      conditionProps,
      cfg.tacoDomain,
      cfg.ritualId,
      cfg.rpcUrl,
      privateKey,
    );

    const messageKitB64 = btoa(String.fromCharCode(...messageKitBytes));
    const keyHash = await sha256Hex(messageKitBytes);

    return {
      encryptedCid: messageKitB64,
      dataToEncryptHash: keyHash,
      encryptedKey: messageKitB64,
      keyHash,
      iv: '',
      algorithm: 'AES-GCM',
      keyLength: 256,
      accessControlConditions: [],
      chain,
    };
  }
}

// ── Utility ───────────────────────────────────────────────────────────────────

async function sha256Hex(data: Uint8Array): Promise<string> {
  const hashBuffer = await crypto.subtle.digest('SHA-256', data as unknown as ArrayBuffer);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

// ── Export ────────────────────────────────────────────────────────────────────

export function createTacoProvider(): AccessControlProvider {
  return new TacoProvider();
}
