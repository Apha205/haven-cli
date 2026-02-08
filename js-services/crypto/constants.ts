/**
 * Constants for hybrid encryption system.
 */

/** AES-256 key size in bytes */
export const AES_KEY_SIZE = 32;

/** AES-GCM IV size in bytes */
export const AES_IV_SIZE = 12;

/** AES-GCM authentication tag size in bytes */
export const AES_AUTH_TAG_SIZE = 16;

/** Default chunk size for progress reporting: 1MB */
export const DEFAULT_CHUNK_SIZE = 1024 * 1024;

/** Threshold for automatic chunked encryption: 50MB */
export const CHUNKED_THRESHOLD = 50 * 1024 * 1024;

/** Header size for chunked encryption format: 4 bytes (chunk count) + 12 bytes (IV) */
export const CHUNKED_HEADER_SIZE = 16;

/** Per-chunk overhead: 4 bytes (index) + 4 bytes (length) + 16 bytes (auth tag) */
export const CHUNK_OVERHEAD = 4 + 4 + AES_AUTH_TAG_SIZE;
