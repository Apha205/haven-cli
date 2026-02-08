/**
 * Access control condition helpers for Lit Protocol.
 */

import { ethers } from 'ethers';
import type {
  EvmBasicAccessControlCondition,
  UnifiedAccessControlCondition,
  ChainName,
} from './types.ts';

/**
 * Normalize a private key to include 0x prefix.
 */
export function normalizePrivateKey(privateKey: string): string {
  const trimmed = privateKey.trim();
  if (trimmed.startsWith('0x') || trimmed.startsWith('0X')) {
    return trimmed;
  }
  return `0x${trimmed}`;
}

/**
 * Get wallet address from a private key.
 */
export function getWalletAddressFromPrivateKey(privateKey: string): string {
  const normalizedKey = normalizePrivateKey(privateKey);
  const wallet = new ethers.Wallet(normalizedKey);
  return wallet.address;
}

/**
 * Create access control conditions that only allow the owner to decrypt.
 */
export function createOwnerOnlyAccessControlConditions(
  walletAddress: string,
  chain: ChainName = 'ethereum'
): EvmBasicAccessControlCondition[] {
  return [
    {
      contractAddress: '',
      standardContractType: '',
      chain,
      method: '',
      parameters: [':userAddress'],
      returnValueTest: {
        comparator: '=',
        value: walletAddress.toLowerCase(),
      },
    },
  ];
}

/**
 * Convert EVM basic access control conditions to unified format.
 */
export function toUnifiedAccessControlConditions(
  conditions: EvmBasicAccessControlCondition[]
): UnifiedAccessControlCondition[] {
  return conditions.map((condition) => ({
    conditionType: 'evmBasic' as const,
    ...condition,
  }));
}
