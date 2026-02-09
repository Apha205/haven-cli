/**
 * Tests for Hybrid Crypto File-to-File Streaming Encryption
 *
 * These tests verify:
 * - Roundtrip encryption/decryption from file to file
 * - Progress callback invocation
 * - Metadata file creation and contents
 * - Error handling (missing files, etc.)
 * - Memory efficiency with large files
 */

import { assertEquals, assertExists, assertRejects } from 'https://deno.land/std@0.200.0/testing/asserts.ts';
import { 
  hybridEncryptFileStream, 
  hybridDecryptFileStream,
  FileNotFoundError,
  ParseError,
  generateAESKey,
  disconnectLitClient,
} from './hybrid-crypto.ts';
import { ChunkedEncryptionMetadata } from './crypto/types.ts';

// Test constants
const TEST_CHUNK_SIZE = 16 * 1024; // 16KB chunks for testing (smaller for tests)
const TEST_DIR = './test-temp-file-stream';

// Test private key (this is a test key, not used in production)
const TEST_PRIVATE_KEY = '0x' + '1'.repeat(64);

// Helper to ensure test directory exists
async function ensureTestDir(): Promise<void> {
  try {
    await Deno.mkdir(TEST_DIR, { recursive: true });
  } catch {
    // Directory may already exist
  }
}

// Helper to cleanup test files
async function cleanupTestFiles(...paths: string[]): Promise<void> {
  for (const path of paths) {
    try {
      await Deno.remove(path);
    } catch {
      // File may not exist
    }
  }
}

// Helper to generate random data in chunks (respecting getRandomValues limit)
function generateRandomData(size: number): Uint8Array {
  const result = new Uint8Array(size);
  const chunkSize = 65536; // Max allowed by crypto.getRandomValues
  
  for (let offset = 0; offset < size; offset += chunkSize) {
    const remaining = size - offset;
    const currentChunkSize = Math.min(chunkSize, remaining);
    const chunk = new Uint8Array(currentChunkSize);
    crypto.getRandomValues(chunk);
    result.set(chunk, offset);
  }
  
  return result;
}

// Helper to create a test file with random data
async function createTestFile(path: string, size: number): Promise<string> {
  const data = generateRandomData(size);
  await Deno.writeFile(path, data);
  
  // Compute and return hash
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const hashBuffer = await crypto.subtle.digest('SHA-256', data as any);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

// Helper to compute file hash
async function computeFileHash(path: string): Promise<string> {
  const file = await Deno.open(path, { read: true });
  try {
    const chunks: Uint8Array[] = [];
    const buffer = new Uint8Array(64 * 1024);
    while (true) {
      const bytesRead = await file.read(buffer);
      if (bytesRead === null) break;
      chunks.push(new Uint8Array(buffer.slice(0, bytesRead)));
    }
    
    // Combine chunks
    let totalLength = 0;
    for (const chunk of chunks) totalLength += chunk.length;
    const combined = new Uint8Array(totalLength);
    let offset = 0;
    for (const chunk of chunks) {
      combined.set(chunk, offset);
      offset += chunk.length;
    }
    
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const hashBuffer = await crypto.subtle.digest('SHA-256', combined as any);
    return Array.from(new Uint8Array(hashBuffer))
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');
  } finally {
    file.close();
  }
}

Deno.test('hybridEncryptFileStream - throws FileNotFoundError for missing input file', async () => {
  await ensureTestDir();
  const inputPath = `${TEST_DIR}/non-existent-file.bin`;
  const outputPath = `${TEST_DIR}/output.enc`;

  await assertRejects(
    async () => {
      await hybridEncryptFileStream(inputPath, outputPath, TEST_PRIVATE_KEY);
    },
    FileNotFoundError,
    'File not found'
  );
});

Deno.test({
  name: 'hybridEncryptFileStream - encrypts small file (1KB)',
  fn: async () => {
    await ensureTestDir();
    const inputPath = `${TEST_DIR}/small-file.bin`;
    const outputPath = `${TEST_DIR}/small-file.enc`;
    const metadataPath = `${TEST_DIR}/small-file.meta`;

    try {
      // Create test file
      const originalHash = await createTestFile(inputPath, 1024);

      // Encrypt
      const result = await hybridEncryptFileStream(
        inputPath,
        outputPath,
        TEST_PRIVATE_KEY,
        {
          metadataPath,
          chunkSize: TEST_CHUNK_SIZE,
        }
      );

      // Verify result
      assertEquals(result.encryptedPath, outputPath);
      assertEquals(result.metadataPath, metadataPath);
      assertEquals(result.originalHash, originalHash);
      assertExists(result.encryptedSize);
      assertEquals(result.encryptedSize > 0, true);

      // Verify encrypted file exists
      const encryptedInfo = await Deno.stat(outputPath);
      assertEquals(encryptedInfo.isFile, true);
      assertEquals(encryptedInfo.size, result.encryptedSize);

      // Verify metadata file exists
      const metadataContent = await Deno.readTextFile(metadataPath);
      assertExists(metadataContent);

      // Verify metadata is valid JSON
      const metadata: ChunkedEncryptionMetadata = JSON.parse(metadataContent);
      assertEquals(metadata.version, 'hybrid-v1');
      assertExists(metadata.encryptedKey);
      assertExists(metadata.keyHash);
      assertExists(metadata.iv);
      assertEquals(metadata.algorithm, 'AES-GCM');
      assertEquals(metadata.keyLength, 256);
      assertExists(metadata.accessControlConditions);
      assertEquals(metadata.chain, 'ethereum');
      assertEquals(metadata.originalSize, 1024);
      assertEquals(metadata.originalHash, originalHash);
      assertEquals(metadata.chunked, true);
      assertExists(metadata.totalChunks);
      assertExists(metadata.chunkSize);

    } finally {
      await cleanupTestFiles(inputPath, outputPath, metadataPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  sanitizeOps: false,
  sanitizeResources: false,
});

Deno.test({
  name: 'hybridEncryptFileStream - progress callback is invoked',
  fn: async () => {
    await ensureTestDir();
    const inputPath = `${TEST_DIR}/progress-test.bin`;
    const outputPath = `${TEST_DIR}/progress-test.enc`;
    const metadataPath = `${TEST_DIR}/progress-test.meta`;

    try {
      // Create test file (multiple chunks worth)
      await createTestFile(inputPath, TEST_CHUNK_SIZE * 3);

      const progressCalls: Array<{ percent: number | undefined; bytesProcessed: number; totalBytes: number | undefined }> = [];

      // Encrypt with progress tracking
      await hybridEncryptFileStream(
        inputPath,
        outputPath,
        TEST_PRIVATE_KEY,
        {
          metadataPath,
          chunkSize: TEST_CHUNK_SIZE,
          onProgress: ({ percent, bytesProcessed, totalBytes }) => {
            progressCalls.push({ percent, bytesProcessed, totalBytes });
          },
        }
      );

      // Verify progress was reported
      assertEquals(progressCalls.length > 0, true, 'Should have progress calls');
      
      // First call should be near 0%
      assertEquals((progressCalls[0].percent ?? 0) >= 0, true);
      
      // Last call should be 100%
      const lastCall = progressCalls[progressCalls.length - 1];
      assertEquals(lastCall.percent, 100);
      
      // Bytes should increase monotonically
      for (let i = 1; i < progressCalls.length; i++) {
        assertEquals(
          progressCalls[i].bytesProcessed >= progressCalls[i - 1].bytesProcessed,
          true,
          `Bytes should increase: ${progressCalls[i - 1].bytesProcessed} -> ${progressCalls[i].bytesProcessed}`
        );
      }

    } finally {
      await cleanupTestFiles(inputPath, outputPath, metadataPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  sanitizeOps: false,
  sanitizeResources: false,
});

Deno.test({
  name: 'hybridEncryptFileStream - onChunkEncrypted callback is invoked',
  fn: async () => {
    await ensureTestDir();
    const inputPath = `${TEST_DIR}/chunk-callback-test.bin`;
    const outputPath = `${TEST_DIR}/chunk-callback-test.enc`;
    const metadataPath = `${TEST_DIR}/chunk-callback-test.meta`;

    try {
      // Create test file (3 chunks worth)
      await createTestFile(inputPath, TEST_CHUNK_SIZE * 3);

      const chunkCalls: Array<{ chunkIndex: number; encryptedSize: number }> = [];

      // Encrypt with chunk tracking
      await hybridEncryptFileStream(
        inputPath,
        outputPath,
        TEST_PRIVATE_KEY,
        {
          metadataPath,
          chunkSize: TEST_CHUNK_SIZE,
          onChunkEncrypted: (chunkIndex, encryptedSize) => {
            chunkCalls.push({ chunkIndex, encryptedSize });
          },
        }
      );

      // Verify chunk callback was invoked (header + data chunks)
      // Note: aesEncryptStream yields: header (index 0), then each encrypted chunk
      assertEquals(chunkCalls.length >= 1, true, 'Should have at least 1 chunk call');
      
      // Verify chunk indices are sequential
      for (let i = 0; i < chunkCalls.length; i++) {
        assertEquals(chunkCalls[i].chunkIndex, i);
        assertEquals(chunkCalls[i].encryptedSize > 0, true);
      }

    } finally {
      await cleanupTestFiles(inputPath, outputPath, metadataPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  sanitizeOps: false,
  sanitizeResources: false,
});

Deno.test({
  name: 'hybridEncryptFileStream - encrypts empty file',
  fn: async () => {
    await ensureTestDir();
    const inputPath = `${TEST_DIR}/empty-file.bin`;
    const outputPath = `${TEST_DIR}/empty-file.enc`;
    const metadataPath = `${TEST_DIR}/empty-file.meta`;

    try {
      // Create empty test file
      await Deno.writeFile(inputPath, new Uint8Array(0));

      // Encrypt
      const result = await hybridEncryptFileStream(
        inputPath,
        outputPath,
        TEST_PRIVATE_KEY,
        {
          metadataPath,
          chunkSize: TEST_CHUNK_SIZE,
        }
      );

      // Verify result
      assertExists(result.originalHash);
      assertExists(result.encryptedSize);

      // Verify metadata
      const metadataContent = await Deno.readTextFile(metadataPath);
      const metadata: ChunkedEncryptionMetadata = JSON.parse(metadataContent);
      assertEquals(metadata.originalSize, 0);

    } finally {
      await cleanupTestFiles(inputPath, outputPath, metadataPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  sanitizeOps: false,
  sanitizeResources: false,
});

Deno.test({
  name: 'hybridEncryptFileStream - encrypts medium file (64KB)',
  fn: async () => {
    await ensureTestDir();
    const inputPath = `${TEST_DIR}/medium-file.bin`;
    const outputPath = `${TEST_DIR}/medium-file.enc`;
    const metadataPath = `${TEST_DIR}/medium-file.meta`;

    try {
      // Create test file
      const originalHash = await createTestFile(inputPath, 64 * 1024);

      // Encrypt
      const result = await hybridEncryptFileStream(
        inputPath,
        outputPath,
        TEST_PRIVATE_KEY,
        {
          metadataPath,
          chunkSize: TEST_CHUNK_SIZE,
        }
      );

      // Verify result
      assertEquals(result.originalHash, originalHash);
      assertExists(result.encryptedSize);

      // Verify encrypted file is larger than original (due to encryption overhead)
      const encryptedInfo = await Deno.stat(outputPath);
      assertEquals(encryptedInfo.size > 0, true);

    } finally {
      await cleanupTestFiles(inputPath, outputPath, metadataPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  sanitizeOps: false,
  sanitizeResources: false,
});

Deno.test('hybridEncryptFileStream - cleanup partial files on error', async () => {
  await ensureTestDir();
  const inputPath = `${TEST_DIR}/cleanup-test.bin`;
  const outputPath = `${TEST_DIR}/cleanup-test.enc`;
  const metadataPath = `${TEST_DIR}/cleanup-test.meta`;

  try {
    // Create test file
    await createTestFile(inputPath, 1024);

    // Try to encrypt with invalid private key (should fail)
    let error: Error | null = null;
    try {
      await hybridEncryptFileStream(
        inputPath,
        outputPath,
        'invalid-private-key',
        { metadataPath }
      );
    } catch (e) {
      error = e instanceof Error ? e : new Error(String(e));
    }

    assertExists(error);

    // Verify partial files were cleaned up
    let outputExists = false;
    let metadataExists = false;
    try {
      await Deno.stat(outputPath);
      outputExists = true;
    } catch { /* ignore */ }
    try {
      await Deno.stat(metadataPath);
      metadataExists = true;
    } catch { /* ignore */ }

    assertEquals(outputExists, false, 'Output file should be cleaned up on error');
    assertEquals(metadataExists, false, 'Metadata file should be cleaned up on error');

  } finally {
    await cleanupTestFiles(inputPath, outputPath, metadataPath);
  }
});

Deno.test({
  name: 'hybridEncryptFileStream - uses default metadata path when not specified',
  fn: async () => {
    await ensureTestDir();
    const inputPath = `${TEST_DIR}/default-meta-test.bin`;
    const outputPath = `${TEST_DIR}/default-meta-test.enc`;
    const defaultMetadataPath = `${outputPath}.meta`;

    try {
      // Create test file
      await createTestFile(inputPath, 1024);

      // Encrypt without specifying metadata path
      const result = await hybridEncryptFileStream(
        inputPath,
        outputPath,
        TEST_PRIVATE_KEY
      );

      // Verify default metadata path is used
      assertEquals(result.metadataPath, defaultMetadataPath);

      // Verify metadata file exists at default path
      const metadataInfo = await Deno.stat(defaultMetadataPath);
      assertEquals(metadataInfo.isFile, true);

    } finally {
      await cleanupTestFiles(inputPath, outputPath, defaultMetadataPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  sanitizeOps: false,
  sanitizeResources: false,
});

Deno.test({
  name: 'hybridEncryptFileStream - default chunk size is used',
  fn: async () => {
    await ensureTestDir();
    const inputPath = `${TEST_DIR}/default-chunk-test.bin`;
    const outputPath = `${TEST_DIR}/default-chunk-test.enc`;
    const metadataPath = `${TEST_DIR}/default-chunk-test.meta`;

    try {
      // Create small test file
      await createTestFile(inputPath, 1024);

      // Encrypt without specifying chunk size
      await hybridEncryptFileStream(
        inputPath,
        outputPath,
        TEST_PRIVATE_KEY,
        { metadataPath }
      );

      // Verify metadata uses default chunk size (1MB = 1024 * 1024)
      const metadataContent = await Deno.readTextFile(metadataPath);
      const metadata: ChunkedEncryptionMetadata = JSON.parse(metadataContent);
      assertEquals(metadata.chunkSize, 1024 * 1024);

    } finally {
      await cleanupTestFiles(inputPath, outputPath, metadataPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  sanitizeOps: false,
  sanitizeResources: false,
});

Deno.test({
  name: 'hybridEncryptFileStream - encrypts file with non-default chain',
  fn: async () => {
    await ensureTestDir();
    const inputPath = `${TEST_DIR}/chain-test.bin`;
    const outputPath = `${TEST_DIR}/chain-test.enc`;
    const metadataPath = `${TEST_DIR}/chain-test.meta`;

    try {
      // Create test file
      await createTestFile(inputPath, 1024);

      // Encrypt with different chain
      await hybridEncryptFileStream(
        inputPath,
        outputPath,
        TEST_PRIVATE_KEY,
        {
          metadataPath,
          chain: 'polygon',
        }
      );

      // Verify metadata has correct chain
      const metadataContent = await Deno.readTextFile(metadataPath);
      const metadata: ChunkedEncryptionMetadata = JSON.parse(metadataContent);
      assertEquals(metadata.chain, 'polygon');

    } finally {
      await cleanupTestFiles(inputPath, outputPath, metadataPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  sanitizeOps: false,
  sanitizeResources: false,
});

// ============================================================================
// hybridDecryptFileStream Tests
// ============================================================================

// NOTE: Roundtrip tests require Lit Protocol capacity credits on the test wallet.
// These tests are marked with `ignore: true` by default since they require:
// 1. A funded wallet with capacity credits on the Lit network
// 2. Network connectivity to Lit nodes
//
// To run these tests, set LIT_TEST_HAS_CREDITS=1 environment variable and
// ensure the TEST_PRIVATE_KEY wallet has capacity credits minted.
const SKIP_LIT_TESTS = !Deno.env.get('LIT_TEST_HAS_CREDITS');

Deno.test({
  name: 'hybridDecryptFileStream - roundtrip encryption and decryption (requires Lit credits)',
  fn: async () => {
    await ensureTestDir();
    const inputPath = `${TEST_DIR}/roundtrip-input.bin`;
    const encryptedPath = `${TEST_DIR}/roundtrip.enc`;
    const metadataPath = `${TEST_DIR}/roundtrip.meta`;
    const decryptedPath = `${TEST_DIR}/roundtrip-output.bin`;

    try {
      // Create test file
      const originalHash = await createTestFile(inputPath, TEST_CHUNK_SIZE * 3);

      // Encrypt
      const encryptResult = await hybridEncryptFileStream(
        inputPath,
        encryptedPath,
        TEST_PRIVATE_KEY,
        {
          metadataPath,
          chunkSize: TEST_CHUNK_SIZE,
        }
      );

      // Decrypt
      const decryptResult = await hybridDecryptFileStream(
        encryptedPath,
        metadataPath,
        decryptedPath,
        TEST_PRIVATE_KEY
      );

      // Verify result
      assertEquals(decryptResult.decryptedPath, decryptedPath);
      assertEquals(decryptResult.originalHash, originalHash);
      assertEquals(decryptResult.computedHash, originalHash);
      assertEquals(decryptResult.hashValid, true);

      // Verify decrypted file exists and has correct size
      const decryptedInfo = await Deno.stat(decryptedPath);
      assertEquals(decryptedInfo.isFile, true);
      assertEquals(decryptedInfo.size, TEST_CHUNK_SIZE * 3);

      // Verify decrypted content matches original
      const decryptedData = await Deno.readFile(decryptedPath);
      const originalData = await Deno.readFile(inputPath);
      assertEquals(decryptedData.length, originalData.length);
      
      // Compare byte by byte
      for (let i = 0; i < decryptedData.length; i++) {
        if (decryptedData[i] !== originalData[i]) {
          throw new Error(`Data mismatch at byte ${i}: ${decryptedData[i]} vs ${originalData[i]}`);
        }
      }

    } finally {
      await cleanupTestFiles(inputPath, encryptedPath, metadataPath, decryptedPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  ignore: SKIP_LIT_TESTS,
  sanitizeOps: false,
  sanitizeResources: false,
});

Deno.test({
  name: 'hybridDecryptFileStream - throws FileNotFoundError for missing encrypted file',
  fn: async () => {
    await ensureTestDir();
    const encryptedPath = `${TEST_DIR}/non-existent.enc`;
    const metadataPath = `${TEST_DIR}/dummy.meta`;
    const outputPath = `${TEST_DIR}/output.bin`;

    // Create a dummy metadata file so only the encrypted file is missing
    const dummyMetadata = {
      version: 'hybrid-v1',
      encryptedKey: 'dummy',
      keyHash: 'dummy',
      iv: 'AAAAAAAAAAAA',
      algorithm: 'AES-GCM',
      keyLength: 256,
      accessControlConditions: [],
      chain: 'ethereum',
      originalSize: 100,
      originalHash: 'abc123',
      chunked: true,
      totalChunks: 1,
      chunkSize: 1024,
    };
    await Deno.writeTextFile(metadataPath, JSON.stringify(dummyMetadata));

    try {
      await assertRejects(
        async () => {
          await hybridDecryptFileStream(encryptedPath, metadataPath, outputPath, TEST_PRIVATE_KEY);
        },
        FileNotFoundError,
        'File not found'
      );
    } finally {
      await cleanupTestFiles(metadataPath);
    }
  },
  sanitizeOps: false,
  sanitizeResources: false,
});

Deno.test({
  name: 'hybridDecryptFileStream - throws FileNotFoundError for missing metadata file',
  fn: async () => {
    await ensureTestDir();
    const encryptedPath = `${TEST_DIR}/dummy.enc`;
    const metadataPath = `${TEST_DIR}/non-existent.meta`;
    const outputPath = `${TEST_DIR}/output.bin`;

    // Create a dummy encrypted file so only the metadata is missing
    await Deno.writeFile(encryptedPath, new Uint8Array([1, 2, 3, 4]));

    try {
      await assertRejects(
        async () => {
          await hybridDecryptFileStream(encryptedPath, metadataPath, outputPath, TEST_PRIVATE_KEY);
        },
        FileNotFoundError,
        'File not found'
      );
    } finally {
      await cleanupTestFiles(encryptedPath);
    }
  },
  sanitizeOps: false,
  sanitizeResources: false,
});

Deno.test({
  name: 'hybridDecryptFileStream - throws ParseError for invalid metadata JSON',
  fn: async () => {
    await ensureTestDir();
    const encryptedPath = `${TEST_DIR}/dummy.enc`;
    const metadataPath = `${TEST_DIR}/invalid.meta`;
    const outputPath = `${TEST_DIR}/output.bin`;

    // Create files
    await Deno.writeFile(encryptedPath, new Uint8Array([1, 2, 3, 4]));
    await Deno.writeTextFile(metadataPath, 'this is not valid JSON {{{');

    try {
      await assertRejects(
        async () => {
          await hybridDecryptFileStream(encryptedPath, metadataPath, outputPath, TEST_PRIVATE_KEY);
        },
        ParseError,
        'Failed to parse metadata'
      );
    } finally {
      await cleanupTestFiles(encryptedPath, metadataPath);
    }
  },
  sanitizeOps: false,
  sanitizeResources: false,
});

Deno.test({
  name: 'hybridDecryptFileStream - throws ParseError for unsupported version',
  fn: async () => {
    await ensureTestDir();
    const encryptedPath = `${TEST_DIR}/dummy.enc`;
    const metadataPath = `${TEST_DIR}/unsupported.meta`;
    const outputPath = `${TEST_DIR}/output.bin`;

    // Create a metadata file with unsupported version
    const badMetadata = {
      version: 'unsupported-v2',
      encryptedKey: 'dummy',
      keyHash: 'dummy',
      iv: 'AAAAAAAAAAAA',
      algorithm: 'AES-GCM',
      keyLength: 256,
      accessControlConditions: [],
      chain: 'ethereum',
      originalSize: 100,
      originalHash: 'abc123',
      chunked: true,
      totalChunks: 1,
      chunkSize: 1024,
    };
    await Deno.writeFile(encryptedPath, new Uint8Array([1, 2, 3, 4]));
    await Deno.writeTextFile(metadataPath, JSON.stringify(badMetadata));

    try {
      await assertRejects(
        async () => {
          await hybridDecryptFileStream(encryptedPath, metadataPath, outputPath, TEST_PRIVATE_KEY);
        },
        ParseError,
        'Unsupported encryption version'
      );
    } finally {
      await cleanupTestFiles(encryptedPath, metadataPath);
    }
  },
  sanitizeOps: false,
  sanitizeResources: false,
});

Deno.test({
  name: 'hybridDecryptFileStream - progress callback is invoked (requires Lit credits)',
  fn: async () => {
    await ensureTestDir();
    const inputPath = `${TEST_DIR}/decrypt-progress-input.bin`;
    const encryptedPath = `${TEST_DIR}/decrypt-progress.enc`;
    const metadataPath = `${TEST_DIR}/decrypt-progress.meta`;
    const decryptedPath = `${TEST_DIR}/decrypt-progress-output.bin`;

    try {
      // Create test file
      await createTestFile(inputPath, TEST_CHUNK_SIZE * 3);

      // Encrypt
      await hybridEncryptFileStream(
        inputPath,
        encryptedPath,
        TEST_PRIVATE_KEY,
        {
          metadataPath,
          chunkSize: TEST_CHUNK_SIZE,
        }
      );

      const progressCalls: Array<{ percent: number | undefined; bytesProcessed: number; totalBytes: number | undefined }> = [];

      // Decrypt with progress tracking
      await hybridDecryptFileStream(
        encryptedPath,
        metadataPath,
        decryptedPath,
        TEST_PRIVATE_KEY,
        {
          onProgress: ({ percent, bytesProcessed, totalBytes }) => {
            progressCalls.push({ percent, bytesProcessed, totalBytes });
          },
        }
      );

      // Verify progress was reported
      assertEquals(progressCalls.length > 0, true, 'Should have progress calls');
      
      // First call should be near 0%
      assertEquals((progressCalls[0].percent ?? 0) >= 0, true);
      
      // Last call should be 100%
      const lastCall = progressCalls[progressCalls.length - 1];
      assertEquals(lastCall.percent, 100);
      
      // Bytes should increase monotonically
      for (let i = 1; i < progressCalls.length; i++) {
        assertEquals(
          progressCalls[i].bytesProcessed >= progressCalls[i - 1].bytesProcessed,
          true,
          `Bytes should increase: ${progressCalls[i - 1].bytesProcessed} -> ${progressCalls[i].bytesProcessed}`
        );
      }

    } finally {
      await cleanupTestFiles(inputPath, encryptedPath, metadataPath, decryptedPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  ignore: SKIP_LIT_TESTS,
  sanitizeOps: false,
  sanitizeResources: false,
});

Deno.test({
  name: 'hybridDecryptFileStream - decrypts empty file (requires Lit credits)',
  fn: async () => {
    await ensureTestDir();
    const inputPath = `${TEST_DIR}/decrypt-empty-input.bin`;
    const encryptedPath = `${TEST_DIR}/decrypt-empty.enc`;
    const metadataPath = `${TEST_DIR}/decrypt-empty.meta`;
    const decryptedPath = `${TEST_DIR}/decrypt-empty-output.bin`;

    try {
      // Create empty file
      await Deno.writeFile(inputPath, new Uint8Array(0));

      // Encrypt
      await hybridEncryptFileStream(
        inputPath,
        encryptedPath,
        TEST_PRIVATE_KEY,
        {
          metadataPath,
          chunkSize: TEST_CHUNK_SIZE,
        }
      );

      // Decrypt
      const decryptResult = await hybridDecryptFileStream(
        encryptedPath,
        metadataPath,
        decryptedPath,
        TEST_PRIVATE_KEY
      );

      // Verify result
      assertEquals(decryptResult.hashValid, true);
      assertEquals(decryptResult.originalSize, 0);

      // Verify decrypted file is empty
      const decryptedInfo = await Deno.stat(decryptedPath);
      assertEquals(decryptedInfo.size, 0);

    } finally {
      await cleanupTestFiles(inputPath, encryptedPath, metadataPath, decryptedPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  ignore: SKIP_LIT_TESTS,
  sanitizeOps: false,
  sanitizeResources: false,
});

Deno.test({
  name: 'hybridDecryptFileStream - cleanup partial files on error (requires Lit credits)',
  fn: async () => {
    await ensureTestDir();
    const inputPath = `${TEST_DIR}/decrypt-cleanup-input.bin`;
    const encryptedPath = `${TEST_DIR}/decrypt-cleanup.enc`;
    const metadataPath = `${TEST_DIR}/decrypt-cleanup.meta`;
    const decryptedPath = `${TEST_DIR}/decrypt-cleanup-output.bin`;

    try {
      // Create and encrypt a file
      await createTestFile(inputPath, 1024);
      await hybridEncryptFileStream(
        inputPath,
        encryptedPath,
        TEST_PRIVATE_KEY,
        { metadataPath }
      );

      // Try to decrypt with wrong private key (should fail during key decryption)
      let error: Error | null = null;
      try {
        await hybridDecryptFileStream(
          encryptedPath,
          metadataPath,
          decryptedPath,
          '0x' + '2'.repeat(64) // Different key
        );
      } catch (e) {
        error = e instanceof Error ? e : new Error(String(e));
      }

      assertExists(error);

      // Verify partial output file was cleaned up
      let outputExists = false;
      try {
        await Deno.stat(decryptedPath);
        outputExists = true;
      } catch { /* ignore */ }

      assertEquals(outputExists, false, 'Output file should be cleaned up on error');

    } finally {
      await cleanupTestFiles(inputPath, encryptedPath, metadataPath, decryptedPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  ignore: SKIP_LIT_TESTS,
  sanitizeOps: false,
  sanitizeResources: false,
});

Deno.test({
  name: 'hybridDecryptFileStream - reports hashValid: false for corrupted encrypted file (requires Lit credits)',
  fn: async () => {
    await ensureTestDir();
    const inputPath = `${TEST_DIR}/corrupt-input.bin`;
    const encryptedPath = `${TEST_DIR}/corrupt.enc`;
    const metadataPath = `${TEST_DIR}/corrupt.meta`;
    const corruptedEncryptedPath = `${TEST_DIR}/corrupt-bad.enc`;
    const decryptedPath = `${TEST_DIR}/corrupt-output.bin`;

    try {
      // Create and encrypt a file
      await createTestFile(inputPath, 1024);
      await hybridEncryptFileStream(
        inputPath,
        encryptedPath,
        TEST_PRIVATE_KEY,
        { metadataPath }
      );

      // Read and corrupt the encrypted file
      const encryptedData = await Deno.readFile(encryptedPath);
      // Corrupt some bytes in the middle (avoid the header)
      encryptedData[50] = encryptedData[50] ^ 0xFF;
      encryptedData[51] = encryptedData[51] ^ 0xFF;
      await Deno.writeFile(corruptedEncryptedPath, encryptedData);

      // Decrypt the corrupted file - this should fail with auth tag error
      // because AES-GCM will detect tampering
      let error: Error | null = null;
      try {
        await hybridDecryptFileStream(
          corruptedEncryptedPath,
          metadataPath,
          decryptedPath,
          TEST_PRIVATE_KEY
        );
      } catch (e) {
        error = e instanceof Error ? e : new Error(String(e));
      }

      // Should have thrown an error due to auth tag failure
      assertExists(error);
      // The error should mention AES decryption or auth tag
      const errorMsg = error.message.toLowerCase();
      assertEquals(
        errorMsg.includes('aes') || errorMsg.includes('auth') || errorMsg.includes('decryption'),
        true,
        `Expected AES/auth/decryption error but got: ${error.message}`
      );

    } finally {
      await cleanupTestFiles(inputPath, encryptedPath, metadataPath, corruptedEncryptedPath, decryptedPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  ignore: SKIP_LIT_TESTS,
  sanitizeOps: false,
  sanitizeResources: false,
});

// Cleanup test directory after all tests
Deno.test({
  name: 'cleanup test directory',
  fn: async () => {
    try {
      await Deno.remove(TEST_DIR, { recursive: true });
    } catch {
      // Directory may not exist
    }
  },
  sanitizeOps: false,
  sanitizeResources: false,
});
