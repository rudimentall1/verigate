# SESSION CHECKPOINT — Verigate / Circle Questbook / Arc Mainnet

Date: 2026-11-07

## CURRENT OBJECTIVE

Prepare the Verigate project for the Circle Questbook grant application:
https://circle.questbook.app/proposal_form/?grantId=6992785dfb7e884efacadb1e&chainId=10

The scope is EXCLUSIVELY Verigate + Arc Mainnet.
Agentic Wallet Guardian V3 is NOT part of this task. Do not continue its integration or deployment work for this grant.

## FOUR QUESTIONS THAT MUST BE ANSWERED WITH VERIFIED EVIDENCE

1. Is your project currently live in production?
2. Are you live on Arc?
3. Have you deployed any smart contracts?
4. Please enter your Arc mainnet smart contract addresses.

## REQUIRED WORK

1. Work only in the Verigate repository: /opt/verigate
2. Inspect the existing Arc integration, RPC configuration, chain ID 5042, USDC integration, API endpoints and authorization flow.
3. Establish whether Verigate has its own deployed Arc Mainnet smart contracts.
4. Locate existing deployment artifacts, deployment transaction hashes and contract addresses.
5. Independently verify every claimed address and transaction on the Arc Mainnet explorer.
6. If Verigate has no required contract, determine whether one is actually needed, implement it and deploy only after review and explicit authorization.
7. Prepare accurate, evidence-backed answers for all four Circle application fields.

## IMPORTANT DISTINCTIONS

- Connecting to Arc RPC does not prove that Verigate is live on Arc.
- Using Circle USDC does not mean Verigate deployed its own smart contract.
- Never enter the USDC token address as a Verigate contract address.
- Never invent deployment addresses or claim production status without evidence.
- Clearly distinguish production deployment, test deployment, integration support and actual on-chain activity.

## CURRENT SERVER STATE

- Production Verigate: /opt/verigate, existing service on 127.0.0.1:8004. Do not disrupt it.
- Separate test Verigate process: /opt/verigate-arc-test, port 8005. Its process was observed running as PID 3953000. Do not assume it represents production or the final Arc deployment.
- Verigate bootstrap PR worktree: /opt/verigate-arc-bootstrap-test. Not relevant to the Circle task unless its code is independently shown to be needed.
- Guardian integration worktree: /opt/hackathons/agentic-wallet-guardian-v3-verigate-test. Out of scope.
- Guardian port 8766 was not listening. Do not spend further time launching Guardian for this task.
- Existing production Verigate must remain untouched unless a specific, reviewed change is necessary.

## NEXT ACTION

Resume by examining ONLY /opt/verigate and its existing Arc-related deployment evidence. Determine the actual Arc Mainnet deployment state and produce a concise evidence table:
- claim
- evidence source
- verified result
- what can safely be entered in Circle's form

Do not begin another broad diagnostic cycle. Do not ask the user to repeat facts already recorded. Prefer direct implementation and evidence collection over repeated status checks.

---
