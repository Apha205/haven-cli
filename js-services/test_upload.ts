import { createSynapseWrapper } from './synapse-wrapper.ts';

const wrapper = createSynapseWrapper();

// Create a small test file
const testFile = '/tmp/test_upload_' + Date.now() + '.bin';
const testData = new Uint8Array(1024 * 10); // 10KB
crypto.getRandomValues(testData);
await Deno.writeFile(testFile, testData);

console.error('Testing Synapse upload with file:', testFile);

try {
  // Connect
  const result = await wrapper.connect({
    rpcUrl: 'https://api.calibration.node.glif.io/rpc/v1',
    networkMode: 'testnet',
    debug: true
  });
  console.error('Connected:', result);
  
  // Upload with progress
  const uploadResult = await wrapper.upload({
    filePath: testFile,
    onProgress: true
  }, (progress) => {
    console.error('Progress:', JSON.stringify(progress));
  });
  
  console.error('Upload result:', JSON.stringify(uploadResult, null, 2));
  
  await wrapper.disconnect();
  console.error('Done!');
  
  // Cleanup
  await Deno.remove(testFile);
} catch (e) {
  console.error('ERROR:', e.message);
  if (e.stack) console.error('Stack:', e.stack);
  try { await Deno.remove(testFile); } catch {}
}
