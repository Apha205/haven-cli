/**
 * Hybrid Encryption System
 * 
 * Combines AES-256-GCM for fast local file encryption with Lit Protocol
 * BLS-IBE for secure key management and access control.
 * 
 * Architecture:
 * - crypto/types.ts - Type definitions
 * - crypto/constants.ts - Configuration constants
 * - crypto/utils.ts - Utility functions
 * - crypto/aes.ts - AES encryption/decryption
 * - crypto/access-control.ts - Access control helpers
 * - crypto/lit-client.ts - Lit Protocol client management
 */

// Re-export types for public API
export type {
  EvmBasicAccessControlCondition,
  UnifiedAccessControlCondition,
  HybridEncryptionMetadata,
  HybridEncryptionResult,
  ChunkedEncryptionMetadata,
  ChunkedDecryptionResult,
  EncryptionProgressCallback,
  MessageProgressCallback,
} from './crypto/types.ts';

// Re-export constants for public API
export {
  AES_KEY_SIZE,
  AES_IV_SIZE,
  AES_AUTH_TAG_SIZE,
  DEFAULT_CHUNK_SIZE,
  CHUNKED_THRESHOLD,
  CHUNKED_HEADER_SIZE,
  CHUNK_OVERHEAD,
} from './crypto/constants.ts';

// Re-export AES functions for public API
export {
  generateAESKey,
  generateIV,
  aesEncrypt,
  aesDecrypt,
  aesEncryptChunked,
  aesDecryptChunked,
  getChunkedEncryptedSize,
  isChunkedEncryption,
  getEncryptedSize,
} from './crypto/aes.ts';

// Re-export Lit client functions for public API
export {
  initLitClient,
  disconnectLitClient,
  getLitClient,
  getAuthManager,
  isLitClientConnected,
} from './crypto/lit-client.ts';

// Re-export access control functions for public API
export {
  normalizePrivateKey,
  getWalletAddressFromPrivateKey,
  createOwnerOnlyAccessControlConditions,
  toUnifiedAccessControlConditions,
} from './crypto/access-control.ts';

// Re-export utility functions for public API
export {
  arrayBufferToBase64,
  base64ToArrayBuffer,
  sha256Hash,
} from './crypto/utils.ts';

// Import for internal use
import { CHUNKED_THRESHOLD, DEFAULT_CHUNK_SIZE } from './crypto/constants.ts';
import { arrayBufferToBase64, base64ToArrayBuffer, sha256Hash } from './crypto/utils.ts';
import {
  generateAESKey,
  generateIV,
  aesEncrypt,
  aesDecrypt,
  aesEncryptChunked,
  aesDecryptChunked,
  isChunkedEncryption,
} from './crypto/aes.ts';
import { getWalletAddressFromPrivateKey, createOwnerOnlyAccessControlConditions } from './crypto/access-control.ts';
import { initLitClient, encryptAesKeyWithLit, decryptWithLit } from './crypto/lit-client.ts';
import type {
  HybridEncryptionMetadata,
  HybridEncryptionResult,
  ChunkedEncryptionMetadata,
  ChunkedDecryptionResult,
  EncryptionProgressCallback,
  MessageProgressCallback,
} from './crypto/types.ts';

/**
 * Encrypt a file using hybrid encryption.
 * 
 * This function:
 * 1. Generates a random AES-256 key
 * 2. Encrypts the file locally with AES-GCM
 * 3. Encrypts the AES key using Lit Protocol BLS-IBE
 * 4. Returns encrypted file + metadata
 * 
 * For files larger than 50MB, automatically uses chunked encryption.
 */
export async function hybridEncryptFile(
  file: ArrayBuffer,
  privateKey: string,
  chain: string = 'ethereum',
  onProgress?: MessageProgressCallback,
  network: string = 'naga'
): Promise<HybridEncryptionResult> {
  const fileData = new Uint8Array(file);
  const fileSize = fileData.byteLength;
  
  // Automatically use chunked encryption for files larger than threshold
  if (fileSize > CHUNKED_THRESHOLD) {
    onProgress?.(`Large file detected (${(fileSize / (1024 * 1024)).toFixed(1)}MB), using chunked encryption...`);
    
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
  const walletAddress = getWalletAddressFromPrivateKey(privateKey);

  onProgress?.('Encrypting key with Lit Protocol...');
  const accessControlConditions = createOwnerOnlyAccessControlConditions(walletAddress, chain as any);
  
  const litResult = await encryptAesKeyWithLit(aesKey, privateKey, chain, network);

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

/**
 * Decrypt a file using hybrid encryption.
 * 
 * This function:
 * 1. Decrypts the AES key from Lit Protocol
 * 2. Decrypts the file locally with AES-GCM
 * 3. Returns decrypted file data
 * 
 * Automatically detects and handles chunked encryption format.
 */
export async function hybridDecryptFile(
  encryptedFile: Uint8Array,
  metadata: HybridEncryptionMetadata,
  privateKey: string,
  onProgress?: MessageProgressCallback,
  network: string = 'naga'
): Promise<Uint8Array> {
  // Validate metadata version
  if (metadata.version !== 'hybrid-v1') {
    throw new Error(
      `Unsupported encryption version: ${metadata.version}. Only hybrid-v1 is supported.`
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
  
  const aesKey = await decryptWithLit(
    metadata.encryptedKey,
    metadata.keyHash,
    metadata.accessControlConditions,
    privateKey,
    metadata.chain,
    network
  );

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
  const walletAddress = getWalletAddressFromPrivateKey(privateKey);
  const accessControlConditions = createOwnerOnlyAccessControlConditions(walletAddress, chain as any);
  
  const litResult = await encryptAesKeyWithLit(aesKey, privateKey, chain, network);

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

/**
 * Decrypt a file using hybrid encryption with automatic chunked format detection.
 * 
 * This function:
 * 1. Decrypts the AES key from Lit Protocol
 * 2. Detects if the file was encrypted with chunked format
 * 3. Decrypts the file locally using AES-GCM (chunked or standard)
 * 4. Returns decrypted file with format info
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

  const aesKey = await decryptWithLit(
    metadata.encryptedKey,
    metadata.keyHash,
    metadata.accessControlConditions,
    privateKey,
    metadata.chain,
    network
  );

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

// ============================================================================
// Metadata Serialization Helpers
// ============================================================================

/**
 * Serialize hybrid encryption metadata to JSON string.
 */
export function serializeHybridMetadata(metadata: HybridEncryptionMetadata): string {
  return JSON.stringify(metadata);
}

/**
 * Deserialize hybrid encryption metadata from JSON string.
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
 * Type guard to check if an object is valid hybrid encryption metadata.
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

/**
 * Type guard to check if metadata is for chunked encryption.
 */
export function isChunkedMetadata(
  metadata: HybridEncryptionMetadata | ChunkedEncryptionMetadata
): metadata is ChunkedEncryptionMetadata {
  return (metadata as ChunkedEncryptionMetadata).chunked === true;
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Get the original file size from metadata.
 */
export function getOriginalSize(metadata: HybridEncryptionMetadata): number | undefined {
  return metadata.originalSize;
}

/**
 * Check if a file size would trigger automatic chunked encryption.
 */
export function willUseChunkedEncryption(fileSize: number): boolean {
  return fileSize > CHUNKED_THRESHOLD;
}

/**
 * Get the chunked encryption threshold in bytes.
 */
export function getChunkedThreshold(): number {
  return CHUNKED_THRESHOLD;
}

/**
 * Estimate processing time based on file size.
 * 
 * @param fileSizeBytes - File size in bytes
 * @param throughputMBps - Expected throughput in MB/s (default: 200)
 * @returns Estimated processing time in milliseconds
 */
export function estimateProcessingTime(
  fileSizeBytes: number,
  throughputMBps: number = 200
): number {
  const fileSizeMB = fileSizeBytes / (1024 * 1024);
  return (fileSizeMB / throughputMBps) * 1000; // milliseconds
}
