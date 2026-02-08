/**
 * Crypto module index
 * 
 * Re-exports all public APIs from the hybrid encryption system.
 */

// Types
export type {
  EvmBasicAccessControlCondition,
  UnifiedAccessControlCondition,
  HybridEncryptionMetadata,
  HybridEncryptionResult,
  ChunkedEncryptionMetadata,
  ChunkedDecryptionResult,
  EncryptionProgressCallback,
  MessageProgressCallback,
  ChainName,
  StandardContractType,
  ReturnValueComparator,
  ReturnValueTest,
} from './types.ts';

// Constants
export {
  AES_KEY_SIZE,
  AES_IV_SIZE,
  AES_AUTH_TAG_SIZE,
  DEFAULT_CHUNK_SIZE,
  CHUNKED_THRESHOLD,
  CHUNKED_HEADER_SIZE,
  CHUNK_OVERHEAD,
} from './constants.ts';

// AES encryption
export {
  generateAESKey,
  generateIV,
  aesEncrypt,
  aesDecrypt,
  aesEncryptChunked,
  aesDecryptChunked,
  getChunkedEncryptedSize,
  isChunkedEncryption,
  getEncryptedSize,
} from './aes.ts';

// Access control
export {
  normalizePrivateKey,
  getWalletAddressFromPrivateKey,
  createOwnerOnlyAccessControlConditions,
  toUnifiedAccessControlConditions,
} from './access-control.ts';

// Lit client
export {
  initLitClient,
  disconnectLitClient,
  getLitClient,
  getAuthManager,
  isLitClientConnected,
  encryptWithLit,
  decryptWithLit,
  encryptAesKeyWithLit,
} from './lit-client.ts';

// Utilities
export {
  arrayBufferToBase64,
  base64ToArrayBuffer,
  sha256Hash,
  secureClear,
} from './utils.ts';
