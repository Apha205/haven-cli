/**
 * AES-256-GCM encryption functions for hybrid encryption system.
 */

import {
  AES_KEY_SIZE,
  AES_IV_SIZE,
  AES_AUTH_TAG_SIZE,
  DEFAULT_CHUNK_SIZE,
  CHUNKED_HEADER_SIZE,
  CHUNK_OVERHEAD,
} from './constants.ts';
import type { EncryptionProgressCallback } from './types.ts';

/**
 * Generate a random AES-256 key.
 */
export function generateAESKey(): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(AES_KEY_SIZE));
}

/**
 * Generate a random AES-GCM IV.
 */
export function generateIV(): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(AES_IV_SIZE));
}

/**
 * Import raw AES key for use with Web Crypto API.
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
 * Encrypt data using AES-256-GCM.
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
 * Decrypt data using AES-256-GCM.
 */
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
 * Derive a chunk IV by XORing the last 4 bytes with the chunk index.
 */
function deriveChunkIv(baseIv: Uint8Array, chunkIndex: number): Uint8Array {
  const chunkIv = new Uint8Array(baseIv);
  const chunkIndexBytes = new Uint8Array(4);
  new DataView(chunkIndexBytes.buffer).setUint32(0, chunkIndex, false);
  chunkIv[8] ^= chunkIndexBytes[0];
  chunkIv[9] ^= chunkIndexBytes[1];
  chunkIv[10] ^= chunkIndexBytes[2];
  chunkIv[11] ^= chunkIndexBytes[3];
  return chunkIv;
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
  const lastChunkSize = totalBytes % chunkSize || chunkSize;
  const fullChunks = totalChunks - (lastChunkSize < chunkSize ? 1 : 0);
  
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

    const chunkIv = deriveChunkIv(iv, chunkIndex);

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

    const chunkIv = deriveChunkIv(originalIv, chunkIndex);

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

/**
 * Get the encrypted size for standard (non-chunked) encryption.
 */
export function getEncryptedSize(originalSize: number): number {
  return originalSize + AES_AUTH_TAG_SIZE;
}
