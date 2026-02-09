/**
 * Type definitions for hybrid encryption system.
 */

export type ChainName =
  | 'ethereum'
  | 'sepolia'
  | 'goerli'
  | 'polygon'
  | 'mumbai'
  | 'bsc'
  | 'avalanche'
  | 'fuji'
  | 'arbitrum'
  | 'optimism'
  | 'base'
  | 'filecoin'
  | 'yellowstone'
  | 'fantom'
  | 'xdai';

export type StandardContractType =
  | ''
  | 'PKPPermissions'
  | 'timestamp'
  | 'ERC20'
  | 'ERC721'
  | 'ERC721MetadataName'
  | 'ERC1155'
  | 'CASK'
  | 'Creaton'
  | 'POAP'
  | 'MolochDAOv2.1'
  | 'ProofOfHumanity'
  | 'SIWE'
  | 'LitAction';

export type ReturnValueComparator = '=' | 'contains' | '>' | '>=' | '<' | '<=';

export interface ReturnValueTest {
  comparator: ReturnValueComparator;
  value: string;
}

export interface EvmBasicAccessControlCondition {
  contractAddress: string;
  standardContractType: StandardContractType;
  chain: ChainName;
  method: string;
  parameters: string[];
  returnValueTest: ReturnValueTest;
}

export interface UnifiedAccessControlCondition extends EvmBasicAccessControlCondition {
  conditionType: 'evmBasic';
}

export interface HybridEncryptionMetadata {
  /** Version identifier for future compatibility */
  version: 'hybrid-v1';
  /** BLS-encrypted AES key (base64-encoded ciphertext from Lit) */
  encryptedKey: string;
  /** SHA-256 hash of the AES key (for verification) */
  keyHash: string;
  /** Base64-encoded 12-byte IV for AES-GCM */
  iv: string;
  /** AES algorithm identifier */
  algorithm: 'AES-GCM';
  /** Key length in bits */
  keyLength: 256;
  /** Access control conditions for Lit decryption */
  accessControlConditions: EvmBasicAccessControlCondition[];
  /** Blockchain chain identifier */
  chain: string;
  /** Optional: Original file MIME type */
  originalMimeType?: string;
  /** Optional: Original file size in bytes */
  originalSize?: number;
  /** Optional: SHA-256 hash of original file content */
  originalHash?: string;
}

export interface HybridEncryptionResult {
  /** AES-encrypted file data */
  encryptedFile: Uint8Array;
  /** Metadata needed for decryption */
  metadata: HybridEncryptionMetadata;
}

/** Extended metadata for chunked encryption */
export interface ChunkedEncryptionMetadata extends HybridEncryptionMetadata {
  /** Indicates this file was encrypted with chunked processing */
  chunked: true;
  /** Number of chunks the file was split into */
  totalChunks: number;
  /** Size of each chunk in bytes (except possibly the last) */
  chunkSize: number;
}

/** Result type for chunked hybrid decryption */
export interface ChunkedDecryptionResult {
  /** Decrypted file data */
  data: Uint8Array;
  /** Whether the file was in chunked format */
  wasChunked: boolean;
}

/** Progress callback for chunked encryption with precise percentage */
export type EncryptionProgressCallback = (
  percent: number,
  bytesProcessed: number,
  totalBytes: number
) => void;

/** Message-based progress callback */
export type MessageProgressCallback = (message: string) => void;

// ============================================================================
// Streaming Types
// ============================================================================

/**
 * Callback for reporting progress of streaming operations
 */
export type StreamProgressCallback = (progress: {
  /** Total bytes processed so far */
  bytesProcessed: number;
  /** Total bytes if known, undefined for indeterminate streams */
  totalBytes?: number;
  /** Percentage complete (0-100), undefined if total unknown */
  percent?: number;
  /** Current chunk index being processed */
  chunkIndex?: number;
  /** Total number of chunks if known */
  totalChunks?: number;
}) => void;

/**
 * Options for file-based streaming operations
 */
export interface FileStreamOptions {
  /** Size of chunks to read/write in bytes (default: 1MB) */
  chunkSize?: number;

  /** Callback for progress updates */
  onProgress?: StreamProgressCallback;

  /** Callback when each chunk is processed (for fine-grained tracking) */
  onChunkProcessed?: (chunkIndex: number, chunkSize: number) => void;

  /** Signal for cancellation */
  signal?: AbortSignal;
}

/**
 * Result of a streaming encryption operation
 */
export interface StreamingEncryptionResult {
  /** Path to the encrypted file */
  encryptedPath: string;

  /** Path to the metadata file */
  metadataPath: string;

  /** SHA-256 hash of the original file (hex string) */
  originalHash: string;

  /** Size of the encrypted file in bytes */
  encryptedSize: number;

  /** Number of chunks the file was split into */
  chunkCount: number;

  /** Size of the original file in bytes */
  originalSize: number;
}

/**
 * Result of a streaming decryption operation
 */
export interface StreamingDecryptionResult {
  /** Path to the decrypted file */
  decryptedPath: string;

  /** SHA-256 hash from metadata (expected) */
  originalHash: string;

  /** SHA-256 hash of the decrypted file (computed) */
  computedHash: string;

  /** Whether the computed hash matches the original */
  hashValid: boolean;

  /** Size of the original file from metadata */
  originalSize: number;

  /** Size of the decrypted file */
  decryptedSize: number;
}

/**
 * Information about a chunk in a streaming operation
 */
export interface ChunkInfo {
  /** Index of the chunk (0-based) */
  index: number;

  /** Size of the original (unencrypted) data */
  originalSize: number;

  /** Size of the encrypted data (includes auth tag) */
  encryptedSize: number;

  /** IV used for this chunk (derived from main IV) */
  iv: Uint8Array;
}

/**
 * Header for streaming encrypted format
 */
export interface StreamHeader {
  /** Total number of chunks (0 for unknown/indeterminate) */
  totalChunks: number;

  /** 12-byte initialization vector */
  iv: Uint8Array;
}

/**
 * Options for AES encryption streams
 */
export interface EncryptionStreamOptions {
  /** Encryption key (32 bytes for AES-256) */
  key: Uint8Array;

  /** Initialization vector (12 bytes for GCM) */
  iv?: Uint8Array;

  /** Total size of data if known (for progress calculation) */
  totalSize?: number;

  /** Chunk size for internal processing */
  chunkSize?: number;

  /** Progress callback */
  onProgress?: StreamProgressCallback;
}

/**
 * Options for AES decryption streams
 */
export interface DecryptionStreamOptions {
  /** Decryption key (32 bytes for AES-256) */
  key: Uint8Array;

  /** Expected number of chunks for validation */
  expectedChunks?: number;

  /** Expected hash for verification */
  expectedHash?: string;

  /** Progress callback */
  onProgress?: StreamProgressCallback;
}

/** Encrypted chunk with header for streaming output */
export interface EncryptedChunk {
  /** Chunk index (4 bytes, big-endian) */
  chunkIndex: number;
  /** Encrypted data including auth tag */
  data: Uint8Array;
}

/** Decrypted chunk with metadata */
export interface DecryptedChunk {
  /** Chunk index */
  chunkIndex: number;
  /** Decrypted data */
  data: Uint8Array;
  /** Whether this is the last chunk */
  isLast: boolean;
}
