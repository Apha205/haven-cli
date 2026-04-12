/**
 * Synapse Node.js Runtime
 *
 * JSON-RPC 2.0 server for Filecoin upload via the Synapse SDK (filecoin-pin).
 * Runs under Node.js (not Deno) because filecoin-pin uses Node.js native modules
 * that are incompatible with Deno's internal APIs.
 *
 * This is a faithful port of synapse-wrapper.ts — same business logic,
 * same API calls, just replacing Deno.* with Node.js equivalents.
 *
 * Environment variables:
 *   HAVEN_PRIVATE_KEY or PRIVATE_KEY  — wallet private key (hex, with or without 0x)
 *   HAVEN_FILECOIN_RPC_URL            — Filecoin WebSocket RPC URL
 *   FILECOIN_RPC_URL                  — fallback RPC URL
 */

import { createInterface } from 'node:readline';
import { readFile, stat } from 'node:fs/promises';

// ── Config ────────────────────────────────────────────────────────────────────

function getPrivateKey() {
  const key = process.env.HAVEN_PRIVATE_KEY ?? process.env.PRIVATE_KEY ?? '';
  if (!key) throw new Error('[synapse-node] HAVEN_PRIVATE_KEY not set');
  return key.startsWith('0x') ? key : `0x${key}`;
}

function getRpcUrl(networkMode = 'testnet') {
  return (
    process.env.HAVEN_FILECOIN_RPC_URL ??
    process.env.FILECOIN_RPC_URL ??
    (networkMode === 'mainnet'
      ? 'wss://node.glif.io/apiw/gw/lotus/rpc/v1'
      : 'wss://api.calibration.node.glif.io/rpc/v1')
  );
}

// ── Pino-compatible logger ────────────────────────────────────────────────────
// filecoin-pin calls logger.info({event:'...'}, 'message') — pino style.
// We handle both (obj, msg) and (msg, ...args) signatures.

function createLogger(prefix = '[Synapse]') {
  const isDebug = process.env.DEBUG === '1' || process.env.LOG_LEVEL?.toLowerCase() === 'debug';

  function write(level, ...args) {
    let msg;
    if (args.length >= 2 && typeof args[0] === 'object' && args[0] !== null) {
      // pino style: (obj, msg)
      msg = String(args[1]);
    } else {
      msg = args.map(a => (typeof a === 'object' ? JSON.stringify(a) : String(a))).join(' ');
    }
    process.stderr.write(`${prefix} ${level}: ${msg}\n`);
  }

  return {
    level: isDebug ? 'debug' : 'info',
    info:  (...args) => write('INFO',  ...args),
    warn:  (...args) => write('WARN',  ...args),
    error: (...args) => write('ERROR', ...args),
    debug: (...args) => { if (isDebug) write('DEBUG', ...args); },
    fatal: (...args) => write('FATAL', ...args),
    trace: (...args) => { if (isDebug) write('TRACE', ...args); },
    silent: () => {},
    msgPrefix: prefix,
    child: () => createLogger(prefix),
  };
}

// ── State ─────────────────────────────────────────────────────────────────────

let _isConnected = false;
let _rpcUrl = '';
let _privateKey = '';

// ── Helpers ───────────────────────────────────────────────────────────────────

function withTimeout(operationName, promise, timeoutMs) {
  let timeoutId;
  const timeoutPromise = new Promise((_, reject) => {
    timeoutId = setTimeout(() => {
      reject(new Error(
        `${operationName} timed out after ${timeoutMs}ms. ` +
        `This may be due to Filecoin RPC connectivity issues. ` +
        `Check your network connection and RPC endpoint status.`
      ));
    }, timeoutMs);
  });
  return Promise.race([promise, timeoutPromise]).finally(() => clearTimeout(timeoutId));
}

// ── Method handlers ───────────────────────────────────────────────────────────

async function handlePing() {
  return 'pong';
}

async function handleGetStatus() {
  return {
    version: '1.0.0',
    uptimeSeconds: process.uptime(),
    synapseConnected: _isConnected,
    litConnected: false,
    runtime: 'node',
    provider: 'synapse',
  };
}

async function handleSynapseConnect(params) {
  const networkMode = params.networkMode ?? 'testnet';
  _privateKey = params.privateKey ?? getPrivateKey();
  _rpcUrl = params.rpcUrl ?? getRpcUrl(networkMode);

  // Just validate credentials are present — actual Synapse init happens per-upload
  // (same as synapse-wrapper.ts which inits inside upload())
  _isConnected = true;
  process.stderr.write(`[synapse-node] Connected (RPC: ${_rpcUrl})\n`);
  return { connected: true, endpoint: _rpcUrl };
}

async function handleSynapseUpload(params, notifyProgress) {
  if (!_isConnected) {
    throw new Error('Synapse not connected. Call synapse.connect first.');
  }

  const filePath = params.filePath;
  if (!filePath) throw new Error('Missing required parameter: filePath');

  // Check file exists and get size
  let fileStat;
  try {
    fileStat = await stat(filePath);
  } catch (error) {
    throw new Error(`Cannot read file: ${filePath} - ${error.message}`);
  }
  const fileSize = fileStat.size;

  process.stderr.write(`[synapse-node] Uploading file: ${filePath} (${fileSize} bytes)\n`);

  // Load filecoin-pin modules
  const { initializeSynapse, createStorageContext, cleanupSynapseService } =
    await import('filecoin-pin/core/synapse');
  const { createUnixfsCarBuilder } = await import('filecoin-pin/core/unixfs');
  const { executeUpload, checkUploadReadiness } = await import('filecoin-pin/core/upload');

  const logger = createLogger('[Synapse]');

  // Normalize private key
  const normalizedPrivateKey = _privateKey.startsWith('0x') ? _privateKey : `0x${_privateKey}`;

  notifyProgress?.({ bytesUploaded: 0, totalBytes: fileSize, percentage: 5 });

  // 1. Initialize Synapse — same config as synapse-wrapper.ts
  const initConfig = {
    privateKey: normalizedPrivateKey,
    rpcUrl: _rpcUrl,
    telemetry: {
      sentryInitOptions: { enabled: false },
    },
  };

  process.stderr.write(`[synapse-node] Initializing Synapse SDK...\n`);
  const synapse = await initializeSynapse(initConfig, logger);

  notifyProgress?.({ bytesUploaded: 0, totalBytes: fileSize, percentage: 10 });

  // 2. Create CAR file — buildCar(filePath, options) with bare:true
  process.stderr.write(`[synapse-node] Creating CAR file...\n`);
  const unixfsCarBuilder = createUnixfsCarBuilder();
  const carBuildResult = await unixfsCarBuilder.buildCar(filePath, {
    logger,
    bare: true,
  });

  notifyProgress?.({ bytesUploaded: 0, totalBytes: fileSize, percentage: 20 });

  // 3. Read CAR bytes
  process.stderr.write(`[synapse-node] Reading CAR file: ${carBuildResult.carPath}\n`);
  const carBytes = await readFile(carBuildResult.carPath);
  process.stderr.write(`[synapse-node] CAR size: ${carBytes.length} bytes\n`);

  notifyProgress?.({ bytesUploaded: 0, totalBytes: carBytes.length, percentage: 25 });

  // 4. Check upload readiness (payment validation) — 10 minute timeout
  process.stderr.write(`[synapse-node] Checking upload readiness...\n`);
  const readiness = await withTimeout(
    'checkUploadReadiness',
    checkUploadReadiness({
      synapse,
      fileSize: carBytes.length,
      autoConfigureAllowances: true,
    }),
    600000
  );

  process.stderr.write(`[synapse-node] Readiness status: ${readiness.status}\n`);

  if (readiness.status === 'blocked') {
    const errorMessage =
      readiness.validation?.errorMessage ||
      (readiness.suggestions && readiness.suggestions.length > 0
        ? readiness.suggestions.join('. ')
        : 'Upload blocked: Payment setup incomplete');
    throw new Error(errorMessage);
  }

  notifyProgress?.({ bytesUploaded: 0, totalBytes: carBytes.length, percentage: 30 });

  // 5. Create storage context — logger as 2nd arg directly (not wrapped in options)
  process.stderr.write(`[synapse-node] Creating storage context...\n`);
  const { storage, providerInfo } = await withTimeout(
    'createStorageContext',
    createStorageContext(synapse, logger),
    60000
  );

  process.stderr.write(`[synapse-node] Storage context created, provider: ${providerInfo?.address ?? 'unknown'}\n`);

  const synapseService = { synapse, storage, providerInfo };

  notifyProgress?.({ bytesUploaded: 0, totalBytes: carBytes.length, percentage: 35 });

  // 6. Execute upload with retry logic — same as _executeUploadWithTimeout
  const rootCidString = carBuildResult.rootCid.toString();
  const contextId = filePath.split(/[\\/]/).pop() || 'upload';
  const maxRetries = 3;
  const uploadTimeoutMs = 1800000; // 30 minutes per attempt
  let lastError = null;

  let uploadResult = null;
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      process.stderr.write(`[synapse-node] Upload attempt ${attempt}/${maxRetries}...\n`);

      const uploadPromise = executeUpload(synapseService, carBytes, rootCidString, {
        logger,
        contextId,
        onProgress: (event) => {
          if (event.type === 'onUploadComplete') {
            notifyProgress?.({ bytesUploaded: carBytes.length, totalBytes: carBytes.length, percentage: 80 });
          } else if (event.type === 'onPieceAdded') {
            notifyProgress?.({ bytesUploaded: carBytes.length, totalBytes: carBytes.length, percentage: 90 });
          } else if (event.type === 'onPieceConfirmed') {
            notifyProgress?.({ bytesUploaded: carBytes.length, totalBytes: carBytes.length, percentage: 95 });
          }
        },
        ipniValidation: { enabled: true },
      });

      uploadResult = await withTimeout(`Upload attempt ${attempt}`, uploadPromise, uploadTimeoutMs);
      process.stderr.write(`[synapse-node] Upload succeeded on attempt ${attempt}\n`);
      break;

    } catch (error) {
      const errorMessage = error.message ?? String(error);
      lastError = error;

      // Check for insufficient balance — do not retry
      const isBalanceError =
        errorMessage.includes('insufficient') ||
        errorMessage.includes('balance') ||
        errorMessage.includes('allowance') ||
        errorMessage.includes('funds');

      if (isBalanceError) {
        process.stderr.write(`[synapse-node] Upload failed with balance error: ${errorMessage}\n`);
        throw error;
      }

      // Check for timeout — retry
      const isTimeoutError =
        errorMessage.includes('timeout') ||
        errorMessage.includes('TIMEOUT') ||
        errorMessage.includes('StorageContext addPieces failed');

      if (isTimeoutError && attempt < maxRetries) {
        const delayMs = attempt * 5000;
        process.stderr.write(`[synapse-node] Upload attempt ${attempt} timed out, retrying in ${delayMs}ms...\n`);
        await new Promise(resolve => setTimeout(resolve, delayMs));
        continue;
      }

      // Non-retryable error
      process.stderr.write(`[synapse-node] Upload failed (non-retryable): ${errorMessage}\n`);
      throw error;
    }
  }

  if (!uploadResult) {
    throw new Error(
      `Upload failed after ${maxRetries} attempts. Last error: ${lastError?.message}`
    );
  }

  // 7. Cleanup CAR file
  try {
    await unixfsCarBuilder.cleanup(carBuildResult.carPath, logger);
  } catch {
    // Ignore cleanup errors
  }

  notifyProgress?.({ bytesUploaded: carBytes.length, totalBytes: carBytes.length, percentage: 100 });

  process.stderr.write(`[synapse-node] Upload complete. CID: ${rootCidString}\n`);

  return {
    cid: rootCidString,
    size: carBytes.length,
    uploadedAt: new Date().toISOString(),
    dealId: uploadResult.pieceId?.toString() ?? '',
    txHash: uploadResult.transactionHash ?? '',
  };
}

async function handleSynapseGetStatus(params) {
  const cid = params.cid ?? '';
  return {
    cid,
    status: 'active',
    deals: [{ dealId: `deal_${cid.slice(-12)}`, provider: 'f01234', status: 'active' }],
  };
}

async function handleSynapseDisconnect() {
  if (_isConnected) {
    try {
      const { cleanupSynapseService } = await import('filecoin-pin/core/synapse');
      await cleanupSynapseService();
    } catch (e) {
      process.stderr.write(`[synapse-node] Cleanup error: ${e.message}\n`);
    }
  }
  _isConnected = false;
  return { disconnected: true };
}

// ── JSON-RPC server ───────────────────────────────────────────────────────────

function sendResponse(id, result) {
  process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id, result }) + '\n');
}

function sendError(id, code, message) {
  process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id, error: { code, message } }) + '\n');
}

function sendNotification(method, params) {
  process.stdout.write(JSON.stringify({ jsonrpc: '2.0', method, params }) + '\n');
}

async function handleRequest(line) {
  let req;
  try { req = JSON.parse(line); } catch { return; }

  const { id, method, params } = req;

  if (method === 'shutdown' && id === undefined) {
    process.stderr.write('[synapse-node] Shutdown requested\n');
    process.exit(0);
  }

  try {
    let result;
    switch (method) {
      case 'ping':
        result = await handlePing(); break;
      case 'getStatus':
        result = await handleGetStatus(); break;
      case 'synapse.connect':
        result = await handleSynapseConnect(params ?? {}); break;
      case 'synapse.upload': {
        const notifyProgress = (p) => sendNotification('synapse.uploadProgress', p);
        result = await handleSynapseUpload(params ?? {}, notifyProgress);
        break;
      }
      case 'synapse.getStatus':
        result = await handleSynapseGetStatus(params ?? {}); break;
      case 'synapse.disconnect':
        result = await handleSynapseDisconnect(); break;
      default:
        sendError(id, -32601, `Method not found: ${method}`);
        return;
    }
    sendResponse(id, result);
  } catch (err) {
    process.stderr.write(`[synapse-node] Error in ${method}: ${err.message}\n${err.stack ?? ''}\n`);
    sendError(id, -32000, err.message);
  }
}

// ── Startup ───────────────────────────────────────────────────────────────────

process.stderr.write('[synapse-node] Starting Synapse Node.js bridge\n');
sendResponse('ready', { ready: true });

const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
rl.on('line', (line) => {
  const trimmed = line.trim();
  if (trimmed) {
    handleRequest(trimmed).catch((e) =>
      process.stderr.write(`[synapse-node] Unhandled: ${e.message}\n${e.stack ?? ''}\n`)
    );
  }
});
rl.on('close', () => {
  process.stderr.write('[synapse-node] stdin closed, exiting\n');
  process.exit(0);
});
