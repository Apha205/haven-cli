// Test the JSON-RPC bridge like Python does
import { createSynapseWrapper } from './synapse-wrapper.ts';

// Simulate JSON-RPC protocol
let requestId = 1;

function sendResponse(id: number | string, result: unknown) {
  console.log(JSON.stringify({ jsonrpc: "2.0", result, id }));
}

function sendError(id: number | string, code: number, message: string) {
  console.log(JSON.stringify({ jsonrpc: "2.0", error: { code, message }, id }));
}

// Signal ready
console.log(JSON.stringify({ jsonrpc: "2.0", method: "ready", params: { version: "test" } }));

// Read stdin for commands
const decoder = new TextDecoder();
const reader = Deno.stdin.readable.getReader();
let buffer = '';

let synapseWrapper: ReturnType<typeof createSynapseWrapper> | null = null;

while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  
  buffer += decoder.decode(value, { stream: true });
  
  let newlineIndex;
  while ((newlineIndex = buffer.indexOf('\n')) !== -1) {
    const line = buffer.slice(0, newlineIndex).trim();
    buffer = buffer.slice(newlineIndex + 1);
    
    if (!line) continue;
    
    try {
      const req = JSON.parse(line);
      console.error(`[bridge] Received: ${req.method}`);
      
      if (req.method === 'synapse.connect') {
        console.error('[bridge] Connecting to Synapse...');
        synapseWrapper = createSynapseWrapper();
        const result = await synapseWrapper.connect(req.params);
        console.error('[bridge] Connected!');
        sendResponse(req.id, result);
      } else if (req.method === 'synapse.upload') {
        if (!synapseWrapper?.isConnected) {
          sendError(req.id, -32000, 'Synapse not connected');
          continue;
        }
        console.error('[bridge] Starting upload...');
        const result = await synapseWrapper.upload(req.params, (progress) => {
          console.error('[bridge] Progress:', progress.percentage + '%');
        });
        console.error('[bridge] Upload complete!');
        sendResponse(req.id, result);
      } else if (req.method === 'shutdown') {
        if (synapseWrapper) await synapseWrapper.disconnect();
        sendResponse(req.id, { status: 'shutting_down' });
        Deno.exit(0);
      }
    } catch (e) {
      console.error('[bridge] Error:', e.message);
      sendError(requestId++, -32000, e.message);
    }
  }
}
