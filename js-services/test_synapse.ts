import { createSynapseWrapper } from './synapse-wrapper.ts';

const wrapper = createSynapseWrapper();

console.error('Testing Synapse connection...');

try {
  const result = await wrapper.connect({
    rpcUrl: 'https://api.calibration.node.glif.io/rpc/v1',
    networkMode: 'testnet',
    debug: true
  });
  console.error('Connect result:', JSON.stringify(result, null, 2));
  
  // Try a simple operation
  console.error('Testing file size validation...');
  const validation = wrapper.validateFileSize(1024 * 1024, false);
  console.error('Validation result:', JSON.stringify(validation, null, 2));
  
  await wrapper.disconnect();
  console.error('Done!');
} catch (e) {
  console.error('ERROR:', e.message);
  console.error('Stack:', e.stack);
}
