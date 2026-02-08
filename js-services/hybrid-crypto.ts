/**
 * Hybrid Encryption Service - AES-256-GCM + Lit Protocol (Deno/CLI Version)
 *
 * This module implements a two-layer encryption approach:
 * - Layer 1: AES-256-GCM for local file encryption (hardware accelerated)
 * - Layer 2: Lit BLS-IBE for encrypting the AES key only (32 bytes)
 *
 * Benefits:
 * - Can encrypt/decrypt files of any size efficiently
 * - Only 32 bytes (the AES key) is sent to Lit nodes
 * - Uses standard Web Crypto API (hardware accelerated)
 * - v8 compatible and future-proof
 *
 * Based on frontend/src/services/hybridCrypto.ts, adapted for Deno
 */

import { createLitClient } from '@lit-protocol/lit-client';
import { naga, nagaDev } from '@lit-protocol/networks';
import { createAuthManager } from '@lit-protocol/auth';
import { LitAccessControlConditionResource } from '@lit-protocol/auth-helpers';
import { ethers } from 'ethers';
import { createMemoryStorage } from './lit-storage.ts';
import { createViemAccount } from './viem-adapter.ts';
import { verifyPaymentSetup } from './lit-payment.ts';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type LitClient = any;

// ============================================================================
// Types and Interfaces
// ============================================================================

/** Standard access control condition format */
export interface EvmBasicAccessControlCondition {
  contractAddress: string;
  standardContractType:
    | ''
    | 'PKPPermissions'
    | 'timestamp'
    | 'ERC20'
    | 'ERC721'
    | 'ERC721MetadataName'
    | 'ERC1155'
    | 'CASK'
    | 'Creaton'
    | 'POAP'
    | 'MolochDAOv2.1'
    | 'ProofOfHumanity'
    | 'SIWE'
    | 'LitAction';
  chain:
    | 'ethereum'
    | 'sepolia'
    | 'goerli'
    | 'polygon'
    | 'mumbai'
    | 'bsc'
    | 'avalanche'
    | 'fuji'
    | 'arbitrum'
    | 'optimism'
    | 'base'
    | 'filecoin'
    | 'yellowstone'
    | 'fantom'
    | 'xdai';
  method: string;
  parameters: string[];
  returnValueTest: {
    comparator: '=' | 'contains' | '>' | '>=' | '<' | '<=';
    value: string;
  };
}

/** Unified access control condition format for Lit v8 */
interface UnifiedAccessControlCondition {
  conditionType: 'evmBasic';
  contractAddress: string;
  standardContractType:
    | ''
    | 'PKPPermissions'
    | 'timestamp'
    | 'ERC20'
    | 'ERC721'
    | 'ERC721MetadataName'
    | 'ERC1155'
    | 'CASK'
    | 'Creaton'
    | 'POAP'
    | 'MolochDAOv2.1'
    | 'ProofOfHumanity'
    | 'SIWE'
    | 'LitAction';
  chain:
    | 'ethereum'
    | 'sepolia'
    | 'goerli'
    | 'polygon'
    | 'mumbai'
    | 'bsc'
    | 'avalanche'
    | 'fuji'
    | 'arbitrum'
    | 'optimism'
    | 'base'
    | 'filecoin'
    | 'yellowstone'
    | 'fantom'
    | 'xdai';
  method: string;
  parameters: string[];
  returnValueTest: {
    comparator: '=' | 'contains' | '>' | '>=' | '<' | '<=';
    value: string;
  };
}

/**
 * Hybrid encryption metadata stored alongside the encrypted file
 */
export interface HybridEncryptionMetadata {
  /** Version identifier for future compatibility */
  version: 'hybrid-v1';
  /** BLS-encrypted AES key (base64-encoded ciphertext from Lit) */
  encryptedKey: string;
  /** SHA-256 hash of the AES key (for verification) */
  keyHash: string;
  /** Base64-encoded 12-byte IV for AES-GCM */
  iv: string;
  /** AES algorithm identifier */
  algorithm: 'AES-GCM';
  /** Key length in bits */
  keyLength: 256;
  /** Access control conditions for Lit decryption */
  accessControlConditions: EvmBasicAccessControlCondition[];
  /** Blockchain chain identifier */
  chain: string;
  /** Optional: Original file MIME type */
  originalMimeType?: string;
  /** Optional: Original file size in bytes */
  originalSize?: number;
  /** Optional: SHA-256 hash of original file content */
  originalHash?: string;
}

/** Result of hybrid encryption operation */
export interface HybridEncryptionResult {
  /** AES-encrypted file data */
  encryptedFile: Uint8Array;
  /** Metadata needed for decryption */
  metadata: HybridEncryptionMetadata;
}

// ============================================================================
// Constants
// ============================================================================

/** AES-256 key size in bytes */
const AES_KEY_SIZE = 32;


/**
 * Convert ArrayBuffer or Uint8Array to base64 string
 */
=======
/** AES-GCM authentication tag size in bytes (128 bits) */
const AES_AUTH_TAG_SIZE = 16;

/** Default chunk size for progress reporting (1MB) */
const DEFAULT_CHUNK_SIZE = 1024 * 1024;

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Convert ArrayBuffer or Uint8Array to base64 string
 */============================================================================
// Utility Functions
// ============================================================================

/**
 * Convert ArrayBuffer or Uint8Array to base64 string
 */
=======
/** AES-GCM authentication tag size in bytes (128 bits) */
const AES_AUTH_TAG_SIZE = 16;

/** Default chunk size for progress reporting (1MB) */
const DEFAULT_CHUNK_SIZE = 1024 * 1024;

// ============================================================================
// Utility Functions
// ========================================================================================================================================================

/**
 * Convert ArrayBuffer or Uint8Array to base64 string
 */
=======
/** AES-GCM authentication tag size in bytes (128 bits) */
const AES_AUTH_TAG_SIZE = 16;

/** Default chunk size for progress reporting (1MB) */
const DEFAULT_CHUNK_SIZE = 1024 * 1024;

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Convert ArrayBuffer or Uint8Array to base64 string
 */============================================================================
// Utility Functions
// ============================================================================

/**
 * Convert ArrayBuffer or Uint8Array to base64 string
 */
function arrayBufferToBase64(buffer: ArrayBuffer | Uint8Array): string {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

/**
 * Convert base64 string to ArrayBuffer
 */
function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

/**
 * Convert Uint8Array to ArrayBuffer safely
 */
function toArrayBuffer(data: Uint8Array): ArrayBuffer {
  if (data.buffer instanceof ArrayBuffer) {
    // Check if this is a view into a larger buffer
    if (data.byteOffset === 0 && data.byteLength === data.buffer.byteLength) {
      return data.buffer;
    }
  }
  // Create a copy to ensure we have a standalone ArrayBuffer
  const buffer = new ArrayBuffer(data.byteLength);
  new Uint8Array(buffer).set(data);
  return buffer;
}

/**
 * Normalize private key by ensuring it has 0x prefix
 */
function normalizePrivateKey(privateKey: string): string {
  const trimmed = privateKey.trim();
  if (trimmed.startsWith('0x') || trimmed.startsWith('0X')) {
    return trimmed;
  }
  return `0x${trimmed}`;
}

/**
 * Get wallet address from private key
 */
function getWalletAddressFromPrivateKey(privateKey: string): string {
  const normalizedKey = normalizePrivateKey(privateKey);
  const wallet = new ethers.Wallet(normalizedKey);
  return wallet.address;
}

/**
 * Create owner-only access control conditions
 * Only the wallet that encrypted can decrypt
 */
function createOwnerOnlyAccessControlConditions(
  walletAddress: string
): EvmBasicAccessControlCondition[] {
  return [
    {
      contractAddress: '',
      standardContractType: '',
      chain: 'ethereum',
      method: '',
      parameters: [':userAddress'],
      returnValueTest: {
        comparator: '=',
        value: walletAddress.toLowerCase(),
      },
    },
  ];
}

/**
 * Convert standard access control conditions to unified format (v8)
 */
function toUnifiedAccessControlConditions(
  conditions: EvmBasicAccessControlCondition[]
): UnifiedAccessControlCondition[] {
  return conditions.map((condition) => ({
    conditionType: 'evmBasic' as const,
    ...condition,
  }));
}

/**
 * Generate SHA-256 hash of data
 */
async function sha256Hash(data: Uint8Array): Promise<string> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const hashBuffer = await crypto.subtle.digest('SHA-256', data as any);
  const hashArray = new Uint8Array(hashBuffer);
  return Array.from(hashArray)
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

// ============================================================================
// AES Encryption Functions
// ============================================================================

/**
 * Generate a random AES-256 key
 * Uses cryptographically secure random number generator
 */
export function generateAESKey(): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(AES_KEY_SIZE));
}

/**
 * Generate a random IV for AES-GCM
 * Uses cryptographically secure random number generator
 */
export function generateIV(): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(AES_IV_SIZE));
}

/**
 * Import raw AES key for Web Crypto API
 */
async function importAESKey(rawKey: Uint8Array, usages: KeyUsage[]): Promise<CryptoKey> {
  return await crypto.subtle.importKey(
    'raw',
    rawKey as unknown as ArrayBuffer,
    { name: 'AES-GCM', length: 256 },
    false, // not extractable after import
    usages
  );
}

/**
 * Encrypt data using AES-256-GCM
 *
 * @param data - Data to encrypt
 * @param key - AES key (32 bytes)
 * @param iv - Initialization vector (12 bytes)
 * @returns Encrypted data (includes auth tag)
 */
export async function aesEncrypt(
  data: Uint8Array,
  key: Uint8Array,
  iv: Uint8Array
): Promise<Uint8Array> {
  const cryptoKey = await importAESKey(key, ['encrypt']);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const encrypted = await crypto.subtle.encrypt({ name: 'AES-GCM', iv: iv as any }, cryptoKey, data as any);

  return new Uint8Array(encrypted);
}

/**
 * Decrypt data using AES-256-GCM
 *
 * @param encryptedData - Encrypted data (includes auth tag)
 * @param key - AES key (32 bytes)
 * @param iv - Initialization vector (12 bytes)
 * @returns Decrypted data
 * @throws Error if decryption fails (wrong key, corrupted data, etc.)
 */
// Lit Client Management
// ============================================================================
=======
export async function aesDecrypt(
  encryptedData: Uint8Array,
  key: Uint8Array,
  iv: Uint8Array
): Promise<Uint8Array> {
  const cryptoKey = await importAESKey(key, ['decrypt']);

  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const decrypted = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: iv as any }, cryptoKey, encryptedData as any);

    return new Uint8Array(decrypted);
  } catch (error) {
    if (error instanceof Error) {
      throw new Error(
        `AES decryption failed: ${error.message}. ` +
          'The file may be corrupted, tampered with, or the wrong decryption key is being used.'
      );
    }
    throw error;
  }
}

/** Progress callback for chunked encryption */
export type EncryptionProgressCallback = (
  percent: number,
  bytesProcessed: number,
  totalBytes: number
) => void;

/** Encrypt data using AES-256-GCM with chunked processing for progress reporting */
export async function aesEncryptChunked(
  data: Uint8Array,
  key: Uint8Array,
  iv: Uint8Array,
  onProgress?: EncryptionProgressCallback,
  chunkSize: number = DEFAULT_CHUNK_SIZE
): Promise<Uint8Array> {
  const totalBytes = data.byteLength;
  const totalChunks = Math.ceil(totalBytes / chunkSize);
  const cryptoKey = await importAESKey(key, ['encrypt']);

  onProgress?.(0, 0, totalBytes);

  const encryptedChunkSize = chunkSize + AES_AUTH_TAG_SIZE;
  const lastChunkSize = (totalBytes % chunkSize) || chunkSize;
  const lastEncryptedChunkSize = lastChunkSize + AES_AUTH_TAG_SIZE;
  const totalEncryptedSize = 4 + (totalChunks - 1) * (4 + 4 + encryptedChunkSize) + (4 + 4 + lastEncryptedChunkSize) + 12;

  const output = new Uint8Array(totalEncryptedSize);
  const view = new DataView(output.buffer);
  view.setUint32(0, totalChunks, false);

  let outputOffset = 4;
  let bytesProcessed = 0;

  for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
    const start = chunkIndex * chunkSize;
    const end = Math.min(start + chunkSize, totalBytes);
    const chunkData = data.slice(start, end);

    const chunkIv = new Uint8Array(iv);
    const chunkIndexBytes = new Uint8Array(4);
    new DataView(chunkIndexBytes.buffer).setUint32(0, chunkIndex, false);
    chunkIv[8] ^= chunkIndexBytes[0];
    chunkIv[9] ^= chunkIndexBytes[1];
    chunkIv[10] ^= chunkIndexBytes[2];
    chunkIv[11] ^= chunkIndexBytes[3];

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const encryptedChunk = new Uint8Array(
      await crypto.subtle.encrypt({ name: 'AES-GCM', iv: chunkIv as any }, cryptoKey, chunkData as any)
    );

    view.setUint32(outputOffset, chunkIndex, false);
    outputOffset += 4;
    view.setUint32(outputOffset, encryptedChunk.byteLength, false);
    outputOffset += 4;
    output.set(encryptedChunk, outputOffset);
    outputOffset += encryptedChunk.byteLength;

    bytesProcessed = end;
    onProgress?.((bytesProcessed / totalBytes) * 100, bytesProcessed, totalBytes);
  }

  output.set(iv, outputOffset);
  return output;
}

/** Decrypt data that was encrypted with aesEncryptChunked */
export async function aesDecryptChunked(encryptedData: Uint8Array, key: Uint8Array): Promise<Uint8Array> {
  const cryptoKey = await importAESKey(key, ['decrypt']);
  const originalIv = encryptedData.slice(-12);
  const view = new DataView(encryptedData.buffer, encryptedData.byteOffset);
  const totalChunks = view.getUint32(0, false);

  let offset = 4;
  let totalDecryptedSize = 0;
  for (let i = 0; i < totalChunks; i++) {
    offset += 4;
    const encryptedChunkLength = view.getUint32(offset, false);
    offset += 4;
    totalDecryptedSize += encryptedChunkLength - AES_AUTH_TAG_SIZE;
    offset += encryptedChunkLength;
  }

  const output = new Uint8Array(totalDecryptedSize);
  let outputOffset = 0;
  offset = 4;

  for (let i = 0; i < totalChunks; i++) {
    const chunkIndex = view.getUint32(offset, false);
    offset += 4;
    const encryptedChunkLength = view.getUint32(offset, false);
    offset += 4;
    const encryptedChunk = encryptedData.slice(offset, offset + encryptedChunkLength);
    offset += encryptedChunkLength;

    const chunkIv = new Uint8Array(originalIv);
    const chunkIndexBytes = new Uint8Array(4);
    new DataView(chunkIndexBytes.buffer).setUint32(0, chunkIndex, false);
    chunkIv[8] ^= chunkIndexBytes[0];
    chunkIv[9] ^= chunkIndexBytes[1];
    chunkIv[10] ^= chunkIndexBytes[2];
    chunkIv[11] ^= chunkIndexBytes[3];

    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const decryptedChunk = new Uint8Array(
        await crypto.subtle.decrypt({ name: 'AES-GCM', iv: chunkIv as any }, cryptoKey, encryptedChunk as any)
      );
      output.set(decryptedChunk, outputOffset);
      outputOffset += decryptedChunk.byteLength;
    } catch (error) {
      if (error instanceof Error) {
        throw new Error(`AES chunk decryption failed at chunk ${chunkIndex}: ${error.message}.`);
      }
      throw error;
    }
  }

  return output;
}

// ============================================================================
// Lit Client Management
// ========================================================================================================================================================
// Lit Client Management
// ============================================================================

let litClient: LitClient | null = null;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let authManager: any = null;
let initPromise: Promise<LitClient> | null = null;

/**
 * Network configuration mapping
 */
const NETWORK_CONFIGS: Record<string, typeof naga> = {
  'naga': naga,  // Mainnet - works
  'naga-dev': nagaDev,  // Devnet - currently has handshake issues
  'naga-staging': nagaDev,  // Staging
  'datil-dev': naga,  // Map to naga for compatibility
};

/**
 * Initialize or get existing Lit client for hybrid encryption
 * Uses nagaDev network (free development network) - Lit SDK v8
 * 
 * @param network - Network name (default: 'naga')
 */
export async function initLitClient(network: string = 'naga'): Promise<LitClient> {
  if (litClient && authManager) {
    return litClient;
  }

  if (initPromise) {
    return initPromise;
  }

  initPromise = (async (): Promise<LitClient> => {
    try {
      // Get network configuration (default to naga mainnet which works)
      const networkConfig = NETWORK_CONFIGS[network] || naga;
      
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      litClient = await (createLitClient as any)({
        network: networkConfig,
      });

      const appName = 'haven-player';
      const networkName = network;

      // Always use memory storage in Deno CLI environment
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      authManager = (createAuthManager as any)({
        storage: createMemoryStorage(appName, networkName),
      });

      console.log(`[Lit] Connected to Lit network (${network}) - SDK v8`);
      return litClient;
    } catch (error) {
      litClient = null;
      authManager = null;
      throw error;
    } finally {
      initPromise = null;
    }
  })();

  return initPromise;
}

/**
 * Disconnect Lit client
 */
export async function disconnectLitClient(): Promise<void> {
  if (litClient) {
    try {
      await litClient.disconnect();
    } catch (error) {
      console.warn('[Lit] Error during disconnect:', error);
    }
    litClient = null;
    authManager = null;
    initPromise = null;
    console.log('[Lit] Disconnected from Lit network');
  }
}

/**
 * Get the current Lit client (null if not initialized)
 */
export function getLitClient(): LitClient | null {
  return litClient;
}

/**
 * Get the current AuthManager (null if not initialized)
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function getAuthManager(): any | null {
  return authManager;
}

/**
 * Check if Lit client is connected and ready
 */
export function isLitClientConnected(): boolean {
  return litClient !== null && authManager !== null;
}

/**
 * Get authentication context for Lit Protocol operations
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function getAuthContext(privateKey: string, chain: string = 'ethereum'): Promise<any> {
  if (!litClient || !authManager) {
    throw new Error('Lit client not initialized. Call initLitClient() first.');
  }

  const viemAccount = createViemAccount(privateKey);

  const authContext = await authManager.createEoaAuthContext({
    authConfig: {
      domain: 'haven-player.local',
      statement: 'Sign this message to authenticate with Haven Player',
      resources: [
        {
          resource: new LitAccessControlConditionResource('*'),
          ability: 'access-control-condition-decryption',
        },
      ],
      expiration: new Date(Date.now() + 1000 * 60 * 60).toISOString(), // 1 hour
    },
    config: {
      account: viemAccount,
    },
    litClient,
  });

  return authContext;
}

// ============================================================================
// Hybrid Encryption/Decryption
// ============================================================================

/**
 * Encrypt a file using hybrid encryption (AES-256-GCM + Lit Protocol)
 *
 * This function:
 * 1. Generates a random AES-256 key
 * 2. Encrypts the file locally using AES-GCM (chunked for progress reporting)
 * 3. Encrypts the AES key using Lit Protocol (BLS-IBE)
 * 4. Returns encrypted file + metadata
 *
 * Benefits:
 * - Only 32 bytes sent to Lit nodes (the AES key)
 * - File encryption is hardware accelerated
 * - Can handle files of any size efficiently
 * - Progress reporting for large files
 *
 * @param file - File or ArrayBuffer to encrypt
 * @param privateKey - Private key for access control
 * @param chain - Blockchain chain (default: 'ethereum')
 * @param onProgress - Optional progress callback (percent, message, bytesProcessed, totalBytes)
 * @param network - Lit network (default: 'naga')
 * @returns Encrypted file and metadata
 */
export async function hybridEncryptFile(
  file: ArrayBuffer,
  privateKey: string,
  chain: string = 'ethereum',
  onProgress?: EncryptionProgressCallback,
  network: string = 'naga'
): Promise<HybridEncryptionResult> {
  const totalBytes = file.byteLength;
  
  // Step 1: Generate local AES key and IV (5%)
  onProgress?.(0, 0, totalBytes);
  onProgress?.(5, 'Generating encryption key...', 0, totalBytes);
  const aesKey = generateAESKey();
  const iv = generateIV();

  // Step 2: Read file data (10%)
  onProgress?.(10, 'Reading file...', 0, totalBytes);
  const fileData = new Uint8Array(file);

  // Step 3: Encrypt file locally with AES using chunked encryption for progress (10-85%)
  // The chunked encryption will report progress from 10% to 85%
  const encryptedFile = await aesEncryptChunked(
    fileData,
    aesKey,
    iv,
    (percent, bytesProcessed, _totalBytes) => {
      // Map chunked encryption progress (0-100) to overall progress (10-85)
      const overallPercent = 10 + (percent * 0.75);
      onProgress?.(overallPercent, 'Encrypting file locally (AES-256-GCM)...', bytesProcessed, totalBytes);
    }
  );

  // Step 4: Calculate hash of original file (87%)
  onProgress?.(87, 'Calculating file hash...', fileData.byteLength, totalBytes);
  const originalHash = await sha256Hash(fileData);

  // Step 5: Initialize Lit client and encrypt AES key (88-95%)
  onProgress?.(88, 'Initializing Lit Protocol...', fileData.byteLength, totalBytes);
  const client = await initLitClient(network);
  const walletAddress = getWalletAddressFromPrivateKey(privateKey);

  onProgress?.(90, 'Encrypting key with Lit Protocol...', fileData.byteLength, totalBytes);
  const accessControlConditions = createOwnerOnlyAccessControlConditions(walletAddress);
  const unifiedAccessControlConditions = toUnifiedAccessControlConditions(accessControlConditions);

  // Encrypt only the AES key with Lit (32 bytes - fast and cheap!)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const litResult = await (client as any).encrypt({
    dataToEncrypt: aesKey,
    unifiedAccessControlConditions,
    chain,
  });

  // Step 6: Construct metadata (97%)
  onProgress?.(97, 'Finalizing encryption...', fileData.byteLength, totalBytes);
  const metadata: HybridEncryptionMetadata = {
    version: 'hybrid-v1',
    encryptedKey: litResult.ciphertext,
    keyHash: litResult.dataToEncryptHash,
    iv: arrayBufferToBase64(iv),
    algorithm: 'AES-GCM',
    keyLength: 256,
    accessControlConditions,
    chain,
    originalSize: fileData.byteLength,
    originalHash,
  };

  // Complete (100%)
  onProgress?.(100, 'Encryption complete', fileData.byteLength, totalBytes);

  // Clear sensitive key from memory
  aesKey.fill(0);

  return { encryptedFile, metadata };
}

/**
 * Decrypt a file using hybrid encryption (Lit Protocol + AES-256-GCM)
 *
 * This function:
 * 1. Decrypts the AES key from Lit Protocol
 * 2. Decrypts the file locally using AES-GCM (chunked for progress reporting)
 * 3. Returns decrypted file as Uint8Array
 *
 * @param encryptedFile - AES-encrypted file data (chunked format)
 * @param metadata - Hybrid encryption metadata
 * @param privateKey - Private key for authentication
 * @param onProgress - Optional progress callback (percent, message, bytesProcessed, totalBytes)
 * @param network - Lit network (default: 'naga')
 * @returns Decrypted file as Uint8Array
 */
export async function hybridDecryptFile(
  encryptedFile: Uint8Array,
  metadata: HybridEncryptionMetadata,
  privateKey: string,
  onProgress?: EncryptionProgressCallback,
  network: string = 'naga'
): Promise<Uint8Array> {
  // Validate metadata version
  if (metadata.version !== 'hybrid-v1') {
    throw new Error(
      `Unsupported encryption version: ${metadata.version}. ` + 'Only hybrid-v1 is supported.'
    );
  }

  const totalBytes = metadata.originalSize || encryptedFile.byteLength;
  
  // Step 1: Initialize Lit Protocol (0-5%)
  onProgress?.(0, 'Initializing Lit Protocol...', 0, totalBytes);
  
  // Verify payment setup before attempting decryption (mainnet only)
  // This is similar to how Synapse SDK checks upload readiness
  try {
    await verifyPaymentSetup(privateKey, network);
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.warn('[Lit Payment] Payment verification warning:', errorMessage);
    // Don't throw here - let the operation proceed and fail naturally if credits are required
    // This allows dev networks to work without credits
  }
  
  // Step 2: Connect to Lit client (5-10%)
  onProgress?.(5, 'Connecting to Lit network...', 0, totalBytes);
  const client = await initLitClient(network);

  // Step 3: Authenticate (10-15%)
  onProgress?.(10, 'Authenticating...', 0, totalBytes);
  const authContext = await getAuthContext(privateKey, metadata.chain);

  // Step 4: Decrypt encryption key (15-20%)
  onProgress?.(15, 'Decrypting encryption key...', 0, totalBytes);
  const unifiedAccessControlConditions = toUnifiedAccessControlConditions(
    metadata.accessControlConditions
  );

  // Decrypt AES key from Lit
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const keyResult = await (client as any).decrypt({
    data: {
      ciphertext: metadata.encryptedKey,
      dataToEncryptHash: metadata.keyHash,
    },
    unifiedAccessControlConditions,
    authContext,
    chain: metadata.chain,
  });

  const aesKey = keyResult.decryptedData as Uint8Array;

  try {
    // Step 5: Decrypt file locally with AES using chunked decryption (20-95%)
    onProgress?.(20, 'Decrypting file locally...', 0, totalBytes);
    const decryptedData = await aesDecryptChunked(encryptedFile, aesKey);

    // Step 6: Verify hash if available (95-100%)
    if (metadata.originalHash) {
      onProgress?.(95, 'Verifying file integrity...', decryptedData.byteLength, totalBytes);
      const computedHash = await sha256Hash(decryptedData);
      if (computedHash !== metadata.originalHash) {
        throw new Error(
          'File integrity check failed. The file may have been corrupted or tampered with.'
        );
      }
    }

    onProgress?.(100, 'Decryption complete', decryptedData.byteLength, totalBytes);

    return decryptedData;
  } finally {
    // Clear sensitive key from memory
    aesKey.fill(0);
  }
}

// ============================================================================
// Serialization Utilities
// ============================================================================

/**
 * Serialize hybrid encryption metadata to JSON string
 */
export function serializeHybridMetadata(metadata: HybridEncryptionMetadata): string {
  return JSON.stringify(metadata);
}

/**
 * Deserialize hybrid encryption metadata from JSON string
 */
export function deserializeHybridMetadata(metadataJson: string): HybridEncryptionMetadata {
  const parsed = JSON.parse(metadataJson);

  // Validate required fields
  if (parsed.version !== 'hybrid-v1') {
    throw new Error(`Unsupported hybrid encryption version: ${parsed.version}`);
  }

  if (!parsed.encryptedKey || !parsed.keyHash || !parsed.iv) {
    throw new Error('Invalid hybrid encryption metadata: missing required fields');
  }

  return parsed as HybridEncryptionMetadata;
}

/**
 * Check if metadata is hybrid encryption format
 */
export function isHybridMetadata(metadata: unknown): metadata is HybridEncryptionMetadata {
  if (typeof metadata !== 'object' || metadata === null) {
    return false;
  }
  const m = metadata as Record<string, unknown>;
  return (
    m.version === 'hybrid-v1' &&
    typeof m.encryptedKey === 'string' &&
    typeof m.keyHash === 'string' &&
    typeof m.iv === 'string'
  );
}

// ============================================================================
// Performance Utilities
// ============================================================================

/**
 * Calculate expected encrypted file size
 * AES-GCM adds 16 bytes for authentication tag
 */
export function getEncryptedSize(originalSize: number): number {
  return originalSize + AES_AUTH_TAG_SIZE;
}

/**
 * Get original file size from metadata
 */
export function getOriginalSize(metadata: HybridEncryptionMetadata): number | undefined {
  return metadata.originalSize;
}

/**
 * Estimate encryption/decryption throughput
 * Typical values: 100-500 MB/s depending on hardware
 */
export function estimateProcessingTime(
  fileSizeBytes: number,
  throughputMBps: number = 200
): number {
  const fileSizeMB = fileSizeBytes / (1024 * 1024);
  return (fileSizeMB / throughputMBps) * 1000; // milliseconds
}
