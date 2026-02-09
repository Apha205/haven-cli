/**
 * Tests for streaming utility functions.
 */

import { assertEquals, assertExists } from 'https://deno.land/std@0.215.0/assert/mod.ts';
import { sha256HashStream, sha256HashStreamAccumulated } from './utils-streaming.ts';
import { sha256Hash } from './utils.ts';

/**
 * Create an async iterable from an array of chunks.
 */
async function* createStream(chunks: Uint8Array[]): AsyncGenerator<Uint8Array> {
  for (const chunk of chunks) {
    yield chunk;
  }
}

/**
 * Create a test data buffer of specified size.
 */
function createTestData(size: number): Uint8Array {
  const data = new Uint8Array(size);
  // Fill with predictable pattern for reproducible tests
  for (let i = 0; i < size; i++) {
    data[i] = i % 256;
  }
  return data;
}

Deno.test('sha256HashStream: empty stream returns correct hash', async () => {
  const stream = createStream([]);
  const hash = await sha256HashStream(stream);

  // SHA-256 of empty data
  const expectedHash = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855';
  assertEquals(hash, expectedHash);
});

Deno.test('sha256HashStream: single chunk matches non-streaming hash', async () => {
  const data = new TextEncoder().encode('Hello, World!');

  // Compute hash using streaming function
  const stream = createStream([data]);
  const streamingHash = await sha256HashStream(stream);

  // Compute hash using non-streaming function
  const nonStreamingHash = await sha256Hash(data);

  assertEquals(streamingHash, nonStreamingHash);
});

Deno.test('sha256HashStream: multiple chunks produce same hash as single chunk', async () => {
  const data = createTestData(1000);

  // Single chunk
  const singleChunkStream = createStream([data]);
  const singleChunkHash = await sha256HashStream(singleChunkStream);

  // Multiple chunks of different sizes
  const chunk1 = data.slice(0, 300);
  const chunk2 = data.slice(300, 700);
  const chunk3 = data.slice(700);

  const multiChunkStream = createStream([chunk1, chunk2, chunk3]);
  const multiChunkHash = await sha256HashStream(multiChunkStream);

  assertEquals(multiChunkHash, singleChunkHash);

  // Also verify against non-streaming hash
  const nonStreamingHash = await sha256Hash(data);
  assertEquals(multiChunkHash, nonStreamingHash);
});

Deno.test('sha256HashStream: many small chunks produce correct hash', async () => {
  const chunks: Uint8Array[] = [];
  const totalSize = 10000;
  const chunkSize = 100;

  // Create many small chunks
  for (let i = 0; i < totalSize; i += chunkSize) {
    const size = Math.min(chunkSize, totalSize - i);
    chunks.push(createTestData(size).map((b, idx) => (i + idx) % 256));
  }

  // Combine all chunks for reference hash
  const combined = new Uint8Array(totalSize);
  let offset = 0;
  for (const chunk of chunks) {
    combined.set(chunk, offset);
    offset += chunk.byteLength;
  }

  // Hash with streaming
  const stream = createStream(chunks);
  const streamingHash = await sha256HashStream(stream);

  // Hash with non-streaming
  const nonStreamingHash = await sha256Hash(combined);

  assertEquals(streamingHash, nonStreamingHash);
});

Deno.test('sha256HashStream: large data produces correct hash', async () => {
  const data = createTestData(1024 * 1024); // 1MB

  const stream = createStream([data]);
  const streamingHash = await sha256HashStream(stream);

  const nonStreamingHash = await sha256Hash(data);

  assertEquals(streamingHash, nonStreamingHash);
});

Deno.test('sha256HashStream: progress callback is called', async () => {
  const data = createTestData(1000);
  const progressCalls: Array<{ percent: number | undefined; bytesProcessed: number; totalBytes: number | undefined }> = [];

  const stream = createStream([data.slice(0, 300), data.slice(300, 700), data.slice(700)]);
  const hash = await sha256HashStream(stream, {
    totalSize: 1000,
    onProgress: ({ percent, bytesProcessed, totalBytes }) => {
      progressCalls.push({ percent, bytesProcessed, totalBytes });
    },
  });

  assertExists(hash);
  // Should have received progress updates
  assertEquals(progressCalls.length > 0, true);

  // First call should be 0%
  assertEquals(progressCalls[0].percent, 0);
  assertEquals(progressCalls[0].bytesProcessed, 0);

  // Last call should be 100%
  const lastCall = progressCalls[progressCalls.length - 1];
  assertEquals(lastCall.percent, 100);
  assertEquals(lastCall.bytesProcessed, 1000);
  assertEquals(lastCall.totalBytes, 1000);
});

Deno.test('sha256HashStream: progress callback works without totalSize', async () => {
  const data = createTestData(1000);
  const progressCalls: Array<{ percent: number | undefined; bytesProcessed: number; totalBytes: number | undefined }> = [];

  const stream = createStream([data]);
  const hash = await sha256HashStream(stream, {
    onProgress: ({ percent, bytesProcessed, totalBytes }) => {
      progressCalls.push({ percent, bytesProcessed, totalBytes });
    },
  });

  assertExists(hash);
  // Progress should still be called
  assertEquals(progressCalls.length > 0, true);

  // First call should be 0%
  assertEquals(progressCalls[0].percent, 0);
});

Deno.test('sha256HashStream: hash of known test vectors', async () => {
  // Test vector from NIST: "abc"
  const abcData = new TextEncoder().encode('abc');
  const abcStream = createStream([abcData]);
  const abcHash = await sha256HashStream(abcStream);
  assertEquals(
    abcHash,
    'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
  );

  // Test vector from NIST: "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"
  const longData = new TextEncoder().encode('abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq');
  const longStream = createStream([longData]);
  const longHash = await sha256HashStream(longStream);
  assertEquals(
    longHash,
    '248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1'
  );
});

Deno.test('sha256HashStream: binary data produces correct hash', async () => {
  // Binary data with all byte values
  const binaryData = new Uint8Array(256);
  for (let i = 0; i < 256; i++) {
    binaryData[i] = i;
  }

  const stream = createStream([binaryData]);
  const streamingHash = await sha256HashStream(stream);
  const nonStreamingHash = await sha256Hash(binaryData);

  assertEquals(streamingHash, nonStreamingHash);
});

Deno.test('sha256HashStreamAccumulated: produces same result as sha256HashStream', async () => {
  const data = createTestData(5000);

  // Split into multiple chunks
  const chunks: Uint8Array[] = [];
  for (let i = 0; i < data.length; i += 1000) {
    chunks.push(data.slice(i, i + 1000));
  }

  const stream1 = createStream(chunks);
  const streamingHash = await sha256HashStream(stream1);

  const stream2 = createStream(chunks);
  const accumulatedHash = await sha256HashStreamAccumulated(stream2);

  assertEquals(accumulatedHash, streamingHash);
});

Deno.test('sha256HashStream: handles stream with single byte chunks', async () => {
  const data = new TextEncoder().encode('Hello');
  const chunks: Uint8Array[] = [];

  // Create one-byte chunks
  for (let i = 0; i < data.length; i++) {
    chunks.push(data.slice(i, i + 1));
  }

  const stream = createStream(chunks);
  const streamingHash = await sha256HashStream(stream);
  const nonStreamingHash = await sha256Hash(data);

  assertEquals(streamingHash, nonStreamingHash);
});

Deno.test('sha256HashStream: handles very large chunks', async () => {
  // Create a chunk larger than typical stream buffers
  const data = createTestData(64 * 1024); // 64KB

  const stream = createStream([data]);
  const streamingHash = await sha256HashStream(stream);
  const nonStreamingHash = await sha256Hash(data);

  assertEquals(streamingHash, nonStreamingHash);
});
