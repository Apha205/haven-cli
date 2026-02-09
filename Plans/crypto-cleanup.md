# Crypto Code Cleanup Plan

## Streaming SHA256 - Candidate for Removal

### Current State

The `sha256HashStream` function in `js-services/crypto/utils-streaming.ts` computes a SHA256 hash of file content during encryption and stores it in the metadata. On decryption, the hash is recomputed and compared to verify file integrity.

### Why It Exists Now

This was implemented as a verification mechanism during development to confirm that the encryption → upload → download → decryption pipeline produces bit-for-bit identical output to the original file. It's useful for:

1. Verifying our workflow is correct end-to-end
2. Debugging issues in the pipeline steps
3. Providing visible proof that each step preserves data integrity

### Why It's Likely Redundant

The Synapse SDK (Filecoin/IPFS upload) already handles content integrity via CID verification. Additionally, AES-GCM authentication catches tampering of encrypted data. The SHA256 hash is therefore a duplicate integrity check.

### Cleanup Criteria

Remove `sha256HashStream` and related hash verification code **after**:

- [ ] End-to-end workflow verified working (upload a video, retrieve it, confirm playable)
- [ ] Confirm Synapse SDK CID verification is sufficient for our needs
- [ ] Confirm AES-GCM auth tag validation is working correctly in decryption

### Files to Clean Up

| File | Changes |
|------|---------|
| `js-services/crypto/utils-streaming.ts` | Remove `sha256HashStream` and `sha256HashStreamAccumulated` |
| `js-services/crypto/mod.ts` | Remove exports of hash stream functions |
| `js-services/hybrid-crypto.ts` | Remove hash computation during encrypt/decrypt, remove `originalHash` from metadata |
| `js-services/crypto/types.ts` | Remove `originalHash` from metadata types |
| `js-services/crypto/utils-streaming_test.ts` | Remove hash stream tests |

### Estimated Effort

~2-3 hours once cleanup criteria are met.

### Notes

Keep this code for now. It's not hurting anything and provides valuable verification during the development phase. The streaming implementation is memory-efficient so there's no performance penalty.
