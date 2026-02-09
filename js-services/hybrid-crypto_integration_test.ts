/**
 * Integration Tests for Hybrid Crypto File-to-File Streaming
 *
 * These tests verify the complete file-to-file encryption/decryption workflow:
 * - Roundtrip encryption/decryption
 * - Large file handling (memory efficient)
 * - Compatibility with existing chunked format
 * - Progress callback invocation
 * - Error handling (missing files, corrupted data, wrong keys)
 * - Edge cases (empty file, single byte)
 *
 * Note: Tests requiring Lit Protocol capacity credits are marked with `ignore: SKIP_LIT_TESTS`
 * and only run when LIT_TEST_HAS_CREDITS=1 environment variable is set.
 */

import {
  assertEquals,
  assertExists,
  assertRejects,
} from 'https://deno.land/std@0.200.0/testing/asserts.ts';
import {
  hybridEncryptFileStreaming,
  hybridDecryptFileStreaming,
  FileNotFoundError,
  ParseError,
  generateAESKey,
  generateIV,
  disconnectLitClient,
  DecryptionError,
} from './hybrid-crypto.ts';
import { ChunkedEncryptionMetadata } from './crypto/types.ts';
import { sha256HashStream } from './crypto/utils-streaming.ts';

// Test constants
const TEST_DIR = './test-temp-integration';
const TEST_CHUNK_SIZE = 256 * 1024; // 256KB chunks for faster tests

// Test private key (this is a test key, not used in production)
const TEST_PRIVATE_KEY = '0x' + '1'.repeat(64);

// Skip Lit tests if no capacity credits available
const SKIP_LIT_TESTS = !Deno.env.get('LIT_TEST_HAS_CREDITS');

// ============================================================================
// Test Helpers
// ============================================================================

async function setup(): Promise<void> {
  try {
    await Deno.mkdir(TEST_DIR, { recursive: true });
  } catch {
    // Directory may already exist
  }
}

async function cleanup(...paths: string[]): Promise<void> {
  for (const path of paths) {
    try {
      await Deno.remove(path);
    } catch {
      // File may not exist
    }
  }
}

async function cleanupAll(): Promise<void> {
  try {
    await Deno.remove(TEST_DIR, { recursive: true });
  } catch {
    // Directory may not exist
  }
}

// Generate random data in chunks (respecting getRandomValues limit)
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

// Create a test file with random data and return the SHA-256 hash
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

// Compute SHA-256 hash of a file (streaming for memory efficiency)
async function hashFile(path: string): Promise<string> {
  const file = await Deno.open(path, { read: true });

  async function* fileStream(): AsyncGenerator<Uint8Array> {
    const buffer = new Uint8Array(1024 * 1024); // 1MB read buffer
    try {
      while (true) {
        const bytesRead = await file.read(buffer);
        if (bytesRead === null) break;
        yield buffer.slice(0, bytesRead);
      }
    } finally {
      file.close();
    }
  }

  return await sha256HashStream(fileStream());
}

// Convert hex private key to Uint8Array
function privateKeyToUint8Array(privateKey: string): Uint8Array {
  const hex = privateKey.startsWith('0x') ? privateKey.slice(2) : privateKey;
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.slice(i, i + 2), 16);
  }
  return bytes;
}

// Generate a new key pair for testing
async function generateKeyPair(): Promise<{ privateKey: Uint8Array; address: string }> {
  // Generate a random private key
  const privateKey = crypto.getRandomValues(new Uint8Array(32));
  
  // For testing, we'll use a fixed address format since we don't have ethers here
  // In production, this would derive the address from the private key
  const address = '0x' + Array.from(crypto.getRandomValues(new Uint8Array(20)))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');

  return { privateKey, address };
}

// ============================================================================
// 1. File-to-File Roundtrip Tests
// ============================================================================

Deno.test({
  name: 'integration: file-to-file roundtrip',
  fn: async () => {
    await setup();

    const inputPath = `${TEST_DIR}/test-input.bin`;
    const encryptedPath = `${TEST_DIR}/test-input.bin.enc`;
    const metadataPath = `${TEST_DIR}/test-input.bin.meta`;
    const decryptedPath = `${TEST_DIR}/test-output.bin`;

    try {
      // Generate test file (1MB)
      const testData = generateRandomData(1024 * 1024);
      await Deno.writeFile(inputPath, testData);

      // Generate key pair
      const keyPair = await generateKeyPair();

      // Encrypt
      const encryptResult = await hybridEncryptFileStreaming(
        inputPath,
        encryptedPath,
        keyPair.privateKey,
        { metadataPath }
      );

      // Verify encrypted file exists
      const encryptedInfo = await Deno.stat(encryptedPath);
      assertEquals(encryptedInfo.size > 0, true);

      // Verify metadata exists and is valid
      const metadataText = await Deno.readTextFile(metadataPath);
      const metadata: ChunkedEncryptionMetadata = JSON.parse(metadataText);
      assertEquals(metadata.originalSize, testData.length);
      assertExists(metadata.encryptedKey);
      assertExists(metadata.iv);

      // Verify original hash is correct
      const originalHash = await hashFile(inputPath);
      assertEquals(encryptResult.originalHash, originalHash);

      // Decrypt (using same key for test - in real scenario would use same key)
      const decryptResult = await hybridDecryptFileStreaming(
        encryptedPath,
        metadataPath,
        decryptedPath,
        keyPair.privateKey
      );

      // Verify decrypted file matches original
      const decryptedData = await Deno.readFile(decryptedPath);
      assertEquals(decryptedData.length, testData.length);
      assertEquals(decryptedData, testData);

      // Verify hash
      assertEquals(decryptResult.hashValid, true);
      assertEquals(decryptResult.originalHash, encryptResult.originalHash);
      assertEquals(decryptResult.computedHash, originalHash);

    } finally {
      await cleanup(inputPath, encryptedPath, metadataPath, decryptedPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  ignore: SKIP_LIT_TESTS,
  sanitizeOps: false,
  sanitizeResources: false,
});

// ============================================================================
// 2. Large File Tests
// ============================================================================

Deno.test({
  name: 'integration: large file (10MB) roundtrip',
  fn: async () => {
    await setup();

    const inputPath = `${TEST_DIR}/large-file.bin`;
    const encryptedPath = `${TEST_DIR}/large-file.bin.enc`;
    const metadataPath = `${TEST_DIR}/large-file.bin.meta`;
    const decryptedPath = `${TEST_DIR}/large-file-decrypted.bin`;

    try {
      const fileSize = 10 * 1024 * 1024; // 10MB
      const chunkSize = 1024 * 1024; // 1MB chunks

      // Generate large file without loading entirely into memory
      const file = await Deno.open(inputPath, { write: true, create: true });
      const chunk = generateRandomData(chunkSize);
      for (let i = 0; i < fileSize / chunkSize; i++) {
        await file.write(chunk);
      }
      file.close();

      // Generate key pair
      const keyPair = await generateKeyPair();

      // Encrypt
      await hybridEncryptFileStreaming(
        inputPath,
        encryptedPath,
        keyPair.privateKey,
        { metadataPath }
      );

      // Decrypt
      await hybridDecryptFileStreaming(
        encryptedPath,
        metadataPath,
        decryptedPath,
        keyPair.privateKey
      );

      // Verify files match by comparing hashes
      const originalHash = await hashFile(inputPath);
      const decryptedHash = await hashFile(decryptedPath);
      assertEquals(decryptedHash, originalHash);

      // Verify file sizes
      const inputInfo = await Deno.stat(inputPath);
      const decryptedInfo = await Deno.stat(decryptedPath);
      assertEquals(decryptedInfo.size, inputInfo.size);

    } finally {
      await cleanup(inputPath, encryptedPath, metadataPath, decryptedPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  ignore: SKIP_LIT_TESTS || !Deno.env.get('RUN_SLOW_TESTS'),
  sanitizeOps: false,
  sanitizeResources: false,
});

// ============================================================================
// 3. Format Compatibility Tests
// ============================================================================

Deno.test({
  name: 'integration: streaming output compatible with chunked format',
  fn: async () => {
    await setup();

    const inputPath = `${TEST_DIR}/compat-input.bin`;
    const encryptedPath = `${TEST_DIR}/compat-encrypted.bin`;
    const metadataPath = `${TEST_DIR}/compat-metadata.json`;

    try {
      // Create test file
      const testData = generateRandomData(1024 * 10);
      await Deno.writeFile(inputPath, testData);

      const keyPair = await generateKeyPair();

      // Encrypt with streaming
      await hybridEncryptFileStreaming(
        inputPath,
        encryptedPath,
        keyPair.privateKey,
        { metadataPath }
      );

      // Verify format matches expected structure
      const encryptedData = await Deno.readFile(encryptedPath);

      // First 16 bytes should be header
      assertEquals(encryptedData.length >= 16, true, 'Encrypted file should have at least header');

      const dataView = new DataView(encryptedData.buffer);
      const totalChunks = dataView.getUint32(0, false); // big-endian

      // IV follows (12 bytes at offset 4)
      const iv = encryptedData.slice(4, 16);
      assertEquals(iv.length, 12);

      // Verify chunks follow expected format
      let offset = 16;
      let chunkCount = 0;

      while (offset < encryptedData.length) {
        // Each chunk: 4 bytes index + 4 bytes length + encrypted data
        assertEquals(
          encryptedData.length >= offset + 8,
          true,
          `Not enough data for chunk header at offset ${offset}`
        );

        const chunkIndex = dataView.getUint32(offset, false);
        assertEquals(chunkIndex, chunkCount, `Chunk index mismatch at chunk ${chunkCount}`);

        const chunkLength = dataView.getUint32(offset + 4, false);
        assertEquals(chunkLength > 0, true, `Invalid chunk length at chunk ${chunkCount}`);

        offset += 8 + chunkLength;
        chunkCount++;
      }

      // Should have consumed all data
      assertEquals(offset, encryptedData.length, 'Should consume all encrypted data');
      assertEquals(chunkCount, totalChunks, 'Chunk count should match header');

    } finally {
      await cleanup(inputPath, encryptedPath, metadataPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  ignore: SKIP_LIT_TESTS,
  sanitizeOps: false,
  sanitizeResources: false,
});

// ============================================================================
// 4. Progress Callback Tests
// ============================================================================

Deno.test({
  name: 'integration: progress callbacks fire correctly',
  fn: async () => {
    await setup();

    const inputPath = `${TEST_DIR}/progress-test.bin`;
    const encryptedPath = `${TEST_DIR}/progress-test.bin.enc`;
    const metadataPath = `${TEST_DIR}/progress-test.bin.meta`;
    const decryptedPath = `${TEST_DIR}/progress-test-decrypted.bin`;

    try {
      // Create 2MB test file
      const fileSize = 2 * 1024 * 1024;
      const testData = generateRandomData(fileSize);
      await Deno.writeFile(inputPath, testData);

      const keyPair = await generateKeyPair();

      // Track encryption progress
      const encryptProgress: number[] = [];
      await hybridEncryptFileStreaming(
        inputPath,
        encryptedPath,
        keyPair.privateKey,
        {
          metadataPath,
          onProgress: (p) => encryptProgress.push(p.bytesProcessed),
          chunkSize: 512 * 1024, // 512KB chunks for more progress events
        }
      );

      // Should have progress events
      assertEquals(encryptProgress.length > 0, true, 'Should have encryption progress calls');
      // Final progress should equal file size
      assertEquals(
        encryptProgress[encryptProgress.length - 1],
        fileSize,
        'Final encryption progress should equal file size'
      );
      // Progress should be monotonic
      for (let i = 1; i < encryptProgress.length; i++) {
        assertEquals(
          encryptProgress[i] >= encryptProgress[i - 1],
          true,
          `Encryption progress should increase: ${encryptProgress[i - 1]} -> ${encryptProgress[i]}`
        );
      }

      // Track decryption progress
      const decryptProgress: number[] = [];
      await hybridDecryptFileStreaming(
        encryptedPath,
        metadataPath,
        decryptedPath,
        keyPair.privateKey,
        {
          onProgress: (p) => decryptProgress.push(p.bytesProcessed),
        }
      );

      // Should have progress events for decryption too
      assertEquals(decryptProgress.length > 0, true, 'Should have decryption progress calls');
      // Final progress should equal original file size
      assertEquals(
        decryptProgress[decryptProgress.length - 1],
        fileSize,
        'Final decryption progress should equal file size'
      );

    } finally {
      await cleanup(inputPath, encryptedPath, metadataPath, decryptedPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  ignore: SKIP_LIT_TESTS,
  sanitizeOps: false,
  sanitizeResources: false,
});

// ============================================================================
// 5. Error Handling Tests
// ============================================================================

Deno.test({
  name: 'integration: handles missing input file',
  fn: async () => {
    await setup();

    const keyPair = await generateKeyPair();

    try {
      await assertRejects(
        () =>
          hybridEncryptFileStreaming(
            `${TEST_DIR}/nonexistent.bin`,
            `${TEST_DIR}/output.bin`,
            keyPair.privateKey
          ),
        FileNotFoundError
      );
    } finally {
      await disconnectLitClient().catch(() => {});
    }
  },
  sanitizeOps: false,
  sanitizeResources: false,
});

Deno.test({
  name: 'integration: handles corrupted metadata',
  fn: async () => {
    await setup();

    const inputPath = `${TEST_DIR}/input.bin`;
    const encryptedPath = `${TEST_DIR}/encrypted.bin`;
    const metadataPath = `${TEST_DIR}/metadata.json`;
    const decryptedPath = `${TEST_DIR}/decrypted.bin`;

    try {
      // Create and encrypt file
      await Deno.writeFile(inputPath, new Uint8Array([1, 2, 3]));
      const keyPair = await generateKeyPair();

      await hybridEncryptFileStreaming(
        inputPath,
        encryptedPath,
        keyPair.privateKey,
        { metadataPath }
      );

      // Corrupt metadata
      await Deno.writeTextFile(metadataPath, 'invalid json');

      // Should throw when trying to decrypt
      await assertRejects(
        () =>
          hybridDecryptFileStreaming(
            encryptedPath,
            metadataPath,
            decryptedPath,
            keyPair.privateKey
          ),
        ParseError
      );

    } finally {
      await cleanup(inputPath, encryptedPath, metadataPath, decryptedPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  ignore: SKIP_LIT_TESTS,
  sanitizeOps: false,
  sanitizeResources: false,
});

Deno.test({
  name: 'integration: handles wrong private key',
  fn: async () => {
    await setup();

    const inputPath = `${TEST_DIR}/input.bin`;
    const encryptedPath = `${TEST_DIR}/encrypted.bin`;
    const metadataPath = `${TEST_DIR}/metadata.json`;
    const decryptedPath = `${TEST_DIR}/decrypted.bin`;

    try {
      // Create and encrypt file
      await Deno.writeFile(inputPath, new Uint8Array([1, 2, 3]));
      const encryptKeyPair = await generateKeyPair();
      const wrongKeyPair = await generateKeyPair();

      await hybridEncryptFileStreaming(
        inputPath,
        encryptedPath,
        encryptKeyPair.privateKey,
        { metadataPath }
      );

      // Should fail with wrong key - Lit will reject the decryption
      await assertRejects(
        () =>
          hybridDecryptFileStreaming(
            encryptedPath,
            metadataPath,
            decryptedPath,
            wrongKeyPair.privateKey
          ),
        DecryptionError
      );

    } finally {
      await cleanup(inputPath, encryptedPath, metadataPath, decryptedPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  ignore: SKIP_LIT_TESTS,
  sanitizeOps: false,
  sanitizeResources: false,
});

Deno.test({
  name: 'integration: handles missing encrypted file',
  fn: async () => {
    await setup();

    const metadataPath = `${TEST_DIR}/dummy.meta`;
    const decryptedPath = `${TEST_DIR}/decrypted.bin`;

    // Create a valid-looking metadata file
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

    const keyPair = await generateKeyPair();

    try {
      await assertRejects(
        () =>
          hybridDecryptFileStreaming(
            `${TEST_DIR}/nonexistent.enc`,
            metadataPath,
            decryptedPath,
            keyPair.privateKey
          ),
        FileNotFoundError
      );
    } finally {
      await cleanup(metadataPath);
    }
  },
  sanitizeOps: false,
  sanitizeResources: false,
});

Deno.test({
  name: 'integration: handles missing metadata file',
  fn: async () => {
    await setup();

    const encryptedPath = `${TEST_DIR}/dummy.enc`;
    const decryptedPath = `${TEST_DIR}/decrypted.bin`;

    // Create a dummy encrypted file
    await Deno.writeFile(encryptedPath, new Uint8Array([1, 2, 3, 4]));

    const keyPair = await generateKeyPair();

    try {
      await assertRejects(
        () =>
          hybridDecryptFileStreaming(
            encryptedPath,
            `${TEST_DIR}/nonexistent.meta`,
            decryptedPath,
            keyPair.privateKey
          ),
        FileNotFoundError
      );
    } finally {
      await cleanup(encryptedPath);
    }
  },
  sanitizeOps: false,
  sanitizeResources: false,
});

// ============================================================================
// 6. Edge Case Tests
// ============================================================================

Deno.test({
  name: 'integration: handles empty file',
  fn: async () => {
    await setup();

    const inputPath = `${TEST_DIR}/empty.bin`;
    const encryptedPath = `${TEST_DIR}/empty.bin.enc`;
    const metadataPath = `${TEST_DIR}/empty.bin.meta`;
    const decryptedPath = `${TEST_DIR}/empty-decrypted.bin`;

    try {
      // Create empty file
      await Deno.writeFile(inputPath, new Uint8Array(0));

      const keyPair = await generateKeyPair();

      // Encrypt
      await hybridEncryptFileStreaming(
        inputPath,
        encryptedPath,
        keyPair.privateKey,
        { metadataPath }
      );

      // Decrypt
      const decryptResult = await hybridDecryptFileStreaming(
        encryptedPath,
        metadataPath,
        decryptedPath,
        keyPair.privateKey
      );

      // Verify empty file roundtrip
      const decryptedData = await Deno.readFile(decryptedPath);
      assertEquals(decryptedData.length, 0);
      assertEquals(decryptResult.originalSize, 0);
      assertEquals(decryptResult.hashValid, true);

    } finally {
      await cleanup(inputPath, encryptedPath, metadataPath, decryptedPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  ignore: SKIP_LIT_TESTS,
  sanitizeOps: false,
  sanitizeResources: false,
});

Deno.test({
  name: 'integration: handles single byte file',
  fn: async () => {
    await setup();

    const inputPath = `${TEST_DIR}/single-byte.bin`;
    const encryptedPath = `${TEST_DIR}/single-byte.bin.enc`;
    const metadataPath = `${TEST_DIR}/single-byte.bin.meta`;
    const decryptedPath = `${TEST_DIR}/single-byte-decrypted.bin`;

    try {
      await Deno.writeFile(inputPath, new Uint8Array([42]));

      const keyPair = await generateKeyPair();

      await hybridEncryptFileStreaming(
        inputPath,
        encryptedPath,
        keyPair.privateKey,
        { metadataPath }
      );

      const result = await hybridDecryptFileStreaming(
        encryptedPath,
        metadataPath,
        decryptedPath,
        keyPair.privateKey
      );

      const decryptedData = await Deno.readFile(decryptedPath);
      assertEquals(decryptedData, new Uint8Array([42]));
      assertEquals(result.hashValid, true);
      assertEquals(result.originalSize, 1);

    } finally {
      await cleanup(inputPath, encryptedPath, metadataPath, decryptedPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  ignore: SKIP_LIT_TESTS,
  sanitizeOps: false,
  sanitizeResources: false,
});

Deno.test({
  name: 'integration: handles file exactly at chunk boundary',
  fn: async () => {
    await setup();

    const inputPath = `${TEST_DIR}/chunk-boundary.bin`;
    const encryptedPath = `${TEST_DIR}/chunk-boundary.bin.enc`;
    const metadataPath = `${TEST_DIR}/chunk-boundary.bin.meta`;
    const decryptedPath = `${TEST_DIR}/chunk-boundary-decrypted.bin`;

    try {
      // Create file exactly 2 chunks worth
      const chunkSize = 256 * 1024;
      const testData = generateRandomData(chunkSize * 2);
      await Deno.writeFile(inputPath, testData);

      const keyPair = await generateKeyPair();

      await hybridEncryptFileStreaming(
        inputPath,
        encryptedPath,
        keyPair.privateKey,
        { metadataPath, chunkSize }
      );

      const result = await hybridDecryptFileStreaming(
        encryptedPath,
        metadataPath,
        decryptedPath,
        keyPair.privateKey
      );

      // Verify
      const decryptedData = await Deno.readFile(decryptedPath);
      assertEquals(decryptedData, testData);
      assertEquals(result.hashValid, true);

      // Verify metadata
      const metadataText = await Deno.readTextFile(metadataPath);
      const metadata: ChunkedEncryptionMetadata = JSON.parse(metadataText);
      assertEquals(metadata.totalChunks, 2);

    } finally {
      await cleanup(inputPath, encryptedPath, metadataPath, decryptedPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  ignore: SKIP_LIT_TESTS,
  sanitizeOps: false,
  sanitizeResources: false,
});

Deno.test({
  name: 'integration: handles file slightly larger than chunk boundary',
  fn: async () => {
    await setup();

    const inputPath = `${TEST_DIR}/chunk-boundary-plus.bin`;
    const encryptedPath = `${TEST_DIR}/chunk-boundary-plus.bin.enc`;
    const metadataPath = `${TEST_DIR}/chunk-boundary-plus.bin.meta`;
    const decryptedPath = `${TEST_DIR}/chunk-boundary-plus-decrypted.bin`;

    try {
      // Create file 2 chunks + 1 byte
      const chunkSize = 256 * 1024;
      const testData = generateRandomData(chunkSize * 2 + 1);
      await Deno.writeFile(inputPath, testData);

      const keyPair = await generateKeyPair();

      await hybridEncryptFileStreaming(
        inputPath,
        encryptedPath,
        keyPair.privateKey,
        { metadataPath, chunkSize }
      );

      const result = await hybridDecryptFileStreaming(
        encryptedPath,
        metadataPath,
        decryptedPath,
        keyPair.privateKey
      );

      // Verify
      const decryptedData = await Deno.readFile(decryptedPath);
      assertEquals(decryptedData, testData);
      assertEquals(result.hashValid, true);

      // Verify metadata
      const metadataText = await Deno.readTextFile(metadataPath);
      const metadata: ChunkedEncryptionMetadata = JSON.parse(metadataText);
      assertEquals(metadata.totalChunks, 3);

    } finally {
      await cleanup(inputPath, encryptedPath, metadataPath, decryptedPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  ignore: SKIP_LIT_TESTS,
  sanitizeOps: false,
  sanitizeResources: false,
});

// ============================================================================
// 7. Metadata Validation Tests
// ============================================================================

Deno.test({
  name: 'integration: metadata contains all required fields',
  fn: async () => {
    await setup();

    const inputPath = `${TEST_DIR}/metadata-check.bin`;
    const encryptedPath = `${TEST_DIR}/metadata-check.bin.enc`;
    const metadataPath = `${TEST_DIR}/metadata-check.bin.meta`;

    try {
      const testData = generateRandomData(1024);
      await Deno.writeFile(inputPath, testData);

      const keyPair = await generateKeyPair();

      await hybridEncryptFileStreaming(
        inputPath,
        encryptedPath,
        keyPair.privateKey,
        { metadataPath }
      );

      const metadataText = await Deno.readTextFile(metadataPath);
      const metadata: ChunkedEncryptionMetadata = JSON.parse(metadataText);

      // Verify all required fields
      assertEquals(metadata.version, 'hybrid-v1');
      assertExists(metadata.encryptedKey);
      assertExists(metadata.keyHash);
      assertExists(metadata.iv);
      assertEquals(metadata.algorithm, 'AES-GCM');
      assertEquals(metadata.keyLength, 256);
      assertExists(metadata.accessControlConditions);
      assertEquals(metadata.accessControlConditions.length > 0, true);
      assertExists(metadata.chain);
      assertEquals(metadata.originalSize, 1024);
      assertExists(metadata.originalHash);
      assertEquals(metadata.chunked, true);
      assertExists(metadata.totalChunks);
      assertExists(metadata.chunkSize);

    } finally {
      await cleanup(inputPath, encryptedPath, metadataPath);
      await disconnectLitClient().catch(() => {});
    }
  },
  ignore: SKIP_LIT_TESTS,
  sanitizeOps: false,
  sanitizeResources: false,
});

// ============================================================================
// Cleanup
// ============================================================================

Deno.test({
  name: 'integration: cleanup test directory',
  fn: async () => {
    await cleanupAll();
  },
  sanitizeOps: false,
  sanitizeResources: false,
});
