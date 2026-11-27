import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import { expect } from "chai";
import { Keypair, PublicKey, SystemProgram, LAMPORTS_PER_SOL } from "@solana/web3.js";
import { Stokvel } from "../target/types/stokvel";

describe("stokvel phase 1", () => {
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);
  const program = anchor.workspace.Stokvel as Program<Stokvel>;
  const creator = (provider.wallet as anchor.Wallet).payer;
  const memberA = Keypair.generate();
  const memberB = Keypair.generate();
  const outsider = Keypair.generate();
  const groupId = new anchor.BN(Date.now());
  const contribution = new anchor.BN(LAMPORTS_PER_SOL / 100); // 0.01 SOL
  let groupPda: PublicKey;

  const airdrop = async (wallet: Keypair) => {
    const sig = await provider.connection.requestAirdrop(wallet.publicKey, 2 * LAMPORTS_PER_SOL);
    await provider.connection.confirmTransaction(sig, "confirmed");
  };

  const expectFailure = async (promise: Promise<unknown>, message?: string) => {
    let failed = false;
    try {
      await promise;
    } catch (error: any) {
      failed = true;
      if (message) expect(String(error)).to.include(message);
    }
    expect(failed, "expected transaction to fail").to.equal(true);
  };

  before(async () => {
    await airdrop(memberA);
    await airdrop(memberB);
    await airdrop(outsider);
    [groupPda] = PublicKey.findProgramAddressSync(
      [Buffer.from("group"), creator.publicKey.toBuffer(), groupId.toArrayLike(Buffer, "le", 8)],
      program.programId
    );
  });

  it("creates a group with the creator as first member", async () => {
    await program.methods
      .createGroup(groupId, contribution, 3)
      .accounts({
        creator: creator.publicKey,
        group: groupPda,
        systemProgram: SystemProgram.programId,
      })
      .rpc();

    const group = await program.account.group.fetch(groupPda);
    expect(group.creator.equals(creator.publicKey)).to.equal(true);
    expect(group.memberCount).to.equal(1);
    expect(group.members[0].equals(creator.publicKey)).to.equal(true);
    expect(group.active).to.equal(false);
  });

  it("rejects zero contribution and invalid group sizes", async () => {
    const badId = groupId.addn(1);
    const [badPda] = PublicKey.findProgramAddressSync(
      [Buffer.from("group"), creator.publicKey.toBuffer(), badId.toArrayLike(Buffer, "le", 8)],
      program.programId
    );
    await expectFailure(
      program.methods.createGroup(badId, new anchor.BN(0), 3)
        .accounts({ creator: creator.publicKey, group: badPda, systemProgram: SystemProgram.programId }).rpc()
    );
    const badId2 = groupId.addn(2);
    const [badPda2] = PublicKey.findProgramAddressSync(
      [Buffer.from("group"), creator.publicKey.toBuffer(), badId2.toArrayLike(Buffer, "le", 8)],
      program.programId
    );
    await expectFailure(
      program.methods.createGroup(badId2, contribution, 1)
        .accounts({ creator: creator.publicKey, group: badPda2, systemProgram: SystemProgram.programId }).rpc()
    );
  });

  it("allows unique members to join and rejects duplicates", async () => {
    await program.methods.joinGroup().accounts({ member: memberA.publicKey, group: groupPda }).signers([memberA]).rpc();
    await expectFailure(
      program.methods.joinGroup().accounts({ member: memberA.publicKey, group: groupPda }).signers([memberA]).rpc()
    );
    await program.methods.joinGroup().accounts({ member: memberB.publicKey, group: groupPda }).signers([memberB]).rpc();
    const group = await program.account.group.fetch(groupPda);
    expect(group.memberCount).to.equal(3);
  });

  it("allows only the creator to activate the group", async () => {
    await expectFailure(
      program.methods.activateGroup().accounts({ creator: memberA.publicKey, group: groupPda }).signers([memberA]).rpc()
    );
    await program.methods.activateGroup().accounts({ creator: creator.publicKey, group: groupPda }).rpc();
    const group = await program.account.group.fetch(groupPda);
    expect(group.active).to.equal(true);
  });

  it("locks membership after activation", async () => {
    await expectFailure(
      program.methods.joinGroup().accounts({ member: outsider.publicKey, group: groupPda }).signers([outsider]).rpc()
    );
  });

  it("rejects non-members and duplicate contributions", async () => {
    await expectFailure(
      program.methods.contribute().accounts({
        member: outsider.publicKey, group: groupPda, systemProgram: SystemProgram.programId,
      }).signers([outsider]).rpc()
    );
    await program.methods.contribute().accounts({
      member: creator.publicKey, group: groupPda, systemProgram: SystemProgram.programId,
    }).rpc();
    await expectFailure(
      program.methods.contribute().accounts({
        member: creator.publicKey, group: groupPda, systemProgram: SystemProgram.programId,
      }).rpc()
    );
  });

  it("does not pay out before every member contributes", async () => {
    await expectFailure(
      program.methods.payout().accounts({ group: groupPda, recipient: creator.publicKey }).rpc()
    );
  });

  it("rejects a payout to the wrong wallet", async () => {
    await program.methods.contribute().accounts({
      member: memberA.publicKey, group: groupPda, systemProgram: SystemProgram.programId,
    }).signers([memberA]).rpc();
    await program.methods.contribute().accounts({
      member: memberB.publicKey, group: groupPda, systemProgram: SystemProgram.programId,
    }).signers([memberB]).rpc();
    await expectFailure(
      program.methods.payout().accounts({ group: groupPda, recipient: memberA.publicKey }).rpc()
    );
  });

  it("pays the correct first recipient and advances the rotation", async () => {
    const before = await provider.connection.getBalance(creator.publicKey);
    await program.methods.payout().accounts({ group: groupPda, recipient: creator.publicKey }).rpc();
    const after = await provider.connection.getBalance(creator.publicKey);
    const group = await program.account.group.fetch(groupPda);
    expect(after).to.be.greaterThan(before);
    expect(group.payoutIndex).to.equal(1);
    expect(group.cycleNumber.toNumber()).to.equal(1);
    expect(group.contributed.every((value) => value === false)).to.equal(true);
  });

  it("completes after each member has received one payout", async () => {
    for (const member of [creator, memberA, memberB]) {
      await program.methods.contribute().accounts({
        member: member.publicKey, group: groupPda, systemProgram: SystemProgram.programId,
      }).signers(member === creator ? [] : [member]).rpc();
    }
    await program.methods.payout().accounts({ group: groupPda, recipient: memberA.publicKey }).rpc();

    for (const member of [creator, memberA, memberB]) {
      await program.methods.contribute().accounts({
        member: member.publicKey, group: groupPda, systemProgram: SystemProgram.programId,
      }).signers(member === creator ? [] : [member]).rpc();
    }
    await program.methods.payout().accounts({ group: groupPda, recipient: memberB.publicKey }).rpc();

    const group = await program.account.group.fetch(groupPda);
    expect(group.completed).to.equal(true);
    expect(group.active).to.equal(false);
    expect(group.payoutIndex).to.equal(2);
    await expectFailure(
      program.methods.contribute().accounts({
        member: creator.publicKey, group: groupPda, systemProgram: SystemProgram.programId,
      }).rpc()
    );
  });
});
