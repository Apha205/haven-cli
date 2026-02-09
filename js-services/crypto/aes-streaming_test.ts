/**
 * Tests for streaming AES encryption functions.
 */

import { assertEquals, assertExists, assertRejects } from 'https://deno.land/std@0.215.0/assert/mod.ts';
import {
  aesEncryptStream,
  aesEncryptStreamImmediate,
  AESStreamingEncryptOptions,
} from './aes-streaming.ts';
import { aesDecryptChunked, generateAESKey, generateIV, aesEncryptChunked } from './aes.ts';
import { AES_KEY_SIZE, AES_IV_SIZE, CHUNKED_HEADER_SIZE } from './constants.ts';

/**
 * Create an async iterable from an array of chunks.
 */
async function* createStream(chunks: Uint8Array[]): AsyncGenerator<Uint8Array> {
  for (const chunk of chunks) {
    yield chunk;
  }
}

/**
 * Collect all chunks from an async iterable into a single Uint8Array.
 */
async function collectChunks(stream: AsyncIterable<Uint8Array>): Promise<Uint8Array> {
  const chunks: Uint8Array[] = [];
  let totalLength = 0;

  for await (const chunk of stream) {
    chunks.push(chunk);
    totalLength += chunk.byteLength;
  }

  const result = new Uint8Array(totalLength);
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.byteLength;
  }

  return result;
}

Deno.test('aesEncryptStream: basic encryption with single chunk', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new TextEncoder().encode('Hello, World!');

  const stream = createStream([data]);
  const encrypted = await collectChunks(aesEncryptStream(stream, key, { iv }));

  // Should have header + at least one chunk
  assertExists(encrypted);
  assertEquals(encrypted.byteLength >= CHUNKED_HEADER_SIZE, true);

  // Verify it can be decrypted
  const decrypted = await aesDecryptChunked(encrypted, key);
  assertEquals(new TextDecoder().decode(decrypted), 'Hello, World!');
});

Deno.test('aesEncryptStream: encryption with multiple input chunks', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const chunk1 = new TextEncoder().encode('Hello, ');
  const chunk2 = new TextEncoder().encode('World!');

  const stream = createStream([chunk1, chunk2]);
  const encrypted = await collectChunks(aesEncryptStream(stream, key, { iv }));

  // Verify it can be decrypted
  const decrypted = await aesDecryptChunked(encrypted, key);
  assertEquals(new TextDecoder().decode(decrypted), 'Hello, World!');
});

Deno.test('aesEncryptStream: encryption with large data and small chunk size', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const chunkSize = 1024; // 1KB chunks

  // Create 10KB of data
  const data = new Uint8Array(10 * 1024);
  crypto.getRandomValues(data);

  const stream = createStream([data]);
  const encrypted = await collectChunks(
    aesEncryptStream(stream, key, { iv, chunkSize })
  );

  // Verify it can be decrypted
  const decrypted = await aesDecryptChunked(encrypted, key);
  assertEquals(decrypted.byteLength, data.byteLength);
  assertEquals(decrypted, data);
});

Deno.test('aesEncryptStream: encryption with multiple small input chunks', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const chunkSize = 1024; // 1KB chunks

  // Create many small input chunks that accumulate
  const inputChunks: Uint8Array[] = [];
  for (let i = 0; i < 100; i++) {
    const chunk = new Uint8Array(100);
    chunk.fill(i);
    inputChunks.push(chunk);
  }

  const stream = createStream(inputChunks);
  const encrypted = await collectChunks(
    aesEncryptStream(stream, key, { iv, chunkSize })
  );

  // Verify it can be decrypted
  const decrypted = await aesDecryptChunked(encrypted, key);

  // Reconstruct original data
  const expectedData = new Uint8Array(100 * 100);
  let offset = 0;
  for (let i = 0; i < 100; i++) {
    const chunk = new Uint8Array(100);
    chunk.fill(i);
    expectedData.set(chunk, offset);
    offset += 100;
  }

  assertEquals(decrypted, expectedData);
});

Deno.test('aesEncryptStream: matches non-streaming encryption output', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new Uint8Array(5000);
  crypto.getRandomValues(data);

  // Encrypt using streaming
  const stream = createStream([data]);
  const streamingEncrypted = await collectChunks(
    aesEncryptStream(stream, key, { iv, chunkSize: 1024 })
  );

  // Encrypt using non-streaming chunked function
  const nonStreamingEncrypted = await aesEncryptChunked(data, key, iv, undefined, 1024);

  // Both should produce the same output
  assertEquals(streamingEncrypted, nonStreamingEncrypted);
});

Deno.test('aesEncryptStream: progress callback fires correctly', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const chunkSize = 1024;
  const totalSize = 5 * 1024; // 5KB

  const progressCalls: Array<{ percent: number; bytesProcessed: number; totalBytes: number }> = [];

  const data = new Uint8Array(totalSize);
  crypto.getRandomValues(data);

  const stream = createStream([data]);
  await collectChunks(
    aesEncryptStream(stream, key, {
      iv,
      chunkSize,
      totalSize,
      onProgress: ({ percent, bytesProcessed, totalBytes }) => {
        progressCalls.push({ percent: percent ?? 0, bytesProcessed, totalBytes: totalBytes ?? 0 });
      },
    })
  );

  // Should have progress calls
  assertEquals(progressCalls.length > 0, true);

  // First call should be at 0%
  assertEquals(progressCalls[0].percent, 0);
  assertEquals(progressCalls[0].bytesProcessed, 0);
  assertEquals(progressCalls[0].totalBytes, totalSize);

  // Last call should be at 100%
  const lastCall = progressCalls[progressCalls.length - 1];
  assertEquals(lastCall.percent, 100);
  assertEquals(lastCall.bytesProcessed, totalSize);
  assertEquals(lastCall.totalBytes, totalSize);

  // Progress should be monotonically increasing
  for (let i = 1; i < progressCalls.length; i++) {
    assertEquals(progressCalls[i].bytesProcessed >= progressCalls[i - 1].bytesProcessed, true);
  }
});

Deno.test('aesEncryptStream: progress callback without totalSize', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const chunkSize = 1024;

  const progressCalls: Array<{ percent: number; bytesProcessed: number; totalBytes: number }> = [];

  const data = new Uint8Array(5 * 1024);
  crypto.getRandomValues(data);

  const stream = createStream([data]);
  await collectChunks(
    aesEncryptStream(stream, key, {
      iv,
      chunkSize,
      onProgress: ({ percent, bytesProcessed, totalBytes }) => {
        progressCalls.push({ percent: percent ?? 0, bytesProcessed, totalBytes: totalBytes ?? 0 });
      },
    })
  );

  // Should have progress calls with 0% (since total is unknown)
  assertEquals(progressCalls.length > 0, true);
  for (const call of progressCalls.slice(0, -1)) {
    assertEquals(call.percent, 0);
    assertEquals(call.totalBytes, 0);
  }

  // Last call should have the actual bytes processed
  const lastCall = progressCalls[progressCalls.length - 1];
  assertEquals(lastCall.bytesProcessed, 5 * 1024);
});

Deno.test('aesEncryptStream: auto-generates IV if not provided', async () => {
  const key = generateAESKey();
  const data = new TextEncoder().encode('Test data');

  const stream = createStream([data]);
  const encrypted = await collectChunks(aesEncryptStream(stream, key));

  // Extract IV from header
  const iv = encrypted.slice(4, 16);
  assertEquals(iv.byteLength, AES_IV_SIZE);

  // Verify it can be decrypted
  const decrypted = await aesDecryptChunked(encrypted, key);
  assertEquals(new TextDecoder().decode(decrypted), 'Test data');
});

Deno.test('aesEncryptStream: validates key size', async () => {
  const invalidKey = new Uint8Array(16); // 16 bytes, not 32
  const data = new TextEncoder().encode('Test data');

  const stream = createStream([data]);
  await assertRejects(
    async () => await collectChunks(aesEncryptStream(stream, invalidKey)),
    Error,
    'Invalid AES key size'
  );
});

Deno.test('aesEncryptStream: validates IV size', async () => {
  const key = generateAESKey();
  const invalidIV = new Uint8Array(8); // 8 bytes, not 12
  const data = new TextEncoder().encode('Test data');

  const stream = createStream([data]);
  await assertRejects(
    async () => await collectChunks(aesEncryptStream(stream, key, { iv: invalidIV })),
    Error,
    'Invalid IV size'
  );
});

Deno.test('aesEncryptStream: handles empty input', async () => {
  const key = generateAESKey();
  const iv = generateIV();

  const stream = createStream([]);
  const encrypted = await collectChunks(aesEncryptStream(stream, key, { iv }));

  // Should have header but no chunks
  assertEquals(encrypted.byteLength, CHUNKED_HEADER_SIZE);

  // Header should indicate 0 chunks
  const view = new DataView(encrypted.buffer);
  assertEquals(view.getUint32(0, false), 0);
});

Deno.test('aesEncryptStream: handles single byte input', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new Uint8Array([42]);

  const stream = createStream([data]);
  const encrypted = await collectChunks(aesEncryptStream(stream, key, { iv }));

  // Should have header + one chunk
  assertEquals(encrypted.byteLength > CHUNKED_HEADER_SIZE, true);

  // Verify it can be decrypted
  const decrypted = await aesDecryptChunked(encrypted, key);
  assertEquals(decrypted, data);
});

Deno.test('aesEncryptStream: header format is correct', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const chunkSize = 100;

  // Create data that will be split into 3 chunks
  const data = new Uint8Array(250);
  crypto.getRandomValues(data);

  const stream = createStream([data]);
  const encrypted = await collectChunks(
    aesEncryptStream(stream, key, { iv, chunkSize })
  );

  // Check header
  const view = new DataView(encrypted.buffer);
  const totalChunks = view.getUint32(0, false);
  assertEquals(totalChunks, 3); // 100 + 100 + 50 = 250

  // Check IV
  const headerIV = encrypted.slice(4, 16);
  assertEquals(headerIV, iv);

  // Check first chunk index
  const firstChunkIndex = view.getUint32(CHUNKED_HEADER_SIZE, false);
  assertEquals(firstChunkIndex, 0);
});

Deno.test('aesEncryptStream: different IVs produce different ciphertexts', async () => {
  const key = generateAESKey();
  const iv1 = generateIV();
  const iv2 = generateIV();
  const data = new TextEncoder().encode('Test data that is the same');

  const stream1 = createStream([data]);
  const encrypted1 = await collectChunks(aesEncryptStream(stream1, key, { iv: iv1 }));

  const stream2 = createStream([data]);
  const encrypted2 = await collectChunks(aesEncryptStream(stream2, key, { iv: iv2 }));

  // Ciphertexts should be different (due to different IVs)
  assertEquals(encrypted1.toString() !== encrypted2.toString(), true);

  // But both should decrypt to the same plaintext
  const decrypted1 = await aesDecryptChunked(encrypted1, key);
  const decrypted2 = await aesDecryptChunked(encrypted2, key);
  assertEquals(decrypted1, decrypted2);
});

Deno.test('aesEncryptStream: memory stays bounded with large data', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const chunkSize = 64 * 1024; // 64KB chunks
  const totalChunks = 10;

  // Track max chunk size seen
  let maxChunkSize = 0;

  async function* largeStream(): AsyncGenerator<Uint8Array> {
    for (let i = 0; i < totalChunks; i++) {
      const chunk = new Uint8Array(chunkSize);
      chunk.fill(i);
      yield chunk;
    }
  }

  let totalBytes = 0;
  for await (const chunk of aesEncryptStream(largeStream(), key, { iv, chunkSize })) {
    maxChunkSize = Math.max(maxChunkSize, chunk.byteLength);
    totalBytes += chunk.byteLength;
  }

  // Max chunk size should be bounded (header + encrypted chunk overhead)
  // Header is 16 bytes, each encrypted chunk has 8 bytes overhead + auth tag
  const expectedMaxChunkSize = CHUNKED_HEADER_SIZE + 8 + chunkSize + 16;
  assertEquals(maxChunkSize <= expectedMaxChunkSize, true);

  // Total bytes should account for all chunks
  assertEquals(totalBytes > totalChunks * chunkSize, true);
});

// ============================================================================
// Tests for aesEncryptStreamImmediate
// ============================================================================

Deno.test('aesEncryptStreamImmediate: yields chunks immediately', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new TextEncoder().encode('Hello, World! This is a test.');

  const { stream, metadata } = aesEncryptStreamImmediate(
    createStream([data]),
    key,
    { iv, chunkSize: 16 }
  );

  // Collect chunks as they arrive
  const chunks: Uint8Array[] = [];
  let chunkCount = 0;

  for await (const chunk of stream) {
    chunks.push(chunk);
    chunkCount++;
  }

  // Should have received multiple chunks
  assertEquals(chunkCount > 0, true);

  // Metadata should be resolved after stream completes
  const meta = await metadata;
  assertEquals(meta.totalChunks, chunkCount);
  assertEquals(meta.bytesEncrypted, data.byteLength);
  assertEquals(meta.iv, iv);
});

Deno.test('aesEncryptStreamImmediate: matches streaming format', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new Uint8Array(5000);
  crypto.getRandomValues(data);

  const { stream, metadata } = aesEncryptStreamImmediate(
    createStream([data]),
    key,
    { iv, chunkSize: 1024 }
  );

  // Collect all chunks
  const chunks: Uint8Array[] = [];
  for await (const chunk of stream) {
    chunks.push(chunk);
  }

  const meta = await metadata;

  // Construct full encrypted data with header
  const header = new Uint8Array(CHUNKED_HEADER_SIZE);
  const view = new DataView(header.buffer);
  view.setUint32(0, meta.totalChunks, false);
  header.set(iv, 4);

  const totalLength = header.byteLength + chunks.reduce((sum, c) => sum + c.byteLength, 0);
  const fullEncrypted = new Uint8Array(totalLength);
  fullEncrypted.set(header, 0);

  let offset = header.byteLength;
  for (const chunk of chunks) {
    fullEncrypted.set(chunk, offset);
    offset += chunk.byteLength;
  }

  // Should be decryptable
  const decrypted = await aesDecryptChunked(fullEncrypted, key);
  assertEquals(decrypted, data);
});

Deno.test('aesEncryptStreamImmediate: validates key size', () => {
  const invalidKey = new Uint8Array(16);
  const iv = generateIV();

  // Validation happens synchronously when the function is called
  let errorThrown = false;
  try {
    aesEncryptStreamImmediate(
      createStream([new Uint8Array(100)]),
      invalidKey,
      { iv }
    );
  } catch (error) {
    errorThrown = true;
    assertEquals(error instanceof Error, true);
    assertEquals((error as Error).message.includes('Invalid AES key size'), true);
  }
  assertEquals(errorThrown, true);
});

Deno.test('aesEncryptStreamImmediate: validates IV size', () => {
  const key = generateAESKey();
  const invalidIV = new Uint8Array(8);

  // Validation happens synchronously when the function is called
  let errorThrown = false;
  try {
    aesEncryptStreamImmediate(
      createStream([new Uint8Array(100)]),
      key,
      { iv: invalidIV }
    );
  } catch (error) {
    errorThrown = true;
    assertEquals(error instanceof Error, true);
    assertEquals((error as Error).message.includes('Invalid IV size'), true);
  }
  assertEquals(errorThrown, true);
});

Deno.test('aesEncryptStreamImmediate: progress callback works', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const totalSize = 5 * 1024;

  const progressCalls: Array<{ percent: number; bytesProcessed: number; totalBytes: number }> = [];

  const data = new Uint8Array(totalSize);
  crypto.getRandomValues(data);

  const { stream } = aesEncryptStreamImmediate(
    createStream([data]),
    key,
    {
      iv,
      chunkSize: 1024,
      totalSize,
      onProgress: ({ percent, bytesProcessed, totalBytes }) => {
        progressCalls.push({ percent: percent ?? 0, bytesProcessed, totalBytes: totalBytes ?? 0 });
      },
    }
  );

  // Consume the stream
  for await (const _ of stream) {
    // Just consume
  }

  // Should have progress calls
  assertEquals(progressCalls.length > 0, true);

  // First call should be at 0%
  assertEquals(progressCalls[0].percent, 0);

  // Last call should be at 100%
  const lastCall = progressCalls[progressCalls.length - 1];
  assertEquals(lastCall.percent, 100);
});


// ============================================================================
// Tests for aesDecryptStream
// ============================================================================

import { aesDecryptStream, DecryptionError } from './aes-streaming.ts';

Deno.test('aesDecryptStream: basic roundtrip with single chunk', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new TextEncoder().encode('Hello, World!');

  // Encrypt
  const stream = createStream([data]);
  const encrypted = await collectChunks(aesEncryptStream(stream, key, { iv }));

  // Decrypt
  const encryptedStream = createStream([encrypted]);
  const decrypted = await collectChunks(aesDecryptStream(encryptedStream, key));

  assertEquals(decrypted, data);
  assertEquals(new TextDecoder().decode(decrypted), 'Hello, World!');
});

Deno.test('aesDecryptStream: roundtrip with multiple chunks', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const chunkSize = 1024; // 1KB chunks

  // Create 10KB of data
  const data = new Uint8Array(10 * 1024);
  crypto.getRandomValues(data);

  // Encrypt
  const stream = createStream([data]);
  const encrypted = await collectChunks(aesEncryptStream(stream, key, { iv, chunkSize }));

  // Decrypt
  const encryptedStream = createStream([encrypted]);
  const decrypted = await collectChunks(aesDecryptStream(encryptedStream, key));

  assertEquals(decrypted, data);
});

Deno.test('aesDecryptStream: decrypts split encrypted data', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new TextEncoder().encode('Hello, streaming world! This is a test of streaming decryption.');

  // Encrypt
  const stream = createStream([data]);
  const encrypted = await collectChunks(aesEncryptStream(stream, key, { iv, chunkSize: 16 }));

  // Split encrypted data into multiple small chunks (simulating network streaming)
  const smallChunks: Uint8Array[] = [];
  for (let i = 0; i < encrypted.byteLength; i += 10) {
    smallChunks.push(encrypted.slice(i, Math.min(i + 10, encrypted.byteLength)));
  }

  // Decrypt from small chunks
  const encryptedStream = createStream(smallChunks);
  const decrypted = await collectChunks(aesDecryptStream(encryptedStream, key));

  assertEquals(decrypted, data);
});

Deno.test('aesDecryptStream: handles header split across chunks', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new TextEncoder().encode('Test data');

  // Encrypt
  const stream = createStream([data]);
  const encrypted = await collectChunks(aesEncryptStream(stream, key, { iv }));

  // Split so header (16 bytes) is spread across multiple chunks
  const chunks = [
    encrypted.slice(0, 5),   // First 5 bytes of header
    encrypted.slice(5, 10),  // Next 5 bytes of header
    encrypted.slice(10, 16), // Remaining 6 bytes of header
    encrypted.slice(16),     // Rest of the data
  ];

  const encryptedStream = createStream(chunks);
  const decrypted = await collectChunks(aesDecryptStream(encryptedStream, key));

  assertEquals(decrypted, data);
});

Deno.test('aesDecryptStream: handles chunk header split across chunks', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new TextEncoder().encode('Hello, World! This is a longer test message.');

  // Encrypt with small chunk size
  const stream = createStream([data]);
  const encrypted = await collectChunks(aesEncryptStream(stream, key, { iv, chunkSize: 16 }));

  // Split at awkward boundaries to test chunk header parsing
  const chunks: Uint8Array[] = [];
  let offset = CHUNKED_HEADER_SIZE; // Skip header
  
  // First chunk: 2 bytes of chunk header + partial data
  chunks.push(encrypted.slice(0, CHUNKED_HEADER_SIZE + 2));
  offset = CHUNKED_HEADER_SIZE + 2;
  
  // Remaining data in small pieces
  while (offset < encrypted.byteLength) {
    const remaining = encrypted.byteLength - offset;
    const size = Math.min(7, remaining);
    chunks.push(encrypted.slice(offset, offset + size));
    offset += size;
  }

  const encryptedStream = createStream(chunks);
  const decrypted = await collectChunks(aesDecryptStream(encryptedStream, key));

  assertEquals(decrypted, data);
});

Deno.test('aesDecryptStream: validates key size', async () => {
  const invalidKey = new Uint8Array(16); // 16 bytes, not 32
  const encrypted = new Uint8Array(100);

  const stream = createStream([encrypted]);
  await assertRejects(
    async () => await collectChunks(aesDecryptStream(stream, invalidKey)),
    DecryptionError,
    'Invalid AES key size'
  );
});

Deno.test('aesDecryptStream: throws on corrupted header', async () => {
  const key = generateAESKey();
  const data = new TextEncoder().encode('Test data');

  // Encrypt
  const stream = createStream([data]);
  const encrypted = await collectChunks(aesEncryptStream(stream, key));

  // Corrupt the header (modify chunk count)
  encrypted[0] = 0xFF;
  encrypted[1] = 0xFF;
  encrypted[2] = 0xFF;
  encrypted[3] = 0xFF;

  const encryptedStream = createStream([encrypted]);
  await assertRejects(
    async () => await collectChunks(aesDecryptStream(encryptedStream, key)),
    DecryptionError,
    'unreasonable chunk count'
  );
});

Deno.test('aesDecryptStream: throws on truncated stream', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new TextEncoder().encode('Hello, World! This is a test message.');

  // Encrypt
  const stream = createStream([data]);
  const encrypted = await collectChunks(aesEncryptStream(stream, key, { iv, chunkSize: 16 }));

  // Truncate the encrypted data (remove last chunk)
  const truncated = encrypted.slice(0, -20);

  const encryptedStream = createStream([truncated]);
  await assertRejects(
    async () => await collectChunks(aesDecryptStream(encryptedStream, key)),
    DecryptionError,
    'incomplete chunk'
  );
});

Deno.test('aesDecryptStream: throws on corrupted chunk (auth tag failure)', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new TextEncoder().encode('Hello, World!');

  // Encrypt
  const stream = createStream([data]);
  const encrypted = await collectChunks(aesEncryptStream(stream, key, { iv }));

  // Corrupt a byte in the encrypted chunk data (after header and chunk header)
  const corrupted = new Uint8Array(encrypted);
  corrupted[CHUNKED_HEADER_SIZE + 10] ^= 0xFF; // Flip bits in encrypted data

  const encryptedStream = createStream([corrupted]);
  await assertRejects(
    async () => await collectChunks(aesDecryptStream(encryptedStream, key)),
    DecryptionError,
    'AES decryption failed'
  );
});

Deno.test('aesDecryptStream: throws on empty stream', async () => {
  const key = generateAESKey();

  const encryptedStream = createStream([]);
  await assertRejects(
    async () => await collectChunks(aesDecryptStream(encryptedStream, key)),
    DecryptionError,
    'Stream ended before header could be parsed'
  );
});

Deno.test('aesDecryptStream: validates expectedChunks option', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new TextEncoder().encode('Hello, World!');

  // Encrypt (will create 1 chunk)
  const stream = createStream([data]);
  const encrypted = await collectChunks(aesEncryptStream(stream, key, { iv }));

  // Try to decrypt with wrong expected chunk count
  const encryptedStream = createStream([encrypted]);
  await assertRejects(
    async () => await collectChunks(aesDecryptStream(encryptedStream, key, { expectedChunks: 5 })),
    DecryptionError,
    'Chunk count mismatch'
  );
});

Deno.test('aesDecryptStream: progress callback fires correctly', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const chunkSize = 1024;
  const totalSize = 5 * 1024; // 5KB

  const progressCalls: Array<{ percent: number; bytesProcessed: number; totalBytes: number }> = [];

  const data = new Uint8Array(totalSize);
  crypto.getRandomValues(data);

  // Encrypt
  const encryptStream = createStream([data]);
  const encrypted = await collectChunks(aesEncryptStream(encryptStream, key, { iv, chunkSize }));

  // Decrypt with progress
  const decryptStream = createStream([encrypted]);
  await collectChunks(
    aesDecryptStream(decryptStream, key, {
      expectedChunks: 5,
      onProgress: ({ percent, bytesProcessed, totalBytes }) => {
        progressCalls.push({ percent: percent ?? 0, bytesProcessed, totalBytes: totalBytes ?? 0 });
      },
    })
  );

  // Should have progress calls
  assertEquals(progressCalls.length > 0, true);

  // First call should be at 0%
  assertEquals(progressCalls[0].percent, 0);
  assertEquals(progressCalls[0].bytesProcessed, 0);

  // Last call should be at 100%
  const lastCall = progressCalls[progressCalls.length - 1];
  assertEquals(lastCall.percent, 100);
  assertEquals(lastCall.bytesProcessed, totalSize);

  // Progress should be monotonically increasing
  for (let i = 1; i < progressCalls.length; i++) {
    assertEquals(progressCalls[i].percent >= progressCalls[i - 1].percent, true);
  }
});

Deno.test('aesDecryptStream: streaming consumption without buffering all', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const chunkSize = 1024;
  const numChunks = 10;

  // Create 10KB of data
  const data = new Uint8Array(numChunks * chunkSize);
  crypto.getRandomValues(data);

  // Encrypt
  const encryptStream = createStream([data]);
  const encrypted = await collectChunks(aesEncryptStream(encryptStream, key, { iv, chunkSize }));

  // Decrypt with streaming consumption
  const decryptStream = aesDecryptStream(createStream([encrypted]), key);

  let chunkCount = 0;
  let totalBytes = 0;

  for await (const decryptedChunk of decryptStream) {
    chunkCount++;
    totalBytes += decryptedChunk.byteLength;
  }

  assertEquals(chunkCount, numChunks);
  assertEquals(totalBytes, data.byteLength);
});

Deno.test('aesDecryptStream: memory stays bounded with large data', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const chunkSize = 64 * 1024; // 64KB chunks
  const totalChunks = 10;

  // Track max chunk size seen during decryption
  let maxChunkSize = 0;
  let totalBytes = 0;

  async function* encryptedStream(): AsyncGenerator<Uint8Array> {
    // Generate encrypted data on-the-fly
    const cryptoKey = await crypto.subtle.importKey(
      'raw',
      key as unknown as ArrayBuffer,
      { name: 'AES-GCM', length: 256 },
      false,
      ['encrypt']
    );

    // Header
    const header = new Uint8Array(CHUNKED_HEADER_SIZE);
    const view = new DataView(header.buffer);
    view.setUint32(0, totalChunks, false);
    header.set(iv, 4);
    yield header;

    // Encrypt chunks
    for (let i = 0; i < totalChunks; i++) {
      const chunkData = new Uint8Array(chunkSize);
      chunkData.fill(i);

      // Derive chunk IV
      const chunkIV = new Uint8Array(iv);
      const chunkIndexBytes = new Uint8Array(4);
      new DataView(chunkIndexBytes.buffer).setUint32(0, i, false);
      chunkIV[8] ^= chunkIndexBytes[0];
      chunkIV[9] ^= chunkIndexBytes[1];
      chunkIV[10] ^= chunkIndexBytes[2];
      chunkIV[11] ^= chunkIndexBytes[3];

      // Encrypt
      const encryptedData = new Uint8Array(
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        await crypto.subtle.encrypt({ name: 'AES-GCM', iv: chunkIV as any }, cryptoKey, chunkData as any)
      );

      // Chunk header
      const chunkHeader = new Uint8Array(8);
      const chunkView = new DataView(chunkHeader.buffer);
      chunkView.setUint32(0, i, false);
      chunkView.setUint32(4, encryptedData.byteLength, false);

      // Yield in small pieces to test buffering
      yield chunkHeader.slice(0, 4);
      yield chunkHeader.slice(4);
      
      // Yield encrypted data in pieces
      for (let j = 0; j < encryptedData.byteLength; j += 32) {
        yield encryptedData.slice(j, Math.min(j + 32, encryptedData.byteLength));
      }
    }
  }

  for await (const chunk of aesDecryptStream(encryptedStream(), key)) {
    maxChunkSize = Math.max(maxChunkSize, chunk.byteLength);
    totalBytes += chunk.byteLength;
  }

  // Max chunk size should be bounded (original chunk size)
  assertEquals(maxChunkSize <= chunkSize, true);

  // Total bytes should match
  assertEquals(totalBytes, totalChunks * chunkSize);
});

Deno.test('aesDecryptStream: handles empty encrypted file (header only)', async () => {
  const key = generateAESKey();
  const iv = generateIV();

  // Create header-only encrypted data (0 chunks)
  const header = new Uint8Array(CHUNKED_HEADER_SIZE);
  const view = new DataView(header.buffer);
  view.setUint32(0, 0, false); // 0 chunks
  header.set(iv, 4);

  const encryptedStream = createStream([header]);
  const decrypted = await collectChunks(aesDecryptStream(encryptedStream, key));

  assertEquals(decrypted.byteLength, 0);
});

Deno.test('aesDecryptStream: matches non-streaming decryption', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new Uint8Array(5000);
  crypto.getRandomValues(data);

  // Encrypt using streaming
  const stream = createStream([data]);
  const streamingEncrypted = await collectChunks(
    aesEncryptStream(stream, key, { iv, chunkSize: 1024 })
  );

  // Decrypt using non-streaming function
  const nonStreamingDecrypted = await aesDecryptChunked(streamingEncrypted, key);

  // Decrypt using streaming function
  const streamingDecrypted = await collectChunks(
    aesDecryptStream(createStream([streamingEncrypted]), key)
  );

  // Both should produce the same output
  assertEquals(streamingDecrypted, nonStreamingDecrypted);
  assertEquals(streamingDecrypted, data);
});

Deno.test('aesDecryptStream: throws on stream with extra bytes at end', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = new TextEncoder().encode('Hello, World!');

  // Encrypt
  const stream = createStream([data]);
  const encrypted = await collectChunks(aesEncryptStream(stream, key, { iv }));

  // Add extra garbage bytes at the end (valid length prefix followed by garbage)
  const withGarbage = new Uint8Array(encrypted.byteLength + 20);
  withGarbage.set(encrypted, 0);
  // Add a valid-looking chunk header: chunk index 999, length 100
  const view = new DataView(withGarbage.buffer, encrypted.byteLength);
  view.setUint32(0, 999, false); // chunk index
  view.setUint32(4, 100, false); // encrypted length (valid, > auth tag size)
  withGarbage.fill(0xAB, encrypted.byteLength + 8); // garbage data

  const encryptedStream = createStream([withGarbage]);
  await assertRejects(
    async () => await collectChunks(aesDecryptStream(encryptedStream, key)),
    DecryptionError,
    'unexpected bytes remaining'
  );
});

Deno.test('aesDecryptStream: throws on wrong key', async () => {
  const encryptKey = generateAESKey();
  const decryptKey = generateAESKey(); // Different key
  const iv = generateIV();
  const data = new TextEncoder().encode('Hello, World! This is secret data.');

  // Encrypt with one key
  const stream = createStream([data]);
  const encrypted = await collectChunks(aesEncryptStream(stream, encryptKey, { iv }));

  // Try to decrypt with a different key
  const encryptedStream = createStream([encrypted]);
  await assertRejects(
    async () => await collectChunks(aesDecryptStream(encryptedStream, decryptKey)),
    DecryptionError,
    'AES decryption failed'
  );
});

Deno.test('aesDecryptStream: handles various chunk boundary sizes', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const data = crypto.getRandomValues(new Uint8Array(10000));

  // Encrypt
  const stream = createStream([data]);
  const encrypted = await collectChunks(aesEncryptStream(stream, key, { iv, chunkSize: 1024 }));

  // Test various split sizes
  const splitSizes = [1, 7, 16, 31, 64, 127, 256, 513, 1024, 2048];

  for (const splitSize of splitSizes) {
    // Split encrypted data into chunks of splitSize
    const chunks: Uint8Array[] = [];
    for (let i = 0; i < encrypted.byteLength; i += splitSize) {
      chunks.push(encrypted.slice(i, Math.min(i + splitSize, encrypted.byteLength)));
    }

    // Decrypt with this chunk size
    const encryptedStream = createStream(chunks);
    const decrypted = await collectChunks(aesDecryptStream(encryptedStream, key));

    assertEquals(decrypted, data, `Failed with split size: ${splitSize}`);
  }
});

Deno.test('aesDecryptStream: memory stays bounded during decryption', async () => {
  const key = generateAESKey();
  const iv = generateIV();
  const chunkSize = 64 * 1024; // 64KB
  const numChunks = 20;

  // Create 1.28MB of data (generate in smaller chunks due to getRandomValues limit)
  const dataChunks: Uint8Array[] = [];
  for (let i = 0; i < numChunks; i++) {
    dataChunks.push(crypto.getRandomValues(new Uint8Array(chunkSize)));
  }
  // Combine chunks using collectChunks helper
  const data = await collectChunks(createStream(dataChunks));

  // Encrypt
  const encryptStream = createStream([data]);
  const encrypted = await collectChunks(aesEncryptStream(encryptStream, key, { iv, chunkSize }));

  // Track max chunk size during decryption
  let maxChunkSize = 0;
  let totalBytes = 0;

  // Split encrypted data into small chunks to test buffering
  const smallChunks: Uint8Array[] = [];
  for (let i = 0; i < encrypted.byteLength; i += 512) {
    smallChunks.push(encrypted.slice(i, Math.min(i + 512, encrypted.byteLength)));
  }

  for await (const chunk of aesDecryptStream(createStream(smallChunks), key)) {
    maxChunkSize = Math.max(maxChunkSize, chunk.byteLength);
    totalBytes += chunk.byteLength;
  }

  // Max chunk size should be bounded (original chunk size)
  assertEquals(maxChunkSize <= chunkSize, true, `Max chunk size ${maxChunkSize} exceeds expected ${chunkSize}`);

  // Total bytes should match
  assertEquals(totalBytes, data.byteLength);
});
