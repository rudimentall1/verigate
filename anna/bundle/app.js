import { AnnaAppRuntime } from "/static/anna-apps/_sdk/latest/index.js";

const EXECUTA_HANDLE = "verigate-authority";
const DEV_FALLBACK_TOOL_ID = "tool-dev-verigate-authority";
const TOOL_ID = window.__ANNA_TOOL_IDS__?.[EXECUTA_HANDLE] || DEV_FALLBACK_TOOL_ID;

async function main() {
  const status = document.getElementById("status");
  const btn = document.getElementById("primary-btn");
  if (!status || !btn) return;

  let anna;
  try {
    anna = await AnnaAppRuntime.connect();
  } catch (e) {
    status.textContent = "Standalone preview (no Anna host).";
    return;
  }

  await anna.window.set_title({ title: "Verigate Authority" });
  if (anna.window.ready) await anna.window.ready();
  status.textContent = "Ready.";

  btn.addEventListener("click", async () => {
    btn.disabled = true;
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
          amount: 10.5
        }
      });
      await anna.storage.set({ key: "verigate-authority:last", value: Date.now() });
      status.textContent = JSON.stringify(out, null, 2);
    } catch (e) {
      status.textContent = "Error: " + (e?.message || String(e));
    } finally {
      btn.disabled = false;
    }
  });
}

main();
