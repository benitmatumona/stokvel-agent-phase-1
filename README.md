# Stokvel Agent — Phase 1: Solana Program

A completed first-phase Anchor program for a **rotating savings stokvel** on Solana.

> **Development scope:** this release uses native SOL on Solana Localnet/Devnet. It is a learning and hackathon prototype, not audited financial software. Do not use real funds.

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
├── tests/
│   └── stokvel.ts
├── scripts/
│   └── prepare.sh
├── keys/
│   └── stokvel-keypair.json
└── README.md
```

## Next phase

Phase 2 will add the FastAPI backend, `GroupSpec`, session state machine, approval gate, and text-based agent. It will call this program through an Anchor/Solana client; the smart contract remains the authority for financial rules.
