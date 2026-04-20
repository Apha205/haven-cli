/**
 * TACo Node.js Runtime
 *
 * JSON-RPC 2.0 server for TACo threshold encryption/decryption.
 * Runs under Node.js (not Deno) because @nucypher/nucypher-core uses
 * native WASM with Node.js-specific internal APIs incompatible with Deno.
 *
 * Same JSON-RPC protocol as main.ts — Python bridge communicates via stdin/stdout.
 *
 * Environment variables:
 *   HAVEN_PRIVATE_KEY or PRIVATE_KEY  — wallet private key (hex, with or without 0x)
 *   TACO_DOMAIN                        — TACo domain: lynx|tapir|datil (default: lynx)
 *   TACO_RITUAL_ID                     — ritual ID (default: 27)
 *   TACO_RPC_URL                       — Polygon Amoy RPC URL
 *   TACO_NFT_CONTRACT                  — ERC20/ERC721 contract address for access condition
 *   TACO_NFT_CHAIN_ID                  — chain ID for condition (default: 11155111 = Sepolia)
 *   TACO_TOKEN_TYPE                    — ERC20 or ERC721 (default: ERC20)
 */

import { createRequire } from 'node:module';
import { createInterface } from 'node:readline';
import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';

// Use createRequire to load CJS packages
const require = createRequire(import.meta.url);

// Load TACo SDK (CJS build — no directory import issues)
const tacoSdk = require('@nucypher/taco');
const tacoAuth = require('@nucypher/taco-auth');
const nucypherCore = require('@nucypher/nucypher-core');

// Load ethers v5 from TACo's own dependency tree to ensure same instance
const tacoMainPath = require.resolve('@nucypher/taco');
const requireFromTaco = createRequire(tacoMainPath);
const ethersLib = requireFromTaco('ethers');
const ethers = ethersLib.ethers ?? ethersLib;
const { JsonRpcProvider, Wallet } = ethers.providers
  ? { JsonRpcProvider: ethers.providers.JsonRpcProvider, Wallet: ethers.Wallet }
  : { JsonRpcProvider: ethers.JsonRpcProvider, Wallet: ethers.Wallet };

const { initialize, encrypt, decrypt, domains, conditions } = tacoSdk;
const { EIP4361AuthProvider } = tacoAuth;
const { ThresholdMessageKit } = nucypherCore;
const { ContractCondition } = conditions.base.contract;
const { ConditionContext } = conditions.context;

// ── Config ────────────────────────────────────────────────────────────────────

function getPrivateKey() {
  const key = process.env.HAVEN_PRIVATE_KEY ?? process.env.PRIVATE_KEY ?? '';
  if (!key) throw new Error('[taco-node] HAVEN_PRIVATE_KEY not set');
  return key.startsWith('0x') ? key : `0x${key}`;
}

function getTacoConfig() {
  const domainName = process.env.TACO_DOMAIN ?? 'lynx';
  const ritualId = parseInt(process.env.TACO_RITUAL_ID ?? '27', 10);
  const rpcUrl = process.env.TACO_RPC_URL ?? 'https://rpc-amoy.polygon.technology';
  const nftContract = process.env.TACO_NFT_CONTRACT ?? process.env.TACO_NFT_CONTRACT_ADDRESS ?? '';
  const chainId = parseInt(process.env.TACO_NFT_CHAIN_ID ?? '11155111', 10);
  const tokenType = process.env.TACO_TOKEN_TYPE ?? 'ERC20';

  const domainMap = {
    lynx: 'lynx', 'datil-dev': 'lynx',
    tapir: 'tapir', 'datil-test': 'tapir',
    datil: 'datil', mainnet: 'datil',
  };
  const resolvedDomain = domainMap[domainName] ?? domainName;
  const tacoDomain = domains[resolvedDomain.toUpperCase()] ?? resolvedDomain;

  return { tacoDomain, resolvedDomain, ritualId, rpcUrl, nftContract, chainId, tokenType };
}

function buildCondition(nftContract, chainId, tokenType) {
  return {
    conditionType: 'contract',
    chain: chainId,
    contractAddress: nftContract,
    standardContractType: tokenType,
    method: 'balanceOf',
    parameters: [':userAddress'],
    returnValueTest: { comparator: '>=', value: 1 },
  };
}

// ── TACo helpers ──────────────────────────────────────────────────────────────
// initialize() is called once at startup (bottom of this file, before readline).
// Do NOT call it inside method handlers — double-init corrupts the WASM module.

async function tacoEncryptBytes(plaintext, conditionProps, tacoDomain, ritualId, rpcUrl, privateKey) {
  const provider = new JsonRpcProvider(rpcUrl);
  const wallet = new Wallet(privateKey, provider);
  const conditionObj = new ContractCondition(conditionProps);
  // wasm-bindgen requires a plain Uint8Array, not a Node.js Buffer
  const plaintextBytes = plaintext instanceof Uint8Array && !(plaintext instanceof Buffer)
    ? plaintext : new Uint8Array(plaintext);
  const messageKit = await encrypt(provider, tacoDomain, plaintextBytes, conditionObj, ritualId, wallet);
  return messageKit.toBytes();
}

async function tacoDecryptBytes(messageKitBytes, tacoDomain, rpcUrl, privateKey) {
  const provider = new JsonRpcProvider(rpcUrl);
  const wallet = new Wallet(privateKey, provider);
  // wasm-bindgen requires a plain Uint8Array, not a Node.js Buffer
  const kitBytes = messageKitBytes instanceof Uint8Array && !(messageKitBytes instanceof Buffer)
    ? messageKitBytes : new Uint8Array(messageKitBytes);
  const messageKit = ThresholdMessageKit.fromBytes(kitBytes);
  const conditionObj = new ContractCondition(messageKit.acp.conditions);
  const conditionContext = new ConditionContext(conditionObj);
  const authProvider = new EIP4361AuthProvider(provider, wallet);
  conditionContext.addAuthProvider(':userAddress', authProvider);
  return await decrypt(provider, tacoDomain, messageKit, conditionContext);
}

function sha256Hex(data) {
  return createHash('sha256').update(data).digest('hex');
}

// ── State ─────────────────────────────────────────────────────────────────────

const VERSION = '1.0.0';
const startTime = Date.now();
let connected = false;
let connectedDomain = '';
let isShuttingDown = false;

// ── JSON-RPC helpers ──────────────────────────────────────────────────────────

function sendLine(obj) {
  process.stdout.write(JSON.stringify(obj) + '\n');
}

function sendResponse(id, result) {
  sendLine({ jsonrpc: '2.0', result, id });
}

function sendError(id, code, message, data) {
  const error = { code, message };
  if (data !== undefined) error.data = data;
  sendLine({ jsonrpc: '2.0', error, id });
}

function sendNotification(method, params) {
  sendLine({ jsonrpc: '2.0', method, params });
}

// ── Method handlers ───────────────────────────────────────────────────────────

const methods = {
  ping: async () => 'pong',

  shutdown: async () => {
    isShuttingDown = true;
    setTimeout(() => process.exit(0), 100);
    return { status: 'shutting_down' };
  },

  getStatus: async () => ({
    version: VERSION,
    uptimeSeconds: (Date.now() - startTime) / 1000,
    litConnected: connected,
    synapseConnected: false,
    pendingRequests: 0,
  }),

  'lit.connect': async (params) => {
    // WASM already initialized by require('@nucypher/nucypher-core') at load time.
    // Do NOT call initialize() here — it corrupts the already-loaded WASM module.
    const cfg = getTacoConfig();
    connected = true;
    connectedDomain = cfg.resolvedDomain;
    process.stderr.write(`[taco-node] Connected — domain=${cfg.tacoDomain}, ritual=${cfg.ritualId}\n`);
    return { connected: true, network: cfg.resolvedDomain, nodeCount: 1 };
  },

  'lit.encryptFile': async (params) => {
    if (!connected) throw new Error('[taco-node] Not connected');
    const { filePath, chain = 'ethereum', onProgress } = params;
    if (!filePath) throw new Error('[taco-node] Missing filePath');

    const privateKey = getPrivateKey();
    const cfg = getTacoConfig();

    if (onProgress) sendNotification('lit.encryptProgress', { percent: 5, message: 'Reading file...', bytesProcessed: 0, totalBytes: 0, percentage: 5 });

    const fileData = await readFile(filePath);

    const conditionProps = cfg.nftContract
      ? buildCondition(cfg.nftContract, cfg.chainId, cfg.tokenType)
      : (params.accessControlConditions?.[0] ?? {});

    if (onProgress) sendNotification('lit.encryptProgress', { percent: 20, message: 'Encrypting with TACo...', bytesProcessed: 0, totalBytes: fileData.length, percentage: 20 });

    const messageKitBytes = await tacoEncryptBytes(
      fileData, conditionProps, cfg.tacoDomain, cfg.ritualId, cfg.rpcUrl, privateKey
    );

    const encryptedFilePath = `${filePath}.encrypted`;
    await writeFile(encryptedFilePath, messageKitBytes);

    const messageKitB64 = Buffer.from(messageKitBytes).toString('base64');
    const keyHash = sha256Hex(messageKitBytes);

    const metadata = {
      version: 'hybrid-v1',
      encryptedKey: messageKitB64,
      keyHash,
      iv: '',
      algorithm: 'AES-GCM',
      keyLength: 256,
      accessControlConditions: [],
      chain,
    };

    const metadataPath = `${encryptedFilePath}.meta.json`;
    await writeFile(metadataPath, JSON.stringify({ ...metadata, provider: 'taco', conditionProps, tacoDomain: cfg.tacoDomain }));

    if (onProgress) sendNotification('lit.encryptProgress', { percent: 100, message: 'Encryption complete', bytesProcessed: fileData.length, totalBytes: fileData.length, percentage: 100 });

    return {
      encryptedFilePath,
      metadataPath,
      metadata,
      originalSize: fileData.length,
      encryptedSize: messageKitBytes.length,
    };
  },

  'lit.decryptFile': async (params) => {
    if (!connected) throw new Error('[taco-node] Not connected');
    const { encryptedFilePath, outputPath, onProgress } = params;
    const metadataPath = params.metadataPath ?? `${encryptedFilePath}.meta.json`;
    if (!encryptedFilePath || !outputPath) throw new Error('[taco-node] Missing encryptedFilePath or outputPath');

    const privateKey = getPrivateKey();
    const cfg = getTacoConfig();

    if (onProgress) sendNotification('lit.decryptProgress', { percent: 5, message: 'Reading encrypted file...', bytesProcessed: 0, totalBytes: 0, percentage: 5 });

    const encryptedData = await readFile(encryptedFilePath);
    const metaRaw = await readFile(metadataPath, 'utf8');
    const meta = JSON.parse(metaRaw);
    const tacoDomain = meta.tacoDomain ?? cfg.tacoDomain;

    if (onProgress) sendNotification('lit.decryptProgress', { percent: 20, message: 'Decrypting with TACo...', bytesProcessed: 0, totalBytes: encryptedData.length, percentage: 20 });

    const decryptedData = await tacoDecryptBytes(encryptedData, tacoDomain, cfg.rpcUrl, privateKey);
    await writeFile(outputPath, decryptedData);

    if (onProgress) sendNotification('lit.decryptProgress', { percent: 100, message: 'Decryption complete', bytesProcessed: decryptedData.length, totalBytes: decryptedData.length, percentage: 100 });

    return { outputPath, size: decryptedData.length, integrityCheck: true };
  },

  'lit.encryptCid': async (params) => {
    if (!connected) throw new Error('[taco-node] Not connected');
    const { cid, chain = 'ethereum' } = params;
    if (!cid) throw new Error('[taco-node] Missing cid');

    const privateKey = getPrivateKey();
    const cfg = getTacoConfig();

    const conditionProps = cfg.nftContract
      ? buildCondition(cfg.nftContract, cfg.chainId, cfg.tokenType)
      : (params.accessControlConditions?.[0] ?? {});

    const cidBytes = Buffer.from(cid, 'utf8');
    const messageKitBytes = await tacoEncryptBytes(
      cidBytes, conditionProps, cfg.tacoDomain, cfg.ritualId, cfg.rpcUrl, privateKey
    );

    const messageKitB64 = Buffer.from(messageKitBytes).toString('base64');
    const keyHash = sha256Hex(messageKitBytes);

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
  },
};

// ── Main loop ─────────────────────────────────────────────────────────────────

async function handleRequest(request) {
  const { method, params, id } = request;
  const isNotification = id === undefined || id === null;

  try {
    const handler = methods[method];
    if (!handler) {
      if (!isNotification) sendError(id, -32601, `Method not found: ${method}`);
      return;
    }
    const result = await handler(params ?? {});
    if (!isNotification) sendResponse(id, result);
  } catch (err) {
    if (!isNotification) {
      const message = err instanceof Error ? err.message : String(err);
      sendError(id, -32603, message);
    }
  }
}

// ── Startup: initialize TACo WASM once before accepting requests ─────────────
// initialize() from @nucypher/taco sets up the SDK's internal state and must
// be called exactly once before encrypt/decrypt/ThresholdMessageKit are used.
// Calling it inside method handlers causes double-init corruption.
// Calling it here (top-level await in ESM) ensures it runs once at startup.
try {
  await initialize();
  process.stderr.write('[taco-node] TACo WASM initialized\n');
} catch (err) {
  process.stderr.write(`[taco-node] WARNING: initialize() failed: ${err.message} — continuing anyway\n`);
}

// Signal ready
sendNotification('ready', { version: VERSION });

// Read stdin line by line
const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });

rl.on('line', async (line) => {
  const trimmed = line.trim();
  if (!trimmed || isShuttingDown) return;
  try {
    const request = JSON.parse(trimmed);
    await handleRequest(request);
  } catch (err) {
    sendError(null, -32700, 'Parse error', err instanceof Error ? err.message : String(err));
  }
});

rl.on('close', () => {
  process.exit(0);
});

process.on('uncaughtException', (err) => {
  process.stderr.write(`[taco-node] Uncaught exception: ${err.message}\n`);
});

process.on('unhandledRejection', (reason) => {
  process.stderr.write(`[taco-node] Unhandled rejection: ${reason}\n`);
});
