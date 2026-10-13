import { AnnaAppRuntime } from "/static/anna-apps/_sdk/latest/index.js";

const EXECUTA_HANDLE = "verigate-authority";
const DEV_FALLBACK_TOOL_ID = "tool-dev-verigate-authority";
const TOOL_ID =
  (typeof window !== "undefined" && window.__ANNA_TOOL_IDS__?.[EXECUTA_HANDLE]) ||
  DEV_FALLBACK_TOOL_ID;

const $ = (id) => document.getElementById(id);
const state = { anna: null, lastReceipt: null, busy: false, lastInterpretedDescription: "", requestId: 0 };
const buttons = [$("interpret-btn"), $("check-btn")];
const inputs = ["action-description", "agent-id", "target", "asset", "network", "amount", "resource"].map($);

function setBusy(busy, message) {
  state.busy = busy;
  buttons.forEach((button) => { button.disabled = busy; });
  inputs.forEach((input) => { input.disabled = busy; });
  $("status").textContent = message || (busy ? "Working…" : "Ready.");
}

function showError(message) {
  const box = $("error");
  box.textContent = message;
  box.style.display = "block";
}

function clearError() {
  $("error").textContent = "";
  $("error").style.display = "none";
}

function clearResult() {
  state.lastReceipt = null;
  $("result").style.display = "none";
  $("decision").textContent = "";
  $("decision").className = "decision";
  $("result-title").textContent = "";
  $("result-meta").textContent = "";
  $("result-summary").textContent = "";
  $("rules").replaceChildren();
  $("proof").textContent = "";
  $("receipt-json").textContent = "";
}

function getTextFromCompletion(reply) {
  const candidate =
    reply?.content ??
    reply?.message?.content ??
    reply?.result?.content ??
    reply?.text ??
    reply?.result?.text;

  if (typeof candidate === "string") return candidate.trim();
  if (Array.isArray(candidate)) {
    return candidate
      .map((part) => typeof part === "string" ? part : (typeof part?.text === "string" ? part.text : ""))
      .filter(Boolean)
      .join("\n")
      .trim();
  }
  if (candidate && typeof candidate.text === "string") return candidate.text.trim();
  throw new Error("Anna AI returned an unexpected response format. Please retry.");
}

async function askAnna(systemPrompt, userPrompt, maxTokens = 320) {
  if (!state.anna?.llm?.complete) {
    throw new Error("Anna's LLM is not available in this session. Open Verigate from the Anna app runtime and try again.");
  }
  const reply = await state.anna.llm.complete({
    systemPrompt,
    messages: [{ role: "user", content: { type: "text", text: userPrompt } }],
    maxTokens,
    temperature: 0.1
  });
  return getTextFromCompletion(reply);
}

function parseJsonFromModel(raw) {
  const cleaned = raw
    .trim()
    .replace(/^\x60{3}(?:json)?\s*/i, "")
    .replace(/\s*\x60{3}$/i, "");
  const start = cleaned.indexOf("{");
  const end = cleaned.lastIndexOf("}");
  if (start < 0 || end <= start) throw new Error("Anna AI could not structure this action. Add the recipient, asset, network and amount, then retry.");
  try {
    return JSON.parse(cleaned.slice(start, end + 1));
  } catch {
    throw new Error("Anna AI returned invalid structured data. Edit the description to be more specific and try again.");
  }
}

function fieldValue(id) {
  return ($(id).value || "").trim();
}

function setIfProvided(id, value) {
  if (value === null || value === undefined || value === "") return;
  if (id === "amount") {
    const n = Number(value);
    if (Number.isFinite(n) && n > 0) $(id).value = String(n);
    return;
  }
  $(id).value = String(value).trim();
}

function collectInputs() {
  const rawAmount = fieldValue("amount");
  const amount = Number(rawAmount);
  const values = {
    actionDescription: fieldValue("action-description"),
    agent_id: fieldValue("agent-id"),
    payee: fieldValue("target"),
    asset: fieldValue("asset"),
    network: fieldValue("network"),
    amount,
    resource: fieldValue("resource")
  };
  if (!values.actionDescription) throw new Error("Describe the action you want to check first.");
  if (!values.agent_id) throw new Error("Enter an agent identifier.");
  if (!values.payee) throw new Error("Enter the recipient or payee. Use “Interpret with Anna AI” to extract it from your description.");
  if (!values.asset) throw new Error("Enter the asset, for example USDC.");
  if (!values.network) throw new Error("Enter the network, for example Base.");
  if (!rawAmount || !Number.isFinite(amount) || amount <= 0) throw new Error("Enter a valid amount greater than zero.");
  return values;
}

function prettyRule(rule) {
  if (typeof rule === "string") return rule;
  const id = rule?.rule || rule?.rule_id || rule?.id || rule?.code || "";
  const message = rule?.message || rule?.reason || rule?.description || "";
  if (id && message) return id + ": " + message;
  return message || id || JSON.stringify(rule);
}

async function interpretAction(options = {}) {
  const keepBusy = options.keepBusy === true;
  if (state.busy && !keepBusy) return;
  clearError();
  $("interpretation").textContent = "";
  const description = fieldValue("action-description");
  if (!description) {
    showError("Describe the action first. Example: Pay 25 USDC on Base to 0xMerchantABC for invoice 1042.");
    return;
  }

  if (description !== state.lastInterpretedDescription && state.lastInterpretedDescription) {
    ["target", "asset", "network", "amount", "resource"].forEach((id) => { $(id).value = ""; });
  }
  if (!keepBusy) setBusy(true, "Anna AI is extracting the payment details…");
  try {
    const known = {
      agent_id: fieldValue("agent-id"),
      payee: fieldValue("target") || null,
      asset: fieldValue("asset") || null,
      network: fieldValue("network") || null,
      amount: fieldValue("amount") ? Number(fieldValue("amount")) : null,
      resource: fieldValue("resource") || null
    };
    const raw = await askAnna(
      "You extract structured fields for a payment-authority check. You do not make authorization decisions. Return only one valid JSON object with exactly these keys: payee, asset, network, amount, resource, summary, missing_fields. Use null for values not explicitly stated or safely inferable from the user message. Never invent an amount, token, network, or recipient. amount must be a positive number or null. Keep summary to one short sentence. missing_fields must be an array containing names from payee, asset, network, amount when unknown.",
      "Extract the action into this schema. Existing form values are authoritative when provided; keep them unless the user description clearly corrects them.\nExisting values: " + JSON.stringify(known) + "\nUser's action: " + description + "\nReturn JSON only."
    );
    const parsed = parseJsonFromModel(raw);
    setIfProvided("target", parsed.payee);
    setIfProvided("asset", parsed.asset);
    setIfProvided("network", parsed.network);
    setIfProvided("amount", parsed.amount);
    setIfProvided("resource", parsed.resource);
    const missing = ["target", "asset", "network", "amount"].filter((id) => !fieldValue(id));
    const summary = typeof parsed.summary === "string" ? parsed.summary : "The AI extracted fields from your description.";
    $("interpretation").textContent = "Anna AI interpretation: " + summary +
      (missing.length ? " Still needed: " + missing.map((id) => ({target:"recipient", asset:"asset", network:"network", amount:"amount"})[id]).join(", ") + "." : " Review the fields above, then check authority.");
    state.lastInterpretedDescription = description;
    if (!keepBusy) setBusy(false, "Interpretation complete. Review the fields before checking.");
  } catch (error) {
    showError(error?.message || String(error));
    if (!keepBusy) setBusy(false, "Interpretation failed.");
  }
}

function renderRules(matchedRules) {
  const list = $("rules");
  list.replaceChildren();
  const rules = Array.isArray(matchedRules) ? matchedRules : [];
  if (!rules.length) {
    const li = document.createElement("li");
    li.textContent = "No configured policy rule was violated by this request.";
    list.appendChild(li);
    return;
  }
  for (const rule of rules) {
    const li = document.createElement("li");
    li.textContent = prettyRule(rule);
    list.appendChild(li);
  }
}

function extractDecisionEnvelope(toolResponse) {
  const outer = toolResponse?.result ?? toolResponse;
  if (outer?.error) {
    throw new Error(outer.error.message || outer.error || "Verigate check failed.");
  }
  if (outer?.success === false) throw new Error(outer.error || "Verigate could not check this action.");
  const data = outer?.data ?? outer;
  const receipt = data?.decision_receipt ?? data?.receipt ?? null;
  if (!receipt?.payload) throw new Error("Verigate returned no signed decision receipt. Please retry; do not treat this as an approval.");
  const decisionData = receipt.payload.decision || {};
  const decision = String(decisionData.decision || "").toUpperCase();
  if (!["ALLOW", "WARN", "BLOCK"].includes(decision)) throw new Error("Verigate returned an unrecognized decision. No approval should be inferred.");
  return {
    receipt,
    decision,
    decisionData,
    intent: receipt.payload.intent || {},
    matchedRules: decisionData.matched_rules || decisionData.rules || []
  };
}

function baseExplanation(decision, rules) {
  const text = (rules || []).map(prettyRule).filter(Boolean);
  if (decision === "ALLOW") return text.length
    ? "Verigate found no blocking rule and allowed this request under the configured policy."
    : "No configured policy rule was violated. ALLOW is a policy result, not a guarantee that the payment is safe or will succeed.";
  if (decision === "WARN") return "Verigate found a condition that needs human review. Do not proceed until the warning has been checked." + (text.length ? " " + text.join(" ") : "");
  return "Verigate blocked this request under the configured policy. Do not proceed with the action as described." + (text.length ? " " + text.join(" ") : "");
}

async function explainDecision(envelope, values) {
  const details = {
    decision: envelope.decision,
    agent_id: values.agent_id,
    payee: values.payee,
    asset: values.asset,
    network: values.network,
    amount: values.amount,
    resource: values.resource || null,
    matched_rules: envelope.matchedRules
  };
  try {
    return await askAnna(
      "You explain an existing Verigate policy decision to a non-technical user. The decision and matched rules are authoritative and final. Never change ALLOW, WARN, or BLOCK. Never say a payment was executed. Use only the supplied matched-rule messages; do not invent rules or safety claims. For ALLOW with no matched rules, say only that no configured rule was violated, not that the payment is safe. Explain in 1-3 short sentences.",
      "Explain this Verigate decision in plain English. Do not output JSON.\n" + JSON.stringify(details),
      220
    );
  } catch {
    return baseExplanation(envelope.decision, envelope.matchedRules);
  }
}

async function checkAuthority() {
  if (state.busy) return;
  const requestId = ++state.requestId;
  setBusy(true, "Preparing authority check…");
  clearError();
  clearResult();

  // The primary action also handles a plain-language-only request. Do not
  // make users discover a separate AI button before they can check authority.
  const requiredFields = ["target", "asset", "network", "amount"];
  const actionDescription = fieldValue("action-description");
  const descriptionChanged = actionDescription && actionDescription !== state.lastInterpretedDescription;
  const needsInterpretation = actionDescription &&
    (descriptionChanged || requiredFields.some((id) => !fieldValue(id)));
  if (needsInterpretation) {
    await interpretAction({ keepBusy: true });
    if (requestId !== state.requestId) return;
    if ($("error").style.display !== "none") {
      setBusy(false, "Check failed. Correct the request and retry.");
      return;
    }
  }

  let values;
  try {
    values = collectInputs();
  } catch (error) {
    showError(error.message);
    setBusy(false, "Check failed. Correct the request and retry.");
    return;
  }
  if (!state.anna) {
    showError("Verigate is not connected to Anna's app runtime. Open it from Anna and retry.");
    setBusy(false, "Check failed. Open the app from Anna and retry.");
    return;
  }

  setBusy(true, "Verigate is evaluating the action against its policy…");
  $("interpretation").textContent = "";
  try {
    const toolResponse = await state.anna.tools.invoke({
      tool_id: TOOL_ID,
      method: "verigate_check",
      args: {
        agent_id: values.agent_id,
        payee: values.payee,
        asset: values.asset.toUpperCase(),
        network: values.network.toLowerCase(),
        amount: values.amount,
        resource: values.resource
      }
    });
    if (requestId !== state.requestId) return;
    const envelope = extractDecisionEnvelope(toolResponse);
    state.lastReceipt = envelope.receipt;

    const pill = $("decision");
    pill.textContent = envelope.decision;
    pill.className = "decision " + envelope.decision.toLowerCase();
    $("result-title").textContent = {
      ALLOW: "Allowed by policy",
      WARN: "Human review required",
      BLOCK: "Blocked by policy"
    }[envelope.decision];
    $("result-meta").textContent = values.agent_id + " · " + values.amount + " " + values.asset.toUpperCase() + " · " + values.network;
    $("result-summary").textContent = "Anna AI is explaining Verigate's signed decision…";
    renderRules(envelope.matchedRules);
    const signaturePresent = Boolean(envelope.receipt.signature);
    $("proof").textContent = signaturePresent
      ? "Signed Decision Receipt issued (" + (envelope.receipt.algorithm || "signature algorithm declared in receipt") + "). This records the policy decision; it does not mean a transaction was executed."
      : "A decision was returned, but the receipt signature is missing. Do not treat this response as independently verifiable.";
    $("receipt-json").textContent = JSON.stringify(envelope.receipt, null, 2);
    $("result").style.display = "block";

    const explanation = await explainDecision(envelope, values);
    if (requestId !== state.requestId) return;
    $("result-summary").textContent = explanation || baseExplanation(envelope.decision, envelope.matchedRules);
    setBusy(false, "Check complete. No transaction was executed.");
  } catch (error) {
    if (requestId !== state.requestId) return;
    clearResult();
    showError(error?.message || String(error));
    setBusy(false, "Check failed.");
  }
}

async function main() {
  try {
    state.anna = await AnnaAppRuntime.connect();
    await state.anna.window.set_title({ title: "Verigate Authority" });
    if (state.anna.window.ready) await state.anna.window.ready();
    setBusy(false, "Connected to Anna. Describe an action to get started.");
  } catch {
    setBusy(false, "Standalone preview. Open inside Anna to use its LLM and Verigate tool.");
    buttons.forEach((button) => { button.disabled = true; });
  }
  $("interpret-btn").addEventListener("click", interpretAction);
  $("check-btn").addEventListener("click", checkAuthority);
  const invalidateResult = () => {
    state.requestId += 1;
    clearResult();
    clearError();
  };
  inputs.forEach((input) => {
    input.addEventListener("input", invalidateResult);
    input.addEventListener("change", invalidateResult);
  });
}

main();
