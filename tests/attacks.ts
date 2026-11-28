import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import { expect } from "chai";
const { Keypair, PublicKey, SystemProgram, Transaction, LAMPORTS_PER_SOL } = anchor.web3;
type Keypair = anchor.web3.Keypair;
type PublicKey = anchor.web3.PublicKey;
import { Stokvel } from "../target/types/stokvel";

// Deterministic attack tests. The program has no clock-based rules, so
// "time" here is rounds: a 12-member group is driven through all 12 rounds.
describe("stokvel attack tests", () => {
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);
  const program = anchor.workspace.Stokvel as Program<Stokvel>;
  const creator = (provider.wallet as anchor.Wallet).payer;
  const methods: any = program.methods; // generated types are very deep; keep tsc fast
  const conn = provider.connection;
  const contribution = new anchor.BN(LAMPORTS_PER_SOL / 100);
  const N = 12;

  const pdaFor = (id: anchor.BN) =>
    PublicKey.findProgramAddressSync(
      [Buffer.from("group"), creator.publicKey.toBuffer(), id.toArrayLike(Buffer, "le", 8)],
      program.programId
    )[0];

  const fails = async (p: Promise<unknown>) => {
    let failed = false;
    try { await p; } catch { failed = true; }
    expect(failed, "expected transaction to fail").to.equal(true);
  };

  const fund = async (kp: Keypair) => {
    const sig = await conn.requestAirdrop(kp.publicKey, 2 * LAMPORTS_PER_SOL);
    await conn.confirmTransaction(sig, "confirmed");
  };

  const contribute = (member: Keypair, group: PublicKey) =>
    methods.contribute()
      .accounts({ member: member.publicKey, group, systemProgram: SystemProgram.programId })
      .signers(member.publicKey.equals(creator.publicKey) ? [] : [member]).rpc();

  it("exposes no withdraw, update or cancel instruction", () => {
    const names = (program.idl as any).instructions.map((i: any) => i.name).sort();
    expect(names).to.deep.equal(["activateGroup", "contribute", "createGroup", "joinGroup", "payout"].sort());
  });

  it("the organiser cannot drain the vault with a direct transfer", async () => {
    const id = new anchor.BN(Date.now() + 1);
    const group = pdaFor(id);
    await methods.createGroup(id, contribution, 2)
      .accounts({ creator: creator.publicKey, group, systemProgram: SystemProgram.programId } as any).rpc();
    const before = await conn.getBalance(group);
    const ix = SystemProgram.transfer({ fromPubkey: group, toPubkey: creator.publicKey, lamports: 1000 });
    await fails(provider.sendAndConfirm(new Transaction().add(ix), [creator]));
    expect(await conn.getBalance(group)).to.equal(before);
  });

  it("rules cannot be changed by re-creating the group", async () => {
    const id = new anchor.BN(Date.now() + 2);
    const group = pdaFor(id);
    await methods.createGroup(id, contribution, 3)
      .accounts({ creator: creator.publicKey, group, systemProgram: SystemProgram.programId } as any).rpc();
    await fails(
      methods.createGroup(id, contribution.muln(100), 5)
        .accounts({ creator: creator.publicKey, group, systemProgram: SystemProgram.programId } as any).rpc()
    );
    const g = await program.account.group.fetch(group);
    expect(g.contributionLamports.toString()).to.equal(contribution.toString());
    expect(g.maxMembers).to.equal(3);
  });

  it("runs 12 members through 12 rounds: vault reconciles, everyone is paid exactly once", async () => {
    const id = new anchor.BN(Date.now() + 3);
    const group = pdaFor(id);
    const members = [creator, ...Array.from({ length: N - 1 }, () => Keypair.generate())];
    for (const m of members.slice(1)) await fund(m);

    await methods.createGroup(id, contribution, N)
      .accounts({ creator: creator.publicKey, group, systemProgram: SystemProgram.programId } as any).rpc();
    for (const m of members.slice(1)) {
      await methods.joinGroup().accounts({ member: m.publicKey, group } as any).signers([m]).rpc();
    }
    await methods.activateGroup().accounts({ creator: creator.publicKey, group } as any).rpc();

    const info = await conn.getAccountInfo(group);
    const rent = await conn.getMinimumBalanceForRentExemption(info!.data.length);
    const pool = contribution.muln(N).toNumber();
    const paid = new Set<string>();

    for (let round = 0; round < N; round++) {
      for (const m of members) await contribute(m, group);
      expect(await conn.getBalance(group)).to.equal(rent + pool);

      // Out-of-turn: any wallet other than the scheduled recipient is refused.
      const wrong = members[(round + 1) % N];
      await fails(methods.payout().accounts({ group, recipient: wrong.publicKey } as any).rpc());
      // Paid twice: the previous recipient cannot be paid again.
      if (round > 0) {
        await fails(methods.payout().accounts({ group, recipient: members[round - 1].publicKey } as any).rpc());
      }

      const recipient = members[round];
      const before = await conn.getBalance(recipient.publicKey);
      await methods.payout().accounts({ group, recipient: recipient.publicKey } as any).rpc();
      if (round > 0) { // creator also pays fees, so only check exact deltas for the others
        expect((await conn.getBalance(recipient.publicKey)) - before).to.equal(pool);
      }
      expect(await conn.getBalance(group)).to.equal(rent);
      expect(paid.has(recipient.publicKey.toBase58())).to.equal(false);
      paid.add(recipient.publicKey.toBase58());
    }

    const g = await program.account.group.fetch(group);
    expect(paid.size).to.equal(N);
    expect(g.completed).to.equal(true);
    expect(g.active).to.equal(false);
    expect(g.cycleNumber.toNumber()).to.equal(N);
  });
});
