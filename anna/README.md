# Verigate Authority (Anna App)

Give Verigate an agent action. Verigate decides whether the agent has the
authority to execute it. Execution produces evidence. Anyone can later verify
that evidence without trusting Verigate.

## Anna packaging

The App uses Anna's Bundled Executa model. The stable handle is
`verigate-authority`; Anna resolves it to the platform-assigned production
`tool_id` when publishing. Local development keeps `tool-dev-verigate-authority`.

The Executa is distributed as four platform binaries:

- `darwin-arm64`
- `darwin-x86_64`
- `linux-x86_64` — required for Anna Cloud Agent
- `windows-x86_64`

GitHub Actions builds and smoke-tests all four binaries and publishes them as
GitHub Release assets. Download the four archives into
`anna/executas/verigate-authority/dist/` before `anna-app apps publish`.

## Local development

```bash
cd anna
anna-app validate --strict
anna-app dev
```

## Production release

Run the GitHub Actions workflow **Build Anna Executa binaries** manually.
Then download all four release archives into:

```text
anna/executas/verigate-authority/dist/
```

Run:

```bash
cd anna
anna-app validate --strict
anna-app apps publish
```

Install the resulting version and test it on an Anna Cloud Agent before
submitting it for review.
