import { createLitClient } from '@lit-protocol/lit-client';
import { naga, nagaDev } from '@lit-protocol/networks';
import { createAuthManager } from '@lit-protocol/auth';
import { LitAccessControlConditionResource } from '@lit-protocol/auth-helpers';
import { ethers } from 'ethers';
import { createMemoryStorage } from './lit-storage.ts';
import { createViemAccount } from './viem-adapter.ts';
import { verifyPaymentSetup } from './lit-payment.ts';

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

const AES_KEY_SIZE = 32;

const AES_IV_SIZE = 12;

const AES_AUTH_TAG_SIZE = 16;

/** Default chunk size for progress reporting: 1MB */
const DEFAULT_CHUNK_SIZE = 1024 * 1024;

/** Threshold for automatic chunked encryption: 50MB */
const CHUNKED_THRESHOLD = 50 * 1024 * 1024;

/** Header size for chunked encryption format: 4 bytes (chunk count) + 12 bytes (IV) */
const CHUNKED_HEADER_SIZE = 16;

/** Per-chunk overhead: 4 bytes (index) + 4 bytes (length) + 16 bytes (auth tag) */
const CHUNK_OVERHEAD = 4 + 4 + AES_AUTH_TAG_SIZE;

export interface HybridEncryptionResult {
  /** AES-encrypted file data */
  encryptedFile: Uint8Array;
  /** Metadata needed for decryption */
  metadata: HybridEncryptionMetadata;
}

/** Progress callback for chunked encryption with precise percentage */
export type EncryptionProgressCallback = (
  percent: number,
  bytesProcessed: number,
  totalBytes: number
) => void;

/** Extended metadata for chunked encryption */
export interface ChunkedEncryptionMetadata extends HybridEncryptionMetadata {
  /** Indicates this file was encrypted with chunked processing */
  chunked: true;
  /** Number of chunks the file was split into */
  totalChunks: number;
  /** Size of each chunk in bytes (except possibly the last) */
  chunkSize: number;
}

function arrayBufferToBase64(buffer: ArrayBuffer | Uint8Array): string {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

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

function normalizePrivateKey(privateKey: string): string {
  const trimmed = privateKey.trim();
  if (trimmed.startsWith('0x') || trimmed.startsWith('0X')) {
    return trimmed;
  }
  return `0x${trimmed}`;
}

function getWalletAddressFromPrivateKey(privateKey: string): string {
  const normalizedKey = normalizePrivateKey(privateKey);
  const wallet = new ethers.Wallet(normalizedKey);
  return wallet.address;
}

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

function toUnifiedAccessControlConditions(
  conditions: EvmBasicAccessControlCondition[]
): UnifiedAccessControlCondition[] {
  return conditions.map((condition) => ({
    conditionType: 'evmBasic' as const,
    ...condition,
  }));
}

async function sha256Hash(data: Uint8Array): Promise<string> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const hashBuffer = await crypto.subtle.digest('SHA-256', data as any);
  const hashArray = new Uint8Array(hashBuffer);
  return Array.from(hashArray)
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

export function generateAESKey(): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(AES_KEY_SIZE));
}

export function generateIV(): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(AES_IV_SIZE));
}

async function importAESKey(rawKey: Uint8Array, usages: KeyUsage[]): Promise<CryptoKey> {
  return await crypto.subtle.importKey(
    'raw',
    rawKey as unknown as ArrayBuffer,
    { name: 'AES-GCM', length: 256 },
    false, // not extractable after import
    usages
  );
}

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

/**
 * Encrypt data using AES-256-GCM with chunked processing for progress reporting.
 * 
 * Format:
 * - Header (16 bytes):
 *   - 4 bytes: total chunk count (uint32, big-endian)
 *   - 12 bytes: original IV
 * - Per chunk:
 *   - 4 bytes: chunk index (uint32, big-endian)
 *   - 4 bytes: encrypted chunk length (uint32, big-endian)
 *   - N bytes: encrypted chunk data (includes 16-byte auth tag)
 * 
 * Each chunk uses a derived IV: original IV with last 4 bytes XOR'd with chunk index.
 * This ensures unique IVs per chunk while maintaining determinism for decryption.
 * 
 * @param data - Data to encrypt
 * @param key - AES key (32 bytes)
 * @param iv - Initialization vector (12 bytes)
 * @param onProgress - Progress callback with precise percentage
 * @param chunkSize - Size of each chunk in bytes (default 1MB)
 * @returns Encrypted data with chunked format
 */
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

  // Report initial state
  onProgress?.(0, 0, totalBytes);

  // Calculate total encrypted size
  // Header: 4 bytes (chunk count) + 12 bytes (IV)
  // Per chunk: 4 bytes (index) + 4 bytes (length) + (chunkSize + 16 bytes auth tag)
  const lastChunkSize = totalBytes % chunkSize || chunkSize;
  const fullChunks = totalChunks - (lastChunkSize < chunkSize ? 1 : 0);
  const encryptedChunkSize = chunkSize + AES_AUTH_TAG_SIZE;
  const lastEncryptedChunkSize = lastChunkSize + AES_AUTH_TAG_SIZE;
  
  const totalEncryptedSize = 
    CHUNKED_HEADER_SIZE + 
    (fullChunks * (CHUNK_OVERHEAD + chunkSize)) +
    (totalChunks > fullChunks ? (CHUNK_OVERHEAD + lastChunkSize) : 0);

  const output = new Uint8Array(totalEncryptedSize);
  const view = new DataView(output.buffer);

  // Write header
  view.setUint32(0, totalChunks, false); // big-endian
  output.set(iv, 4);

  let outputOffset = CHUNKED_HEADER_SIZE;
  let bytesProcessed = 0;

  for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
    const start = chunkIndex * chunkSize;
    const end = Math.min(start + chunkSize, totalBytes);
    const chunkData = data.slice(start, end);

    // Derive chunk IV by modifying last 4 bytes with chunk index
    const chunkIv = new Uint8Array(iv);
    const chunkIndexBytes = new Uint8Array(4);
    new DataView(chunkIndexBytes.buffer).setUint32(0, chunkIndex, false);
    chunkIv[8] ^= chunkIndexBytes[0];
    chunkIv[9] ^= chunkIndexBytes[1];
    chunkIv[10] ^= chunkIndexBytes[2];
    chunkIv[11] ^= chunkIndexBytes[3];

    // Encrypt chunk
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const encryptedChunk = new Uint8Array(
      await crypto.subtle.encrypt({ name: 'AES-GCM', iv: chunkIv as any }, cryptoKey, chunkData as any)
    );

    // Write chunk header and data
    view.setUint32(outputOffset, chunkIndex, false);
    outputOffset += 4;
    view.setUint32(outputOffset, encryptedChunk.byteLength, false);
    outputOffset += 4;
    output.set(encryptedChunk, outputOffset);
    outputOffset += encryptedChunk.byteLength;

    bytesProcessed = end;
    onProgress?.((bytesProcessed / totalBytes) * 100, bytesProcessed, totalBytes);
  }

  return output;
}

/**
 * Decrypt data that was encrypted with aesEncryptChunked.
 * 
 * @param encryptedData - Encrypted data in chunked format
 * @param key - AES key (32 bytes)
 * @param onProgress - Optional progress callback
 * @returns Decrypted data
 */
export async function aesDecryptChunked(
  encryptedData: Uint8Array,
  key: Uint8Array,
  onProgress?: EncryptionProgressCallback
): Promise<Uint8Array> {
  const cryptoKey = await importAESKey(key, ['decrypt']);

  // Read header
  const view = new DataView(encryptedData.buffer, encryptedData.byteOffset);
  const totalChunks = view.getUint32(0, false);
  const originalIv = encryptedData.slice(4, 16);

  // First pass: calculate total decrypted size
  let offset = CHUNKED_HEADER_SIZE;
  let totalDecryptedSize = 0;
  
  for (let i = 0; i < totalChunks; i++) {
    offset += 4; // skip chunk index
    const encryptedChunkLength = view.getUint32(offset, false);
    offset += 4;
    totalDecryptedSize += encryptedChunkLength - AES_AUTH_TAG_SIZE;
    offset += encryptedChunkLength;
  }

  // Second pass: decrypt all chunks
  const output = new Uint8Array(totalDecryptedSize);
  let outputOffset = 0;
  offset = CHUNKED_HEADER_SIZE;
  let bytesProcessed = 0;

  for (let i = 0; i < totalChunks; i++) {
    const chunkIndex = view.getUint32(offset, false);
    offset += 4;
    const encryptedChunkLength = view.getUint32(offset, false);
    offset += 4;
    const encryptedChunk = encryptedData.slice(offset, offset + encryptedChunkLength);
    offset += encryptedChunkLength;

    // Derive chunk IV
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
      bytesProcessed += decryptedChunk.byteLength;
      
      onProgress?.((bytesProcessed / totalDecryptedSize) * 100, bytesProcessed, totalDecryptedSize);
    } catch (error) {
      if (error instanceof Error) {
        throw new Error(
          `AES chunk decryption failed at chunk ${chunkIndex}: ${error.message}. ` +
            'The file may be corrupted, tampered with, or the wrong decryption key is being used.'
        );
      }
      throw error;
    }
  }

  return output;
}

/**
 * Calculate the expected encrypted size for chunked encryption.
 * 
 * @param originalSize - Original file size in bytes
 * @param chunkSize - Size of each chunk in bytes (default 1MB)
 * @returns Expected encrypted size in bytes
 */
export function getChunkedEncryptedSize(originalSize: number, chunkSize: number = DEFAULT_CHUNK_SIZE): number {
  const totalChunks = Math.ceil(originalSize / chunkSize);
  const lastChunkSize = originalSize % chunkSize || chunkSize;
  const fullChunks = totalChunks - (lastChunkSize < chunkSize ? 1 : 0);
  
  return (
    CHUNKED_HEADER_SIZE +
    (fullChunks * (CHUNK_OVERHEAD + chunkSize)) +
    (totalChunks > fullChunks ? (CHUNK_OVERHEAD + lastChunkSize) : 0)
  );
}

/**
 * Check if encrypted data is in chunked format.
 * 
 * @param encryptedData - Encrypted data to check
 * @returns True if data appears to be in chunked format
 */
export function isChunkedEncryption(encryptedData: Uint8Array): boolean {
  // Minimum size: header (16) + one chunk (8 overhead + 17 minimum data with auth tag)
  if (encryptedData.byteLength < CHUNKED_HEADER_SIZE + CHUNK_OVERHEAD + 1) {
    return false;
  }
  
  const view = new DataView(encryptedData.buffer, encryptedData.byteOffset);
  const totalChunks = view.getUint32(0, false);
  
  // Sanity check: reasonable number of chunks
  if (totalChunks === 0 || totalChunks > 1000000) {
    return false;
  }
  
  // Check if first chunk index is 0
  const firstChunkIndex = view.getUint32(CHUNKED_HEADER_SIZE, false);
  return firstChunkIndex === 0;
}

let litClient: LitClient | null = null;

let authManager: any = null;
let initPromise: Promise<LitClient> | null = null;

const NETWORK_CONFIGS: Record<string, typeof naga> = {
  'naga': naga,  // Mainnet - works
  'naga-dev': nagaDev,  
  'naga-staging': nagaDev,  // Staging
  'datil-dev': naga,  // Map to naga for compatibility
};

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

export function getLitClient(): LitClient | null {
  return litClient;
}

export function getAuthManager(): any | null {
  return authManager;
}

export function isLitClientConnected(): boolean {
  return litClient !== null && authManager !== null;
}

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

export async function hybridEncryptFile(
  file: ArrayBuffer,
  privateKey: string,
  chain: string = 'ethereum',
  onProgress?: (message: string) => void,
  network: string = 'naga'
): Promise<HybridEncryptionResult> {
  const fileData = new Uint8Array(file);
  const fileSize = fileData.byteLength;
  
  // Automatically use chunked encryption for files larger than threshold
  if (fileSize > CHUNKED_THRESHOLD) {
    onProgress?.(`Large file detected (${(fileSize / (1024 * 1024)).toFixed(1)}MB), using chunked encryption...`);
    
    // Convert message-based progress to percentage-based
    const result = await hybridEncryptFileChunked(
      file,
      privateKey,
      chain,
      (percent, bytesProcessed, totalBytes) => {
        onProgress?.(`Encrypting: ${percent.toFixed(1)}% (${(bytesProcessed / (1024 * 1024)).toFixed(1)}MB / ${(totalBytes / (1024 * 1024)).toFixed(1)}MB)`);
      },
      DEFAULT_CHUNK_SIZE,
      network
    );
    
    return { encryptedFile: result.encryptedFile, metadata: result.metadata };
  }

  onProgress?.('Generating encryption key...');

  // Step 1: Generate local AES key and IV
  const aesKey = generateAESKey();
  const iv = generateIV();

  // Step 2: Read file data
  onProgress?.('Reading file...');

  // Step 3: Encrypt file locally with AES
  onProgress?.('Encrypting file locally (AES-256-GCM)...');
  const encryptedFile = await aesEncrypt(fileData, aesKey, iv);

  // Step 4: Calculate hash of original file
  const originalHash = await sha256Hash(fileData);

  // Step 5: Initialize Lit client and encrypt AES key
  onProgress?.('Initializing Lit Protocol...');
  const client = await initLitClient(network);
  const walletAddress = getWalletAddressFromPrivateKey(privateKey);

  onProgress?.('Encrypting key with Lit Protocol...');
  const accessControlConditions = createOwnerOnlyAccessControlConditions(walletAddress);
  const unifiedAccessControlConditions = toUnifiedAccessControlConditions(accessControlConditions);

  // Encrypt only the AES key with Lit (32 bytes - fast and cheap!)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const litResult = await (client as any).encrypt({
    dataToEncrypt: aesKey,
    unifiedAccessControlConditions,
    chain,
  });

  // Step 6: Construct metadata
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

  onProgress?.('Encryption complete');

  // Clear sensitive key from memory
  aesKey.fill(0);

  return { encryptedFile, metadata };
}

export async function hybridDecryptFile(
  encryptedFile: Uint8Array,
  metadata: HybridEncryptionMetadata,
  privateKey: string,
  onProgress?: (message: string) => void,
  network: string = 'naga'
): Promise<Uint8Array> {
  // Validate metadata version
  if (metadata.version !== 'hybrid-v1') {
    throw new Error(
      `Unsupported encryption version: ${metadata.version}. ` + 'Only hybrid-v1 is supported.'
    );
  }

  // Automatically detect and handle chunked encryption
  if (isChunkedEncryption(encryptedFile)) {
    onProgress?.('Chunked encryption detected, using chunked decryption...');
    
    const result = await hybridDecryptFileChunked(
      encryptedFile,
      metadata,
      privateKey,
      (percent, bytesProcessed, totalBytes) => {
        onProgress?.(`Decrypting: ${percent.toFixed(1)}% (${(bytesProcessed / (1024 * 1024)).toFixed(1)}MB / ${(totalBytes / (1024 * 1024)).toFixed(1)}MB)`);
      },
      network
    );
    
    return result.data;
  }

  onProgress?.('Initializing Lit Protocol...');
  
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
  
  const client = await initLitClient(network);

  onProgress?.('Authenticating...');
  const authContext = await getAuthContext(privateKey, metadata.chain);

  onProgress?.('Decrypting encryption key...');
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
    // Decrypt file locally with AES
    onProgress?.('Decrypting file locally...');
    const iv = new Uint8Array(base64ToArrayBuffer(metadata.iv));
    const decryptedData = await aesDecrypt(encryptedFile, aesKey, iv);

    // Verify hash if available
    if (metadata.originalHash) {
      const computedHash = await sha256Hash(decryptedData);
      if (computedHash !== metadata.originalHash) {
        throw new Error(
          'File integrity check failed. The file may have been corrupted or tampered with.'
        );
      }
    }

    onProgress?.('Decryption complete');

    return decryptedData;
  } finally {
    // Clear sensitive key from memory
    aesKey.fill(0);
  }
}

/**
 * Encrypt a file using hybrid encryption with chunked processing for large files.
 * 
 * This function:
 * 1. Generates a random AES-256 key
 * 2. Encrypts the file in chunks using AES-GCM (low memory usage)
 * 3. Encrypts the AES key using Lit Protocol BLS-IBE
 * 4. Returns encrypted file + metadata
 * 
 * Benefits:
 * - Only 32 bytes sent to Lit nodes (the AES key)
 * - File encryption is hardware accelerated
 * - Low memory usage - processes file in chunks
 * - Precise progress reporting for pipeline integration
 * 
 * @param file - File or ArrayBuffer to encrypt
 * @param privateKey - Private key for access control
 * @param chain - Blockchain chain (default: ethereum)
 * @param onProgress - Progress callback with precise percentage
 * @param chunkSize - Size of each chunk in bytes (default: 1MB)
 * @param network - Lit network (default: naga)
 * @returns Encrypted file and chunked metadata
 */
export async function hybridEncryptFileChunked(
  file: ArrayBuffer,
  privateKey: string,
  chain: string = 'ethereum',
  onProgress?: EncryptionProgressCallback,
  chunkSize: number = DEFAULT_CHUNK_SIZE,
  network: string = 'naga'
): Promise<{ encryptedFile: Uint8Array; metadata: ChunkedEncryptionMetadata }> {
  // Step 1: Generate local AES key and IV
  const aesKey = generateAESKey();
  const iv = generateIV();

  // Step 2: Read file data
  const fileData = new Uint8Array(file);
  const totalBytes = fileData.byteLength;
  const totalChunks = Math.ceil(totalBytes / chunkSize);

  // Step 3: Encrypt file in chunks with progress reporting
  onProgress?.(0, 0, totalBytes);
  const encryptedFile = await aesEncryptChunked(fileData, aesKey, iv, onProgress, chunkSize);

  // Step 4: Calculate hash of original file
  const originalHash = await sha256Hash(fileData);

  // Step 5: Initialize Lit client and encrypt AES key
  const client = await initLitClient(network);
  const walletAddress = getWalletAddressFromPrivateKey(privateKey);

  const accessControlConditions = createOwnerOnlyAccessControlConditions(walletAddress);
  const unifiedAccessControlConditions = toUnifiedAccessControlConditions(accessControlConditions);

  // Encrypt only the AES key with Lit (32 bytes - fast and cheap!)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const litResult = await (client as any).encrypt({
    dataToEncrypt: aesKey,
    unifiedAccessControlConditions,
    chain,
  });

  // Step 6: Construct chunked metadata
  const metadata: ChunkedEncryptionMetadata = {
    version: 'hybrid-v1',
    encryptedKey: litResult.ciphertext,
    keyHash: litResult.dataToEncryptHash,
    iv: arrayBufferToBase64(iv),
    algorithm: 'AES-GCM',
    keyLength: 256,
    accessControlConditions,
    chain,
    originalSize: totalBytes,
    originalHash,
    chunked: true,
    totalChunks,
    chunkSize,
  };

  // Clear sensitive key from memory
  aesKey.fill(0);

  return { encryptedFile, metadata };
}

/** Result type for chunked hybrid decryption */
export interface ChunkedDecryptionResult {
  /** Decrypted file data */
  data: Uint8Array;
  /** Whether the file was in chunked format */
  wasChunked: boolean;
}

/**
 * Decrypt a file using hybrid encryption with automatic chunked format detection.
 * 
 * This function:
 * 1. Decrypts the AES key from Lit Protocol
 * 2. Detects if the file was encrypted with chunked format
 * 3. Decrypts the file locally using AES-GCM (chunked or standard)
 * 4. Returns decrypted file with format info
 * 
 * @param encryptedFile - AES-encrypted file data
 * @param metadata - Hybrid encryption metadata
 * @param privateKey - Private key for authentication
 * @param onProgress - Optional progress callback with precise percentage
 * @param network - Lit network (default: naga)
 * @returns Decrypted file and format info
 */
export async function hybridDecryptFileChunked(
  encryptedFile: Uint8Array,
  metadata: HybridEncryptionMetadata | ChunkedEncryptionMetadata,
  privateKey: string,
  onProgress?: EncryptionProgressCallback,
  network: string = 'naga'
): Promise<ChunkedDecryptionResult> {
  // Validate metadata version
  if (metadata.version !== 'hybrid-v1') {
    throw new Error(
      `Unsupported encryption version: ${metadata.version}. Only hybrid-v1 is supported.`
    );
  }

  // Verify payment setup before attempting decryption (mainnet only)
  try {
    await verifyPaymentSetup(privateKey, network);
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.warn('[Lit Payment] Payment verification warning:', errorMessage);
  }

  const client = await initLitClient(network);

  const authContext = await getAuthContext(privateKey, metadata.chain);

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
    const iv = new Uint8Array(base64ToArrayBuffer(metadata.iv));
    let decryptedData: Uint8Array;
    let wasChunked = false;

    // Detect if file is in chunked format
    if (isChunkedEncryption(encryptedFile)) {
      wasChunked = true;
      decryptedData = await aesDecryptChunked(encryptedFile, aesKey, onProgress);
    } else {
      // Standard single-chunk decryption
      decryptedData = await aesDecrypt(encryptedFile, aesKey, iv);
      onProgress?.(100, decryptedData.byteLength, decryptedData.byteLength);
    }

    // Verify hash if available
    if (metadata.originalHash) {
      const computedHash = await sha256Hash(decryptedData);
      if (computedHash !== metadata.originalHash) {
        throw new Error(
          'File integrity check failed. The file may have been corrupted or tampered with.'
        );
      }
    }

    return { data: decryptedData, wasChunked };
  } finally {
    // Clear sensitive key from memory
    aesKey.fill(0);
  }
}

/**
 * Type guard to check if metadata is for chunked encryption.
 */
export function isChunkedMetadata(
  metadata: HybridEncryptionMetadata | ChunkedEncryptionMetadata
): metadata is ChunkedEncryptionMetadata {
  return (metadata as ChunkedEncryptionMetadata).chunked === true;
}

/**
 * Check if a file size would trigger automatic chunked encryption.
 * 
 * @param fileSize - File size in bytes
 * @returns True if the file would be encrypted with chunked processing
 */
export function willUseChunkedEncryption(fileSize: number): boolean {
  return fileSize > CHUNKED_THRESHOLD;
}

/**
 * Get the chunked encryption threshold in bytes.
 * 
 * @returns Threshold size in bytes (currently 50MB)
 */
export function getChunkedThreshold(): number {
  return CHUNKED_THRESHOLD;
}

export function serializeHybridMetadata(metadata: HybridEncryptionMetadata): string {
  return JSON.stringify(metadata);
}

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

export function getEncryptedSize(originalSize: number): number {
  return originalSize + AES_AUTH_TAG_SIZE;
}

export function getOriginalSize(metadata: HybridEncryptionMetadata): number | undefined {
  return metadata.originalSize;
}

export function estimateProcessingTime(
  fileSizeBytes: number,
  throughputMBps: number = 200
): number {
  const fileSizeMB = fileSizeBytes / (1024 * 1024);
  return (fileSizeMB / throughputMBps) * 1000; // milliseconds
}
