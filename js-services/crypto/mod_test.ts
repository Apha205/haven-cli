/**
 * Tests for crypto/mod.ts exports
 *
 * Verifies that all public APIs are properly exported from the module.
 */

import { assertEquals, assertExists } from 'jsr:@std/assert@1.0.12';

// Test imports from mod.ts
import {
  // Types
  type EvmBasicAccessControlCondition,
  type UnifiedAccessControlCondition,
  type HybridEncryptionMetadata,
  type HybridEncryptionResult,
  type ChunkedEncryptionMetadata,
  type ChunkedDecryptionResult,
  type EncryptionProgressCallback,
  type MessageProgressCallback,
  type StreamProgressCallback,
  type StreamingEncryptionResult,
  type StreamingDecryptionResult,
  type ChunkInfo,
  type StreamHeader,
  type FileStreamOptions,
  type EncryptionStreamOptions,
  type DecryptionStreamOptions,
  type EncryptedChunk,
  type DecryptedChunk,
  type AESStreamingEncryptOptions,
  type StreamingEncryptInit,
  type AESStreamingDecryptOptions,
  type SHA256StreamOptions,
  // Constants
  AES_KEY_SIZE,
  AES_IV_SIZE,
  AES_AUTH_TAG_SIZE,
  DEFAULT_CHUNK_SIZE,
  CHUNKED_THRESHOLD,
  CHUNKED_HEADER_SIZE,
  CHUNK_OVERHEAD,
  // Core AES
  generateAESKey,
  generateIV,
  aesEncrypt,
  aesDecrypt,
  aesEncryptChunked,
  aesDecryptChunked,
  getChunkedEncryptedSize,
  isChunkedEncryption,
  getEncryptedSize,
  // Streaming AES
  aesEncryptStream,
  aesEncryptStreamImmediate,
  aesDecryptStream,
  DecryptionError,
  // Access Control
  normalizePrivateKey,
  getWalletAddressFromPrivateKey,
  createOwnerOnlyAccessControlConditions,
  toUnifiedAccessControlConditions,
  // Lit Client
  initLitClient,
  disconnectLitClient,
  getLitClient,
  getAuthManager,
  isLitClientConnected,
  encryptWithLit,
  decryptWithLit,
  encryptAesKeyWithLit,
  // Utilities
  arrayBufferToBase64,
  base64ToArrayBuffer,
  sha256Hash,
  secureClear,
  // Streaming Utilities
  sha256HashStream,
  sha256HashStreamAccumulated,
} from './mod.ts';

// ============================================================================
// Type Exports Tests
// ============================================================================

Deno.test('mod.ts exports AES key size constant', () => {
  assertEquals(AES_KEY_SIZE, 32);
});

Deno.test('mod.ts exports AES IV size constant', () => {
  assertEquals(AES_IV_SIZE, 12);
});

Deno.test('mod.ts exports AES auth tag size constant', () => {
  assertEquals(AES_AUTH_TAG_SIZE, 16);
});

Deno.test('mod.ts exports default chunk size constant', () => {
  assertEquals(DEFAULT_CHUNK_SIZE, 1024 * 1024);
});

Deno.test('mod.ts exports chunked threshold constant', () => {
  assertEquals(CHUNKED_THRESHOLD, 50 * 1024 * 1024);
});

Deno.test('mod.ts exports chunked header size constant', () => {
  assertEquals(CHUNKED_HEADER_SIZE, 16);
});

Deno.test('mod.ts exports chunk overhead constant', () => {
  assertEquals(CHUNK_OVERHEAD, 24);
});

// ============================================================================
// Core AES Functions Tests
// ============================================================================

Deno.test('mod.ts exports generateAESKey function', () => {
  assertEquals(typeof generateAESKey, 'function');
  const key = generateAESKey();
  assertEquals(key instanceof Uint8Array, true);
  assertEquals(key.length, 32);
});

Deno.test('mod.ts exports generateIV function', () => {
  assertEquals(typeof generateIV, 'function');
  const iv = generateIV();
  assertEquals(iv instanceof Uint8Array, true);
  assertEquals(iv.length, 12);
});

Deno.test('mod.ts exports aesEncrypt function', () => {
  assertEquals(typeof aesEncrypt, 'function');
});

Deno.test('mod.ts exports aesDecrypt function', () => {
  assertEquals(typeof aesDecrypt, 'function');
});

Deno.test('mod.ts exports aesEncryptChunked function', () => {
  assertEquals(typeof aesEncryptChunked, 'function');
});

Deno.test('mod.ts exports aesDecryptChunked function', () => {
  assertEquals(typeof aesDecryptChunked, 'function');
});

Deno.test('mod.ts exports getChunkedEncryptedSize function', () => {
  assertEquals(typeof getChunkedEncryptedSize, 'function');
  const size = getChunkedEncryptedSize(1024);
  assertEquals(typeof size, 'number');
  assertEquals(size > 1024, true);
});

Deno.test('mod.ts exports isChunkedEncryption function', () => {
  assertEquals(typeof isChunkedEncryption, 'function');
});

Deno.test('mod.ts exports getEncryptedSize function', () => {
  assertEquals(typeof getEncryptedSize, 'function');
  const size = getEncryptedSize(1024);
  assertEquals(size, 1024 + 16); // Original size + auth tag
});

// ============================================================================
// Streaming AES Functions Tests
// ============================================================================

Deno.test('mod.ts exports aesEncryptStream function', () => {
  assertEquals(typeof aesEncryptStream, 'function');
});

Deno.test('mod.ts exports aesEncryptStreamImmediate function', () => {
  assertEquals(typeof aesEncryptStreamImmediate, 'function');
});

Deno.test('mod.ts exports aesDecryptStream function', () => {
  assertEquals(typeof aesDecryptStream, 'function');
});

Deno.test('mod.ts exports DecryptionError class', () => {
  assertEquals(typeof DecryptionError, 'function');
  const error = new DecryptionError('test error');
  assertEquals(error instanceof Error, true);
  assertEquals(error.name, 'DecryptionError');
  assertEquals(error.message, 'test error');
});

// ============================================================================
// Access Control Functions Tests
// ============================================================================

Deno.test('mod.ts exports normalizePrivateKey function', () => {
  assertEquals(typeof normalizePrivateKey, 'function');
});

Deno.test('mod.ts exports getWalletAddressFromPrivateKey function', () => {
  assertEquals(typeof getWalletAddressFromPrivateKey, 'function');
});

Deno.test('mod.ts exports createOwnerOnlyAccessControlConditions function', () => {
  assertEquals(typeof createOwnerOnlyAccessControlConditions, 'function');
});

Deno.test('mod.ts exports toUnifiedAccessControlConditions function', () => {
  assertEquals(typeof toUnifiedAccessControlConditions, 'function');
});

// ============================================================================
// Lit Client Functions Tests
// ============================================================================

Deno.test('mod.ts exports initLitClient function', () => {
  assertEquals(typeof initLitClient, 'function');
});

Deno.test('mod.ts exports disconnectLitClient function', () => {
  assertEquals(typeof disconnectLitClient, 'function');
});

Deno.test('mod.ts exports getLitClient function', () => {
  assertEquals(typeof getLitClient, 'function');
});

Deno.test('mod.ts exports getAuthManager function', () => {
  assertEquals(typeof getAuthManager, 'function');
});

Deno.test('mod.ts exports isLitClientConnected function', () => {
  assertEquals(typeof isLitClientConnected, 'function');
});

Deno.test('mod.ts exports encryptWithLit function', () => {
  assertEquals(typeof encryptWithLit, 'function');
});

Deno.test('mod.ts exports decryptWithLit function', () => {
  assertEquals(typeof decryptWithLit, 'function');
});

Deno.test('mod.ts exports encryptAesKeyWithLit function', () => {
  assertEquals(typeof encryptAesKeyWithLit, 'function');
});

// ============================================================================
// Utility Functions Tests
// ============================================================================

Deno.test('mod.ts exports arrayBufferToBase64 function', () => {
  assertEquals(typeof arrayBufferToBase64, 'function');
});

Deno.test('mod.ts exports base64ToArrayBuffer function', () => {
  assertEquals(typeof base64ToArrayBuffer, 'function');
});

Deno.test('mod.ts exports sha256Hash function', () => {
  assertEquals(typeof sha256Hash, 'function');
});

Deno.test('mod.ts exports secureClear function', () => {
  assertEquals(typeof secureClear, 'function');
});

// ============================================================================
// Streaming Utility Functions Tests
// ============================================================================

Deno.test('mod.ts exports sha256HashStream function', () => {
  assertEquals(typeof sha256HashStream, 'function');
});

Deno.test('mod.ts exports sha256HashStreamAccumulated function', () => {
  assertEquals(typeof sha256HashStreamAccumulated, 'function');
});

// ============================================================================
// Integration Tests
// ============================================================================

Deno.test('mod.ts - roundtrip: aesEncrypt / aesDecrypt', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const originalData = new TextEncoder().encode('Hello, World!');

  const encrypted = await aesEncrypt(originalData, key, iv);
  const decrypted = await aesDecrypt(encrypted, key, iv);

  assertEquals(decrypted, originalData);
});

Deno.test('mod.ts - roundtrip: aesEncryptChunked / aesDecryptChunked', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const originalData = new TextEncoder().encode('This is a test message for chunked encryption!'.repeat(100));

  const encrypted = await aesEncryptChunked(originalData, key, iv);
  const decrypted = await aesDecryptChunked(encrypted, key);

  assertEquals(decrypted, originalData);
});

Deno.test('mod.ts - aesEncryptStream produces valid output', async () => {
  const key = generateAESKey();
  const originalData = new TextEncoder().encode('Streaming test data!'.repeat(50));

  // Create a simple async iterable
  async function* dataStream(): AsyncGenerator<Uint8Array> {
    yield originalData;
  }

  const chunks: Uint8Array[] = [];
  for await (const chunk of aesEncryptStream(dataStream(), key)) {
    chunks.push(chunk);
  }

  // Should have at least the header chunk
  assertEquals(chunks.length >= 1, true);
  // First chunk should be the header (16 bytes)
  assertEquals(chunks[0].length, 16);
});

Deno.test('mod.ts - aesDecryptStream decrypts aesEncryptStream output', async () => {
  const key = generateAESKey();
  const originalData = new TextEncoder().encode('Streaming roundtrip test!'.repeat(50));

  // Encrypt
  async function* dataStream(): AsyncGenerator<Uint8Array> {
    yield originalData;
  }

  const encryptedChunks: Uint8Array[] = [];
  for await (const chunk of aesEncryptStream(dataStream(), key)) {
    encryptedChunks.push(chunk);
  }

  // Decrypt
  async function* encryptedStream(): AsyncGenerator<Uint8Array> {
    for (const chunk of encryptedChunks) {
      yield chunk;
    }
  }

  const decryptedChunks: Uint8Array[] = [];
  for await (const chunk of aesDecryptStream(encryptedStream(), key)) {
    decryptedChunks.push(chunk);
  }

  // Combine decrypted chunks
  const totalLength = decryptedChunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const decrypted = new Uint8Array(totalLength);
  let offset = 0;
  for (const chunk of decryptedChunks) {
    decrypted.set(chunk, offset);
    offset += chunk.length;
  }

  assertEquals(decrypted, originalData);
});

Deno.test('mod.ts - sha256Hash computes correct hash', async () => {
  const data = new TextEncoder().encode('Hello, World!');
  const hash = await sha256Hash(data);

  assertEquals(typeof hash, 'string');
  assertEquals(hash.length, 64); // Hex-encoded SHA-256 is 64 characters
});

Deno.test('mod.ts - sha256HashStream computes same hash as sha256Hash', async () => {
  const data = new TextEncoder().encode('Streaming hash test!'.repeat(100));

  // Regular hash
  const regularHash = await sha256Hash(data);

  // Streaming hash
  async function* dataStream(): AsyncGenerator<Uint8Array> {
    yield data;
  }
  const streamHash = await sha256HashStream(dataStream());

  assertEquals(streamHash, regularHash);
});

Deno.test('mod.ts - arrayBufferToBase64 and base64ToArrayBuffer roundtrip', () => {
  const original = new Uint8Array([1, 2, 3, 4, 5, 255, 254, 253]);
  const base64 = arrayBufferToBase64(original);
  const decoded = base64ToArrayBuffer(base64);

  assertEquals(new Uint8Array(decoded), original);
});

Deno.test('mod.ts - isChunkedEncryption identifies chunked format', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new TextEncoder().encode('Test data');

  const chunked = await aesEncryptChunked(data, key, iv);
  const regular = await aesEncrypt(data, key, iv);

  assertEquals(isChunkedEncryption(chunked), true);
  assertEquals(isChunkedEncryption(regular), false);
});

Deno.test('mod.ts - getChunkedEncryptedSize returns correct size', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new TextEncoder().encode('x'.repeat(5000));

  const expectedSize = getChunkedEncryptedSize(data.length);
  const encrypted = await aesEncryptChunked(data, key, iv);

  assertEquals(encrypted.length, expectedSize);
});

Deno.test('mod.ts - DecryptionError can be caught as Error', () => {
  try {
    throw new DecryptionError('test');
  } catch (e) {
    assertEquals(e instanceof DecryptionError, true);
    assertEquals(e instanceof Error, true);
  }
});
