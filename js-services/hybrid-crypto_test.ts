/**
 * Tests for Hybrid Crypto - Chunked Encryption
 *
 * These tests verify the chunked AES encryption/decryption including:
 * - Roundtrip encryption/decryption
 * - Progress callback invocation
 * - Large file handling
 * - IV derivation per chunk
 */

import { assertEquals, assertExists } from 'https://deno.land/std@0.200.0/testing/asserts.ts';
import {
  generateAESKey,
  generateIV,
  aesEncrypt,
  aesDecrypt,
  aesEncryptChunked,
  aesDecryptChunked,
} from './hybrid-crypto.ts';

// Test constants
const TEST_CHUNK_SIZE = 1024; // 1KB chunks for testing

Deno.test('aesEncryptChunked - encrypts small data (less than chunk size)', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new TextEncoder().encode('Hello, World!');

  const encrypted = await aesEncryptChunked(data, key, iv, undefined, TEST_CHUNK_SIZE);
  const decrypted = await aesDecryptChunked(encrypted, key);

  assertEquals(decrypted, data);
});

Deno.test('aesEncryptChunked - encrypts data exactly one chunk', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new Uint8Array(TEST_CHUNK_SIZE);
  crypto.getRandomValues(data);

  const encrypted = await aesEncryptChunked(data, key, iv, undefined, TEST_CHUNK_SIZE);
  const decrypted = await aesDecryptChunked(encrypted, key);

  assertEquals(decrypted, data);
});

Deno.test('aesEncryptChunked - encrypts multiple chunks', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new Uint8Array(TEST_CHUNK_SIZE * 3.5); // 3.5 chunks
  crypto.getRandomValues(data);

  const encrypted = await aesEncryptChunked(data, key, iv, undefined, TEST_CHUNK_SIZE);
  const decrypted = await aesDecryptChunked(encrypted, key);

  assertEquals(decrypted, data);
});

Deno.test('aesEncryptChunked - encrypts large data', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new Uint8Array(TEST_CHUNK_SIZE * 100); // 100 chunks
  crypto.getRandomValues(data);

  const encrypted = await aesEncryptChunked(data, key, iv, undefined, TEST_CHUNK_SIZE);
  const decrypted = await aesDecryptChunked(encrypted, key);

  assertEquals(decrypted, data);
});

Deno.test('aesEncryptChunked - progress callback is invoked', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new Uint8Array(TEST_CHUNK_SIZE * 5);
  crypto.getRandomValues(data);

  const progressCalls: Array<{ percent: number; bytesProcessed: number; totalBytes: number }> = [];

  await aesEncryptChunked(
    data,
    key,
    iv,
    (percent, bytesProcessed, totalBytes) => {
      progressCalls.push({ percent, bytesProcessed, totalBytes });
    },
    TEST_CHUNK_SIZE
  );

  // Should have progress calls for each chunk plus initial 0%
  assertEquals(progressCalls.length >= 5, true, 'Should have at least 5 progress calls');

  // First call should be 0%
  assertEquals(progressCalls[0].percent, 0);

  // Last call should be 100%
  const lastCall = progressCalls[progressCalls.length - 1];
  assertEquals(lastCall.percent, 100);
  assertEquals(lastCall.bytesProcessed, data.byteLength);
  assertEquals(lastCall.totalBytes, data.byteLength);
});

Deno.test('aesEncryptChunked - progress callback reports correct bytes', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const chunkCount = 3;
  const data = new Uint8Array(TEST_CHUNK_SIZE * chunkCount);
  crypto.getRandomValues(data);

  const progressCalls: Array<{ percent: number; bytesProcessed: number }> = [];

  await aesEncryptChunked(
    data,
    key,
    iv,
    (percent, bytesProcessed, _totalBytes) => {
      progressCalls.push({ percent, bytesProcessed });
    },
    TEST_CHUNK_SIZE
  );

  // Check that bytes processed increases monotonically
  let lastBytes = 0;
  for (const call of progressCalls) {
    assertEquals(call.bytesProcessed >= lastBytes, true, 'Bytes should increase monotonically');
    lastBytes = call.bytesProcessed;
  }

  // Final bytes should equal total
  assertEquals(progressCalls[progressCalls.length - 1].bytesProcessed, data.byteLength);
});

Deno.test('aesDecryptChunked - fails with wrong key', async () => {
  const key1 = generateAESKey();
  const key2 = generateAESKey(); // Different key
  const iv = generateIV();
  const data = new TextEncoder().encode('Secret message');

  const encrypted = await aesEncryptChunked(data, key1, iv, undefined, TEST_CHUNK_SIZE);

  // Decryption with wrong key should fail
  let error: Error | null = null;
  try {
    await aesDecryptChunked(encrypted, key2);
  } catch (e) {
    error = e instanceof Error ? e : new Error(String(e));
  }

  assertExists(error, 'Should throw error with wrong key');
  assertEquals(error?.message.includes('decryption failed'), true);
});

Deno.test('aesEncryptChunked - encrypted size is larger than original', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new Uint8Array(TEST_CHUNK_SIZE * 3);
  crypto.getRandomValues(data);

  const encrypted = await aesEncryptChunked(data, key, iv, undefined, TEST_CHUNK_SIZE);

  // Encrypted size should be larger due to headers and auth tags
  assertEquals(encrypted.byteLength > data.byteLength, true, 'Encrypted should be larger');
});

Deno.test('aesEncryptChunked - handles empty data', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new Uint8Array(0);

  const encrypted = await aesEncryptChunked(data, key, iv, undefined, TEST_CHUNK_SIZE);
  const decrypted = await aesDecryptChunked(encrypted, key);

  // Empty data should still work (creates one empty chunk)
  assertEquals(decrypted.byteLength, 0);
});

Deno.test('aesEncryptChunked - handles single byte', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new Uint8Array([42]);

  const encrypted = await aesEncryptChunked(data, key, iv, undefined, TEST_CHUNK_SIZE);
  const decrypted = await aesDecryptChunked(encrypted, key);

  assertEquals(decrypted, data);
});

Deno.test('aesEncryptChunked - chunked output differs from non-chunked format', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new Uint8Array(TEST_CHUNK_SIZE * 2);
  crypto.getRandomValues(data);

  const encryptedChunked = await aesEncryptChunked(data, key, iv, undefined, TEST_CHUNK_SIZE);
  const encryptedNormal = await aesEncrypt(data, key, iv);

  // The formats should be different (chunked has headers, normal doesn't)
  assertEquals(encryptedChunked.byteLength > encryptedNormal.byteLength, true, 'Chunked format should be larger');

  // But both should decrypt to the same data (using appropriate decrypt function)
  const decryptedChunked = await aesDecryptChunked(encryptedChunked, key);
  const decryptedNormal = await aesDecrypt(encryptedNormal, key, iv);

  assertEquals(decryptedChunked, data);
  assertEquals(decryptedNormal, data);
});

Deno.test('aesEncryptChunked - progress percent increases monotonically', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new Uint8Array(TEST_CHUNK_SIZE * 10);
  crypto.getRandomValues(data);

  const percents: number[] = [];

  await aesEncryptChunked(
    data,
    key,
    iv,
    (percent, _bytesProcessed, _totalBytes) => {
      percents.push(percent);
    },
    TEST_CHUNK_SIZE
  );

  // Check that percent increases (or stays same for last chunk)
  for (let i = 1; i < percents.length; i++) {
    assertEquals(
      percents[i] >= percents[i - 1],
      true,
      `Percent should increase: ${percents[i - 1]} -> ${percents[i]}`
    );
  }

  // First should be 0, last should be 100
  assertEquals(percents[0], 0);
  assertEquals(percents[percents.length - 1], 100);
});
