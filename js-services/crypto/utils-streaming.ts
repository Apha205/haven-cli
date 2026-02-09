/**
 * Streaming utility functions for hybrid encryption system.
 *
 * This module provides streaming operations that process data incrementally
 * without loading the entire file into memory.
 */

import { crypto } from 'jsr:@std/crypto@1.0.4';
import type { StreamProgressCallback } from './types.ts';

/**
 * Options for streaming SHA-256 hash computation.
 */
export interface SHA256StreamOptions {
  /** Total size of the data in bytes (for progress reporting) */
  totalSize?: number;
  /** Progress callback for reporting hash computation progress */
  onProgress?: StreamProgressCallback;
}

/**
 * Compute SHA-256 hash of a data stream.
 *
 * Processes data incrementally without loading the entire stream into memory.
 * Uses Deno's std/crypto which supports true streaming digest computation via
 * AsyncIterable input.
 *
 * @param dataStream - Async iterable of data chunks
 * @param options - Options for hash computation including progress callback
 * @returns Promise resolving to hex-encoded SHA-256 hash
 *
 * @example
 * ```typescript
 * const fileStream = Deno.openSync('file.txt').readable;
 * const hash = await sha256HashStream(fileStream, {
 *   onProgress: (percent, bytes, total) => console.log(`${percent}%`)
 * });
 * console.log(`SHA-256: ${hash}`);
 * ```
 */
export async function sha256HashStream(
  dataStream: AsyncIterable<Uint8Array>,
  options: SHA256StreamOptions = {}
): Promise<string> {
  const { totalSize, onProgress } = options;

  // Track bytes processed for progress reporting
  let bytesProcessed = 0;

  // Report initial progress
  if (onProgress) {
    onProgress({ bytesProcessed: 0, totalBytes: totalSize, percent: 0 });
  }

  // Create a wrapped async iterable that reports progress
  async function* progressTrackingStream(): AsyncGenerator<Uint8Array> {
    for await (const chunk of dataStream) {
      bytesProcessed += chunk.byteLength;

      if (onProgress && totalSize !== undefined && totalSize > 0) {
        const percent = (bytesProcessed / totalSize) * 100;
        onProgress({ bytesProcessed, totalBytes: totalSize, percent });
      }

      yield chunk;
    }
  }

  // Use Deno's std/crypto for streaming digest
  // This provides true incremental hashing without loading all data into memory
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const hashBuffer = await crypto.subtle.digest('SHA-256', progressTrackingStream() as any);

  // Report final progress
  if (onProgress) {
    onProgress({ bytesProcessed, totalBytes: totalSize ?? bytesProcessed, percent: 100 });
  }

  // Convert hash buffer to hex string
  const hashArray = new Uint8Array(hashBuffer);
  return Array.from(hashArray)
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

/**
 * Compute SHA-256 hash of a data stream with explicit chunk-based processing.
 *
 * This is an alternative implementation that uses manual chunk accumulation
 * and can be used in environments where Web Crypto streaming is not available.
 * Note: This implementation accumulates all chunks into memory before hashing,
 * so it's not truly streaming. Use sha256HashStream() for true streaming.
 *
 * @param dataStream - Async iterable of data chunks
 * @param options - Options for hash computation
 * @returns Promise resolving to hex-encoded SHA-256 hash
 *
 * @deprecated Use sha256HashStream() instead for true streaming
 */
export async function sha256HashStreamAccumulated(
  dataStream: AsyncIterable<Uint8Array>,
  options: SHA256StreamOptions = {}
): Promise<string> {
  const { totalSize, onProgress } = options;

  const chunks: Uint8Array[] = [];
  let totalLength = 0;

  // Report initial progress
  if (onProgress) {
    onProgress({ bytesProcessed: 0, totalBytes: totalSize, percent: 0 });
  }

  // Collect all chunks
  for await (const chunk of dataStream) {
    chunks.push(chunk);
    totalLength += chunk.byteLength;

    if (onProgress && totalSize !== undefined && totalSize > 0) {
      const percent = (totalLength / totalSize) * 100;
      onProgress({ bytesProcessed: totalLength, totalBytes: totalSize, percent });
    }
  }

  // Combine chunks into single buffer
  const combined = new Uint8Array(totalLength);
  let offset = 0;
  for (const chunk of chunks) {
    combined.set(chunk, offset);
    offset += chunk.byteLength;
  }

  // Compute hash using Web Crypto
  const hashBuffer = await crypto.subtle.digest('SHA-256', combined);

  // Report final progress
  if (onProgress) {
    onProgress({ bytesProcessed: totalLength, totalBytes: totalSize ?? totalLength, percent: 100 });
  }

  // Convert to hex string
  const hashArray = new Uint8Array(hashBuffer);
  return Array.from(hashArray)
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}
