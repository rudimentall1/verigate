# Arc signer Unix-socket access model

The signer exposes no TCP listener. The issuer and agent roles each have a separate Unix-domain socket:

- `/run/verigate-signer-issuer/signer.sock`
- `/run/verigate-signer-agent/signer.sock`

The systemd template runs each role as its own user and primary group (`verigate-signer-issuer` or `verigate-signer-agent`). systemd creates the matching runtime directory with mode `0750`. The daemon sets its socket to mode `0660`. The resulting owner/group boundary is the signer account and its private group.

## Agent client access

The Verigate agent runtime must not own or read the agent signer's private key. It receives socket access through supplementary membership in the `verigate-signer-agent` group only. After the actual application account is identified during read-only host inventory, an operator may grant that one account membership:

```sh
sudo usermod --append --groups verigate-signer-agent ACTUAL_AGENT_RUNTIME_USER
id ACTUAL_AGENT_RUNTIME_USER
namei -l /run/verigate-signer-agent/signer.sock
stat -c '%U:%G:%a %n' /run/verigate-signer-agent/signer.sock
```

Replace the placeholder with the verified service account. Do not guess the account name. Restart only the client application after changing supplementary groups so that its process receives the updated group list; the signer service does not need a restart just for the client's supplementary group change.

Verify that the intended client can connect and an unrelated unprivileged account cannot. The deployment smoke test performs this positive and negative Unix-socket permission check using disposable users.

## Issuer isolation

Do not add the autonomous agent runtime, model worker, or agent signer account to `verigate-signer-issuer`. Access to the issuer socket must remain with a separately identified operator-controlled issuer client. If that client runs under another service account, grant only that exact account supplementary membership in `verigate-signer-issuer`, after reviewing the process and trust boundary.

Never make either socket world-accessible (`0666`), never expose an equivalent TCP endpoint, and never share signer private-key files with the client process. Socket access authorizes only the typed role operations enforced by the signer; it does not reveal the private key.

## Acceptance checks before enabling either unit

1. Confirm the signer user/group, runtime directory owner/group and socket owner/group/mode.
2. Confirm the exact agent client user is a member of the agent signer group and is not a member of the issuer signer group.
3. Confirm the issuer client principal is operator-controlled and is not the autonomous agent runtime.
4. Test access as each real service account, then verify unrelated accounts are denied.
5. Record the verified user/group mapping in the deployment checkpoint. Do not start the production signer until these checks are complete.
