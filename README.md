# Stokvel by Voice — Solana program + voice agent

A completed first-phase Anchor program for a **rotating savings stokvel** on Solana.

> **Development scope:** this release uses native SOL on Solana Localnet/Devnet. It is a learning and hackathon prototype, not audited financial software. Do not use real funds.

A voice-driven agent that drafts a rotating-savings group (stokvel), waits for explicit approval, runs attack tests, deploys it to Solana **devnet**, records a hash of the agreed rules on-chain, and returns a shareable summary, links and QR code.

## Status

| Phase | Scope | State |
|---|---|---|
| 1 | Anchor program + integration tests | Done |
| 2 | FastAPI backend, `GroupSpec`, state machine, approval gate, web app with voice | Done |
| 3 | Test / deploy / verify endpoints, UI buttons, share card, QR | Done |
| 4 | Supabase session persistence (falls back to memory) | Done |
| 5 | Attack tests (12-member simulation), semantic scenarios, summary check | Done |

Not done / known limits: SOL only (no USDC or rand), devnet only, no audit, no calendar dates or penalties on-chain, wallet onboarding for non-crypto users, the optional LLM judge has not been run against a live Groq key, and the Solana-side tests need a local toolchain (see below).

## Run the whole thing

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-agent.txt
cp .env.example .env            # all keys optional
python -m pytest -q             # Python + semantic scenarios (no network)
yarn install && RUN_ANCHOR=1 ./scripts/check.sh   # adds anchor test (needs Solana + Anchor 0.31.1)
uvicorn agent.main:app --reload --port 8000        # open http://localhost:8000
```

Real devnet flow: `solana config set --url devnet && solana airdrop 2 && ./scripts/prepare.sh && anchor build && anchor deploy --provider.cluster devnet`, then set `ANCHOR_PROVIDER_URL=https://api.devnet.solana.com` and `ANCHOR_WALLET=~/.config/solana/id.json` before starting uvicorn. Set `STOKVEL_TEST_MODE=1` to record tool calls instead of running them.

Optional persistence: run `db/schema.sql` in Supabase, then set `SUPABASE_URL` and `SUPABASE_KEY` (service-role key, server side only).

## API

| Endpoint | Purpose |
|---|---|
| `POST /chat` | Conversation; fills the `GroupSpec`, handles approval |
| `POST /sessions/{id}/test` | Runs the attack tests; refused unless approved |
| `POST /sessions/{id}/deploy` | Creates the group on devnet; refused unless approved **and** tests passed |
| `GET /sessions/{id}/verify` | Compares the spec's rules hash with the deployed one |
| `GET /sessions/{id}/share` | Plain-language summary, hash, explorer links |
| `GET /sessions/{id}/qr.svg?url=` | QR code for a link |

The deploy gate lives in code (`agent/tools.py`), not in the prompt.

## What the program does

1. A creator creates a group and becomes its first member.
2. Other wallets join before activation.
3. The creator activates the group, locking membership.
4. Each member contributes the configured amount once per round.
5. Once everyone has contributed, the next member in the fixed rotation receives the full pool.
6. The program resets contribution flags and advances the payout order.
7. After every member has received one payout, the group is marked complete.

The group creator receives the first payout. The next recipient is selected from on-chain state; the caller cannot choose a different recipient.

## Phase 1 features

- Group creation with unique `(creator, group_id)` PDA.
- Configurable contribution amount in lamports.
- Group size constrained to 2–20 members.
- Duplicate membership prevention.
- Creator-only activation.
- Membership locked after activation.
- One contribution per member per round.
- Payout blocked until all members contribute.
- Exact rotating payout recipient.
- Payout amount checked for arithmetic overflow.
- Rent-exempt balance preserved.
- No organizer withdrawal instruction.
- Group automatically completes after one payout per member.
- Anchor integration tests for core behavior and common attacks.

## Important product decisions and limitations

- **Currency:** contributions are native SOL, not South African rand. The amount is specified in lamports (1 SOL = 1,000,000,000 lamports). A later phase can support an SPL token such as a test stablecoin.
- **Schedule:** the program enforces rounds, not calendar dates. The agent/backend can later manage reminders and due dates.
- **Group size:** fixed maximum of 20 in this first version.
- **Payout model:** every member contributes the same amount each round; one member receives the full pool per round.
- **No cancellation/refunds:** there is intentionally no arbitrary withdrawal or emergency drain instruction. A cancellation/refund policy requires a separately designed and tested state machine.
- **No audit:** tests do not prove the program is secure. Get an independent audit before any mainnet or real-value use.

## Requirements

Install compatible versions of:

- Rust and Cargo
- Solana CLI 2.x
- Anchor CLI 0.31.1
- Node.js 20+
- Yarn classic (or compatible Yarn)

Check your tools:

```bash
rustc --version
cargo --version
solana --version
anchor --version
node --version
yarn --version
```

## Install dependencies

From the repository root:

```bash
yarn install
```

Ensure your local Solana wallet exists:

```bash
solana-keygen new
solana config set --url localhost
```

The local validator does not require API keys or paid services.

## Build and test

```bash
chmod +x scripts/prepare.sh
./scripts/prepare.sh
anchor build
anchor test
```

`anchor test` starts a local validator, builds the program, runs the TypeScript integration suite, and stops the validator.

If your Anchor installation does not automatically start a validator, run this in a separate terminal:

```bash
solana-test-validator
```

Then, in the project terminal:

```bash
anchor test
```

## Run on Devnet (optional)

This is only for deploying the prototype to Devnet. Devnet SOL has no real monetary value.

```bash
solana config set --url devnet
solana airdrop 2
./scripts/prepare.sh
anchor build
anchor deploy
```

The included program keypair is provided for reproducible local development only. Before publishing or deploying a public project, generate a program keypair that you control, replace `keys/stokvel-keypair.json`, and update the program ID in both `Anchor.toml` and `programs/stokvel/src/lib.rs`. Keep your wallet/upgrade authority private.

## Program instructions

| Instruction | Purpose |
|---|---|
| `create_group(group_id, contribution_lamports, max_members)` | Creates the group; creator joins automatically |
| `join_group()` | Adds a unique member before activation |
| `activate_group()` | Creator locks membership and starts the group |
| `contribute()` | Transfers one contribution for the current round |
| `payout()` | Releases the pool to the next scheduled member |

## Account model

`Group` stores:

- Creator and group ID
- Contribution amount in lamports
- Maximum and current member counts
- Fixed member array (20 slots)
- Per-round contribution flags
- Current payout index and cycle number
- Active/completed state
- PDA bump

PDA seeds:

```text
["group", creator_pubkey, group_id_le_bytes]
```

## Test coverage

The integration suite covers:

- Group creation and invalid parameters
- Unique member joining
- Duplicate member rejection
- Creator-only activation
- Membership lock after activation
- Non-member contribution rejection
- Duplicate contribution rejection
- Payout blocked before all contributions arrive
- Wrong payout recipient rejection
- Correct first payout and rotation advancement
- Completion after all members have received one payout

## Repository layout

```text
stokvel-agent-phase-1/
├── Anchor.toml
├── Cargo.toml
├── package.json
├── tsconfig.json
├── programs/
│   └── stokvel/
│       ├── Cargo.toml
│       └── src/lib.rs
├── agent/            FastAPI app, state machine, gate, store, summary check
├── web/              phone web app
├── db/schema.sql     Supabase table
├── tests/
│   ├── stokvel.ts, attacks.ts   Anchor tests
│   ├── unit/, integration/      Python tests
│   └── semantic/                markdown scenarios
├── scripts/
│   └── prepare.sh
├── keys/
│   └── stokvel-keypair.json
└── README.md
```

## Test coverage (attacks)

`tests/attacks.ts` adds: no withdraw/update instruction exists, the organiser cannot drain the vault, rules cannot be re-created, and a 12-member group runs 12 rounds with the vault reconciling and each member paid exactly once.
