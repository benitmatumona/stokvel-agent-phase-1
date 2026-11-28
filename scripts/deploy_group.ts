// Usage: ts-node scripts/deploy_group.ts <groupIdHex> <lamports> <maxMembers> <rulesHash>
// Creates the group on the cluster from ANCHOR_PROVIDER_URL / ANCHOR_WALLET
// and records the rules hash on-chain via the Memo program.
// Prints one JSON line: {"signature","group_pda","memo_signature"}
import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import { Stokvel } from "../target/types/stokvel";

const { PublicKey, Transaction, TransactionInstruction } = anchor.web3;
const MEMO = new PublicKey("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr");

async function main() {
  const [idHex, lamports, maxMembers, rulesHash] = process.argv.slice(2);
  if (!rulesHash) throw new Error("usage: deploy_group.ts <idHex> <lamports> <max> <hash>");
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);
  const program = anchor.workspace.Stokvel as Program<Stokvel>;
  const methods = (program as any).methods; // avoids very deep generated types
  const creator = provider.wallet.publicKey;

  const groupId = new anchor.BN(BigInt("0x" + idHex).toString());
  const [groupPda] = PublicKey.findProgramAddressSync(
    [Buffer.from("group"), creator.toBuffer(), groupId.toArrayLike(Buffer, "le", 8)],
    program.programId
  );

  const signature = await methods
    .createGroup(groupId, new anchor.BN(lamports), Number(maxMembers))
    .accounts({ creator } as any)
    .rpc();

  const memoIx = new TransactionInstruction({
    programId: MEMO,
    keys: [],
    data: Buffer.from(`stokvel:${idHex}:${rulesHash}`),
  });
  const memoSignature = await provider.sendAndConfirm(new Transaction().add(memoIx));

  console.log(JSON.stringify({ signature, group_pda: groupPda.toBase58(), memo_signature: memoSignature }));
}
main().catch((e) => { console.error(e); process.exit(1); });
