/**
 * Testing helper functions for streaming encryption tests.
 *
 * This module provides utility functions for creating test streams
 * and collecting results in tests.
 */

/**
 * Create a stream from a Uint8Array with configurable chunk size
 *
 * @param data - The data to stream
 * @param chunkSize - Size of each chunk in bytes (default: 1024)
 * @returns Async generator yielding data chunks
 *
 * @example
 * ```typescript
 * const data = new Uint8Array(10000);
 * const stream = createStream(data, 1024); // 10 chunks of 1KB each
 *
 * for await (const chunk of stream) {
 *   console.log(chunk.length);
 * }
 * ```
 */
export async function* createStream(
  data: Uint8Array,
  chunkSize: number = 1024
): AsyncGenerator<Uint8Array> {
  for (let i = 0; i < data.length; i += chunkSize) {
    yield data.slice(i, Math.min(i + chunkSize, data.length));
  }
}

/**
 * Create a stream from an array of Uint8Array chunks.
 *
 * @param chunks - Array of chunks to yield
 * @returns Async generator yielding each chunk
 *
 * @example
 * ```typescript
 * const chunks = [new Uint8Array([1, 2]), new Uint8Array([3, 4])];
 * const stream = createStreamFromChunks(chunks);
 * ```
 */
export async function* createStreamFromChunks(
  chunks: Uint8Array[]
): AsyncGenerator<Uint8Array> {
  for (const chunk of chunks) {
    yield chunk;
  }
}

/**
 * Collect an async iterable into an array.
 *
 * @param iterable - The async iterable to collect
 * @returns Array of all items from the iterable
 *
 * @example
 * ```typescript
 * const chunks = await collect(aesEncryptStream(dataStream, key));
 * ```
 */
export async function collect<T>(
  iterable: AsyncIterable<T>
): Promise<T[]> {
  const result: T[] = [];
  for await (const item of iterable) {
    result.push(item);
  }
  return result;
}

/**
 * Combine Uint8Array chunks into a single array.
 *
 * @param chunks - Array of Uint8Array chunks
 * @returns Combined Uint8Array containing all chunks
 *
 * @example
 * ```typescript
 * const chunks = [chunk1, chunk2, chunk3];
 * const combined = combineChunks(chunks);
 * ```
 */
export function combineChunks(chunks: Uint8Array[]): Uint8Array {
  const totalLength = chunks.reduce((sum, c) => sum + c.length, 0);
  const result = new Uint8Array(totalLength);
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.length;
  }
  return result;
}

/**
 * Create a stream that yields random data of specified size.
 *
 * @param totalBytes - Total bytes to generate
 * @param chunkSize - Size of each chunk (default: 1024)
 * @returns Async generator yielding random data chunks
 *
 * @example
 * ```typescript
 * const stream = createRandomStream(1024 * 100, 1024); // 100KB in 1KB chunks
 * ```
 */
export async function* createRandomStream(
  totalBytes: number,
  chunkSize: number = 1024
): AsyncGenerator<Uint8Array> {
  let remaining = totalBytes;
  while (remaining > 0) {
    const size = Math.min(chunkSize, remaining);
    yield crypto.getRandomValues(new Uint8Array(size));
    remaining -= size;
  }
}

/**
 * Create a stream that yields predictable pattern data.
 * Useful for debugging since the data is deterministic.
 *
 * @param totalBytes - Total bytes to generate
 * @param chunkSize - Size of each chunk (default: 1024)
 * @returns Async generator yielding pattern data chunks
 *
 * @example
 * ```typescript
 * const stream = createPatternStream(1000, 100);
 * // Yields chunks with values [0, 1, 2, ..., 255, 0, 1, ...]
 * ```
 */
export async function* createPatternStream(
  totalBytes: number,
  chunkSize: number = 1024
): AsyncGenerator<Uint8Array> {
  let remaining = totalBytes;
  let patternValue = 0;

  while (remaining > 0) {
    const size = Math.min(chunkSize, remaining);
    const chunk = new Uint8Array(size);
    for (let i = 0; i < size; i++) {
      chunk[i] = patternValue % 256;
      patternValue++;
    }
    yield chunk;
    remaining -= size;
  }
}

/**
 * Compare two Uint8Arrays for equality.
 *
 * @param a - First array
 * @param b - Second array
 * @returns True if arrays are equal
 */
export function arraysEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

/**
 * Hex encode a Uint8Array.
 *
 * @param data - Data to encode
 * @returns Hex string
 */
export function toHex(data: Uint8Array): string {
  return Array.from(data)
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

/**
 * Hex decode a string to Uint8Array.
 *
 * @param hex - Hex string to decode
 * @returns Decoded Uint8Array
 */
export function fromHex(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.slice(i, i + 2), 16);
  }
  return bytes;
}
