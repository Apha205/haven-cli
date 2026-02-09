# Upload Memory Investigation Report

## Summary

The Synapse SDK upload step has a memory issue caused by loading the entire CAR file into memory before upload. This investigation traces the data flow from the Python CLI through the JavaScript bridge to the Synapse SDK.

## Root Cause Analysis

### Data Flow Trace

```
Python (upload_step.py)
    ↓ JSON-RPC call "synapse.upload"
JavaScript (synapse-wrapper.ts)
    ↓ Deno.readFile() ← ENTIRE CAR FILE LOADED INTO MEMORY
filecoin-pin (upload/synapse.ts)
    ↓ uploadToSynapse(carData: Uint8Array)
synapse-sdk (storage/context.ts)
    ↓ StorageContext.upload(data: Uint8Array | ReadableStream)
PDP Server
```

### Critical Memory Hotspot

**File:** `js-services/synapse-wrapper.ts` (line ~430)

```typescript
// Read CAR file - THIS LOADS ENTIRE FILE INTO MEMORY
const carBytes = await Deno.readFile(carBuildResult.carPath);
```

This `Deno.readFile()` call loads the entire CAR file into a `Uint8Array` in memory. For a 1 GiB file:
- Original file: ~1 GiB
- CAR file: ~1.01 GiB (1% overhead)
- **Peak memory: ~2+ GiB** (original + CAR + encrypted data buffers)

### The SDK Already Supports Streaming!

**File:** `synapse-sdk/packages/synapse-sdk/src/storage/context.ts` (line ~680)

```typescript
/**
 * Upload data to the service provider
 *
 * Accepts Uint8Array or ReadableStream<Uint8Array>.
 * For large files, prefer streaming to minimize memory usage.
 */
async upload(data: Uint8Array | ReadableStream<Uint8Array>, options?: UploadOptions): Promise<UploadResult>
```

The Synapse SDK's `StorageContext.upload()` method **already accepts `ReadableStream<Uint8Array>`** for memory-efficient streaming uploads. However, the current implementation in `synapse-wrapper.ts` only uses `Uint8Array`.

### Missing Link: filecoin-pin's executeUpload

**File:** `filecoin-pin/src/core/upload/synapse.ts`

```typescript
export async function uploadToSynapse(
  synapseService: SynapseService,
  carData: Uint8Array,  // ← Only accepts Uint8Array, not ReadableStream
  rootCid: CID,
  logger: Logger,
  options: SynapseUploadOptions = {}
): Promise<SynapseUploadResult>
```

The `uploadToSynapse` function in filecoin-pin only accepts `Uint8Array`, not `ReadableStream`. This is the intermediary layer that needs to be updated to support streaming.

## Memory Impact Calculation

| Component | Size | Notes |
|-----------|------|-------|
| Original file | 1 GiB | User's encrypted file |
| CAR file | 1.01 GiB | CAR format adds ~1% overhead |
| CAR in memory | 1.01 GiB | `Deno.readFile()` result |
| Upload buffers | ~256 MiB | Network chunk buffers |
| **Peak memory** | **~2.3 GiB** | All buffers in memory simultaneously |

With the current timeout workaround (180 seconds), uploads are interrupted before memory grows too large, but this is not a real solution.

## Proposed Solutions

### Option 1: Stream CAR File to Upload (Recommended)

Modify `synapse-wrapper.ts` to use streaming:

```typescript
// Instead of:
const carBytes = await Deno.readFile(carBuildResult.carPath);

// Use:
const file = await Deno.open(carBuildResult.carPath, { read: true });
const carStream = readableStreamFromReader(file);
```

**Requirements:**
1. Update `filecoin-pin`'s `uploadToSynapse()` to accept `ReadableStream`
2. Or bypass `uploadToSynapse()` and call `synapse.storage.upload()` directly with a stream

**Pros:**
- Memory usage drops to O(chunk size) ~2-4 MiB
- No file size limitations
- Clean architecture

**Cons:**
- Requires changes to filecoin-pin package (external dependency)
- Need to handle stream errors gracefully

### Option 2: Chunk Large Files

Split files larger than a threshold into smaller pieces:

```typescript
const CHUNK_SIZE = 100 * 1024 * 1024; // 100 MiB
if (fileSize > CHUNK_SIZE) {
  // Upload in chunks
}
```

**Pros:**
- Works with existing API
- Bounded memory usage

**Cons:**
- More complex upload logic
- Multiple pieces to track
- Reassembly complexity on download

### Option 3: Memory-Mapped File I/O

Use Deno's FFI to memory-map the CAR file:

```typescript
// Using Deno FFI for mmap
const mapped = mmap(fd, fileSize);
```

**Pros:**
- OS manages memory paging
- Appears as contiguous memory to application

**Cons:**
- Platform-specific code
- Still requires virtual address space
- Complex error handling

### Option 4: Direct Streaming Bypass

Create a new upload path that bypasses the in-memory CAR:

```typescript
// In synapse-wrapper.ts
async uploadStream(filePath: string, ...): Promise<UploadResult> {
  const file = await Deno.open(filePath, { read: true });
  const stream = readableStreamFromReader(file);
  
  // Call SDK directly, bypassing filecoin-pin's uploadToSynapse
  const result = await this._synapse.storage.upload(stream, options);
  return result;
}
```

**Pros:**
- No changes to external packages needed
- Maximum control over memory usage

**Cons:**
- Duplicates some logic from filecoin-pin
- Need to handle CAR creation differently

## Recommended Investigation Steps

### Short-term (Immediate)

1. **Verify streaming support in synapse-sdk**
   - Test `StorageContext.upload()` with a `ReadableStream`
   - Confirm `_pdpServer.uploadPiece()` handles streams correctly
   - Measure actual memory usage with streaming

2. **Check filecoin-pin's willingness to accept streaming PR**
   - Open issue/discussion on filecoin-pin repository
   - Propose adding `ReadableStream` support to `uploadToSynapse()`

3. **Profile current memory usage**
   ```bash
   # Use Deno's memory profiling
   deno --v8-flags=--prof run js-services/main.ts
   
   # Or use heapdump
   deno --v8-flags=--heap-prof run js-services/main.ts
   ```

### Medium-term

4. **Implement streaming in synapse-wrapper.ts**
   - Create a streaming upload method
   - Test with large files (>500 MiB)
   - Compare memory profiles before/after

5. **Consider CAR streaming creation**
   - Current: Build CAR to disk → Read entire CAR → Upload
   - Target: Build CAR directly to upload stream
   - This would eliminate the intermediate CAR file entirely

### Long-term

6. **Contribute streaming support upstream**
   - Submit PR to filecoin-pin for `ReadableStream` support
   - Submit PR to synapse-sdk for improved streaming documentation

## Code References

| File | Line | Issue |
|------|------|-------|
| `js-services/synapse-wrapper.ts` | ~430 | `Deno.readFile()` loads entire CAR |
| `filecoin-pin/src/core/upload/synapse.ts` | ~70 | `carData: Uint8Array` only |
| `synapse-sdk/storage/context.ts` | ~680 | Supports `ReadableStream` already |
| `haven_cli/pipeline/steps/upload_step.py` | ~345 | 180s timeout workaround |

## Progress Events: Synthetic vs Real

**Current Implementation:** `synapse-wrapper.ts` creates **synthetic progress events** with hardcoded percentages:

```typescript
// These are NOT real upload progress - just phase markers
onProgress?.({ bytesUploaded: 0, totalBytes: carBytes.length, percentage: 0 });   // Start
onProgress?.({ bytesUploaded: 0, totalBytes: carBytes.length, percentage: 5 });    // After init
onProgress?.({ bytesUploaded: 0, totalBytes: carBytes.length, percentage: 10 });   // After synapse init
onProgress?.({ bytesUploaded: 0, totalBytes: carBytes.length, percentage: 20 });   // After CAR build
onProgress?.({ bytesUploaded: 0, totalBytes: carBytes.length, percentage: 25 });   // After readFile
onProgress?.({ bytesUploaded: 0, totalBytes: carBytes.length, percentage: 30 });   // After readiness
onProgress?.({ bytesUploaded: 0, totalBytes: carBytes.length, percentage: 35 });   // After context
// ... then jumps to 80% when upload completes
```

**The SDK Provides Real Byte-Level Progress:**

`synapse-sdk/packages/synapse-core/src/sp.ts` (line ~520):
```typescript
// Real progress from actual network upload
let bytesUploaded = 0
const trackingStream = new TransformStream<Uint8Array, Uint8Array>({
  transform(chunk, controller) {
    bytesUploaded += chunk.length
    if (options.onProgress) {
      options.onProgress(bytesUploaded)  // Real bytes uploaded!
    }
    controller.enqueue(chunk)
  },
})
```

`synapse-sdk/packages/synapse-sdk/src/types.ts`:
```typescript
export interface UploadCallbacks {
  /** Called periodically during upload with bytes uploaded so far */
  onProgress?: (bytesUploaded: number) => void  // ← REAL progress!
  onUploadComplete?: (pieceCid: PieceCID) => void
  onPiecesAdded?: (transaction: Hex, pieces?: { pieceCid: PieceCID }[]) => void
  onPieceConfirmed?: (pieceIds: bigint[]) => void
}
```

**The Problem:**

1. The wrapper ignores the SDK's `onProgress` callback that provides real byte-level progress
2. Progress jumps from 35% → 80% with no intermediate updates during the actual upload
3. `bytesUploaded` is always 0 or `carBytes.length` - never actual transfer progress
4. Users see a progress bar that sits at 35% then suddenly completes

**Fix Required:**

Pass the `onProgress` callback through to the SDK to get real upload progress:

```typescript
// In synapse-wrapper.ts - pass through real progress
const uploadResult = await executeUpload(synapseService as any, carBytes, rootCidString as any, {
  logger: this._logger,
  contextId: filePath.split('/').pop() || 'upload',
  onProgress: (event: { type: string; data?: any }) => {
    if (event.type === 'onProgress' && event.data?.bytesUploaded) {
      // Real progress from SDK!
      const percentage = 35 + Math.round((event.data.bytesUploaded / carBytes.length) * 45); // 35-80%
      onProgress?.({
        bytesUploaded: event.data.bytesUploaded,
        totalBytes: carBytes.length,
        percentage,
      });
    }
    // ... handle other events
  },
});
```

**Investigation of `filecoin-pin`:**

The `filecoin-pin`'s `uploadToSynapse()` function does **NOT** pass through the byte-level `onProgress` callback:

```typescript
// filecoin-pin/src/core/upload/synapse.ts
const uploadCallbacks: UploadCallbacks = {
  onUploadComplete: (pieceCid) => { ... },  // ✓ Passed
  onPieceAdded: (txHash) => { ... },        // ✓ Passed  
  onPieceConfirmed: (pieceIds) => { ... },  // ✓ Passed
  // onProgress: ???                         // ✗ NOT PASSED!
};
```

The SDK's `onProgress(bytesUploaded)` callback that provides real-time byte-level progress is **completely ignored** by `filecoin-pin`.

**Summary of Progress Issues:**

| Layer | Has Real Progress? | Passes It Through? |
|-------|-------------------|-------------------|
| synapse-core (sp.ts) | ✓ Yes - `onProgress(bytesUploaded)` | N/A (lowest layer) |
| synapse-sdk (context.ts) | ✓ Accepts `onProgress` in UploadOptions | ✓ Calls SDK's callback |
| filecoin-pin (upload/synapse.ts) | ✗ No - only milestone events | ✗ Does NOT pass `onProgress` |
| synapse-wrapper.ts | ✗ No - synthetic percentages | ✗ Cannot receive real progress |

**Fix Required in `filecoin-pin`:**

```typescript
// In uploadToSynapse(), add:
const uploadCallbacks: UploadCallbacks = {
  onProgress: (bytesUploaded) => {
    onProgress?.({ type: 'onProgress', data: { bytesUploaded } })
  },
  onUploadComplete: (pieceCid) => { ... },
  // ...
};
```

## Conclusion

The memory issue is caused by `Deno.readFile()` loading the entire CAR file into memory. The Synapse SDK already supports streaming uploads via `ReadableStream<Uint8Array>`, but the intermediary `filecoin-pin` package's `uploadToSynapse()` function only accepts `Uint8Array`.

**The fix requires either:**
1. Updating `filecoin-pin` to support streaming (preferred, benefits everyone)
2. Bypassing `filecoin-pin` and calling `synapse.storage.upload()` directly with a stream

Both approaches would reduce memory usage from O(file size) to O(chunk size), eliminating the need for the timeout workaround.
