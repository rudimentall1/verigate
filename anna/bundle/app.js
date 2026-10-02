// Anna App bundle entry for verigate-authority. Calls the real Verigate
// GuardrailEngine through the bundled Executa (verigate_authority_plugin.py).
import { AnnaAppRuntime } from "/static/anna-apps/_sdk/latest/index.js";

const TOOL_ID = "tool-rinat-verigate-authority-2um8gwhw";

async function main() {
  const status = document.getElementById("status");
  const btn = document.getElementById("primary-btn");
  if (!status || !btn) return;

  let anna;
  try {
    anna = await AnnaAppRuntime.connect();
  } catch (e) {
    status.textContent = "Standalone preview (no host).";
    return;
  }

  await anna.window.set_title({ title: "Verigate Authority" });
  status.textContent = "Ready.";

  btn.addEventListener("click", async () => {
    status.textContent = "Asking Verigate for authority...";
    try {
      const out = await anna.tools.invoke({
        tool_id: TOOL_ID,
        method: "verigate_check",
        args: {
          agent_id: "anna-demo-agent",
          payee: "0xMerchantDemo",
          asset: "USDC",
          network: "base",
          amount: 10.5,
        },
      });
      await anna.storage.set({ key: "verigate-authority:last", value: Date.now() });
      status.textContent = JSON.stringify(out, null, 2);
    } catch (e) {
      status.textContent = "Error: " + e.message;
    }
  });
}

main();
