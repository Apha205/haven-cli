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
