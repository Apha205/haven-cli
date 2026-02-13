/**
 * Lit Protocol client management for hybrid encryption.
 */

import { createLitClient } from '@lit-protocol/lit-client';
import { naga, nagaDev } from '@lit-protocol/networks';
import { createAuthManager } from '@lit-protocol/auth';
import { LitAccessControlConditionResource } from '@lit-protocol/auth-helpers';
import { createMemoryStorage } from '../lit-storage.ts';
import { createViemAccount } from '../viem-adapter.ts';
import { verifyPaymentSetup } from '../lit-payment.ts';
import { getWalletAddressFromPrivateKey, toUnifiedAccessControlConditions } from './access-control.ts';
import type { EvmBasicAccessControlCondition } from './types.ts';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type LitClient = any;

/** Network configurations mapping */
const NETWORK_CONFIGS: Record<string, typeof naga> = {
  'naga': naga,  // Mainnet - works
  'naga-dev': nagaDev,  
  'naga-staging': nagaDev,  // Staging
  'datil-dev': naga,  // Map to naga for compatibility
};

// Singleton state
let litClient: LitClient | null = null;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let authManager: any = null;
let initPromise: Promise<LitClient> | null = null;

/**
 * Initialize and get the Lit Protocol client.
 * Uses singleton pattern to maintain a single connection.
 */
export async function initLitClient(network: string = 'naga'): Promise<LitClient> {
  if (litClient && authManager) {
    return litClient;
  }

  if (initPromise) {
    return initPromise;
  }

  initPromise = (async (): Promise<LitClient> => {
    try {
      // Get network configuration (default to naga mainnet which works)
      const networkConfig = NETWORK_CONFIGS[network] || naga;
      
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      litClient = await (createLitClient as any)({
        network: networkConfig,
      });

      const appName = 'haven-player';
      const networkName = network;

      // Always use memory storage in Deno CLI environment
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      authManager = (createAuthManager as any)({
        storage: createMemoryStorage(appName, networkName),
      });

      console.error(`[Lit] Connected to Lit network (${network}) - SDK v8`);
      return litClient;
    } catch (error) {
      litClient = null;
      authManager = null;
      throw error;
    } finally {
      initPromise = null;
    }
  })();

  return initPromise;
}

/**
 * Disconnect from the Lit Protocol network.
 */
export async function disconnectLitClient(): Promise<void> {
  if (litClient) {
    try {
      await litClient.disconnect();
    } catch (error) {
      console.warn('[Lit] Error during disconnect:', error);
    }
    litClient = null;
    authManager = null;
    initPromise = null;
    console.error('[Lit] Disconnected from Lit network');
  }
}

/**
 * Get the current Lit client instance.
 */
export function getLitClient(): LitClient | null {
  return litClient;
}

/**
 * Get the current auth manager instance.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function getAuthManager(): any | null {
  return authManager;
}

/**
 * Check if the Lit client is connected.
 */
export function isLitClientConnected(): boolean {
  return litClient !== null && authManager !== null;
}

/**
 * Get authentication context for Lit Protocol operations.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function getAuthContext(privateKey: string, chain: string = 'ethereum'): Promise<any> {
  if (!litClient || !authManager) {
    throw new Error('Lit client not initialized. Call initLitClient() first.');
  }

  const viemAccount = createViemAccount(privateKey);

  const authContext = await authManager.createEoaAuthContext({
    authConfig: {
      domain: 'haven-player.local',
      statement: 'Sign this message to authenticate with Haven Player',
      resources: [
        {
          resource: new LitAccessControlConditionResource('*'),
          ability: 'access-control-condition-decryption',
        },
      ],
      expiration: new Date(Date.now() + 1000 * 60 * 60).toISOString(), // 1 hour
    },
    config: {
      account: viemAccount,
    },
    litClient,
  });

  return authContext;
}

/**
 * Encrypt data using Lit Protocol BLS-IBE.
 */
export async function encryptWithLit(
  data: Uint8Array,
  accessControlConditions: EvmBasicAccessControlCondition[],
  chain: string,
  network: string
): Promise<{ ciphertext: string; dataToEncryptHash: string }> {
  const client = await initLitClient(network);
  const unifiedAccessControlConditions = toUnifiedAccessControlConditions(accessControlConditions);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const litResult = await (client as any).encrypt({
    dataToEncrypt: data,
    unifiedAccessControlConditions,
    chain,
  });

  return {
    ciphertext: litResult.ciphertext,
    dataToEncryptHash: litResult.dataToEncryptHash,
  };
}

/**
 * Decrypt data using Lit Protocol.
 */
export async function decryptWithLit(
  ciphertext: string,
  dataToEncryptHash: string,
  accessControlConditions: EvmBasicAccessControlCondition[],
  privateKey: string,
  chain: string,
  network: string
): Promise<Uint8Array> {
  // Verify payment setup before attempting decryption (mainnet only)
  try {
    await verifyPaymentSetup(privateKey, network);
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.warn('[Lit Payment] Payment verification warning:', errorMessage);
    // Don't throw here - let the operation proceed and fail naturally if credits are required
  }

  const client = await initLitClient(network);
  const authContext = await getAuthContext(privateKey, chain);
  const unifiedAccessControlConditions = toUnifiedAccessControlConditions(accessControlConditions);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const keyResult = await (client as any).decrypt({
    data: {
      ciphertext,
      dataToEncryptHash,
    },
    unifiedAccessControlConditions,
    authContext,
    chain,
  });

  return keyResult.decryptedData as Uint8Array;
}

/**
 * Encrypt an AES key using Lit Protocol with owner-only access control.
 */
export async function encryptAesKeyWithLit(
  aesKey: Uint8Array,
  privateKey: string,
  chain: string,
  network: string
): Promise<{ ciphertext: string; dataToEncryptHash: string }> {
  const walletAddress = getWalletAddressFromPrivateKey(privateKey);
  const accessControlConditions = toUnifiedAccessControlConditions(
    [{ 
      contractAddress: '',
      standardContractType: '',
      chain: chain as any,
      method: '',
      parameters: [':userAddress'],
      returnValueTest: { comparator: '=', value: walletAddress.toLowerCase() }
    }]
  );

  const client = await initLitClient(network);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const litResult = await (client as any).encrypt({
    dataToEncrypt: aesKey,
    unifiedAccessControlConditions: accessControlConditions,
    chain,
  });

  return {
    ciphertext: litResult.ciphertext,
    dataToEncryptHash: litResult.dataToEncryptHash,
  };
}
