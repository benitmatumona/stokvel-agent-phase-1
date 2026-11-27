use anchor_lang::prelude::*;
use anchor_lang::system_program;

declare_id!("2j75oQcmygUWj69thzMoF7yDwjmsmN5tnYVhCnGBH57h");

/// Maximum group size in this first release. A fixed-size account keeps rent
/// and account allocation predictable and avoids reallocating member arrays.
pub const MAX_MEMBERS: usize = 20;
pub const MIN_MEMBERS: u8 = 2;

#[program]
pub mod stokvel {
    use super::*;

    /// Creates a group. The creator is automatically member zero and receives
    /// the first payout in the rotation.
    pub fn create_group(
        ctx: Context<CreateGroup>,
        group_id: u64,
        contribution_lamports: u64,
        max_members: u8,
    ) -> Result<()> {
        require!(contribution_lamports > 0, StokvelError::InvalidContribution);
        require!(
            (MIN_MEMBERS..=MAX_MEMBERS as u8).contains(&max_members),
            StokvelError::InvalidMemberLimit
        );

        let group = &mut ctx.accounts.group;
        group.creator = ctx.accounts.creator.key();
        group.group_id = group_id;
        group.contribution_lamports = contribution_lamports;
        group.max_members = max_members;
        group.member_count = 1;
        group.members = [Pubkey::default(); MAX_MEMBERS];
        group.members[0] = ctx.accounts.creator.key();
        group.contributed = [false; MAX_MEMBERS];
        group.payout_index = 0;
        group.cycle_number = 0;
        group.active = false;
        group.completed = false;
        group.bump = ctx.bumps.group;
        Ok(())
    }

    /// Adds a unique member before the creator activates the group.
    pub fn join_group(ctx: Context<JoinGroup>) -> Result<()> {
        let group = &mut ctx.accounts.group;
        require!(!group.active && !group.completed, StokvelError::GroupNotJoinable);
        require!(
            group.member_count < group.max_members,
            StokvelError::GroupFull
        );
        require!(
            !group.members[..group.member_count as usize].contains(&ctx.accounts.member.key()),
            StokvelError::AlreadyMember
        );

        let index = group.member_count as usize;
        group.members[index] = ctx.accounts.member.key();
        group.contributed[index] = false;
        group.member_count = group
            .member_count
            .checked_add(1)
            .ok_or(StokvelError::ArithmeticOverflow)?;
        Ok(())
    }

    /// Locks the membership list. Once activated, members cannot be added or
    /// removed, making the payout rotation deterministic.
    pub fn activate_group(ctx: Context<ActivateGroup>) -> Result<()> {
        let group = &mut ctx.accounts.group;
        require_keys_eq!(
            group.creator,
            ctx.accounts.creator.key(),
            StokvelError::Unauthorized
        );
        require!(!group.active && !group.completed, StokvelError::InvalidGroupState);
        require!(group.member_count >= MIN_MEMBERS, StokvelError::NotEnoughMembers);
        group.active = true;
        Ok(())
    }

    /// A member contributes exactly once per payout cycle. SOL is transferred
    /// into the program-owned group account; no member can withdraw it directly.
    pub fn contribute(ctx: Context<Contribute>) -> Result<()> {
        let group = &mut ctx.accounts.group;
        require!(group.active && !group.completed, StokvelError::GroupNotActive);

        let member_key = ctx.accounts.member.key();
        let index = group.members[..group.member_count as usize]
            .iter()
            .position(|key| key == &member_key)
            .ok_or(StokvelError::NotMember)?;

        require!(!group.contributed[index], StokvelError::AlreadyContributed);

        let transfer_accounts = system_program::Transfer {
            from: ctx.accounts.member.to_account_info(),
            to: group.to_account_info(),
        };
        system_program::transfer(
            CpiContext::new(ctx.accounts.system_program.to_account_info(), transfer_accounts),
            group.contribution_lamports,
        )?;

        group.contributed[index] = true;
        Ok(())
    }

    /// Releases one full contribution pool to the next member in the fixed
    /// rotation. Anyone may call this once all members have contributed, but
    /// the recipient is derived from program state and cannot be chosen by
    /// the caller.
    pub fn payout(ctx: Context<Payout>) -> Result<()> {
        let group = &mut ctx.accounts.group;
        require!(group.active && !group.completed, StokvelError::GroupNotActive);

        let count = group.member_count as usize;
        require!(
            group.contributed[..count].iter().all(|contributed| *contributed),
            StokvelError::ContributionsIncomplete
        );

        let expected_recipient = group.members[group.payout_index as usize];
        require_keys_eq!(
            expected_recipient,
            ctx.accounts.recipient.key(),
            StokvelError::IncorrectPayoutRecipient
        );

        let payout_amount = group
            .contribution_lamports
            .checked_mul(group.member_count as u64)
            .ok_or(StokvelError::ArithmeticOverflow)?;

        // The group account must retain its rent-exempt minimum.
        let rent_reserve = Rent::get()?.minimum_balance(group.to_account_info().data_len());
        let available = group
            .to_account_info()
            .lamports()
            .checked_sub(rent_reserve)
            .ok_or(StokvelError::InsufficientEscrow)?;
        require!(available >= payout_amount, StokvelError::InsufficientEscrow);

        **group.to_account_info().try_borrow_mut_lamports()? -= payout_amount;
        **ctx.accounts.recipient.to_account_info().try_borrow_mut_lamports()? += payout_amount;

        // Start a fresh contribution round after the payout.
        group.contributed = [false; MAX_MEMBERS];
        group.cycle_number = group
            .cycle_number
            .checked_add(1)
            .ok_or(StokvelError::ArithmeticOverflow)?;

        if group.payout_index + 1 >= group.member_count {
            group.completed = true;
            group.active = false;
        } else {
            group.payout_index = group
                .payout_index
                .checked_add(1)
                .ok_or(StokvelError::ArithmeticOverflow)?;
        }

        emit!(PayoutReleased {
            group: group.key(),
            recipient: expected_recipient,
            amount_lamports: payout_amount,
            cycle_number: group.cycle_number,
        });
        Ok(())
    }
}

#[derive(Accounts)]
#[instruction(group_id: u64)]
pub struct CreateGroup<'info> {
    #[account(mut)]
    pub creator: Signer<'info>,
    #[account(
        init,
        payer = creator,
        space = Group::SPACE,
        seeds = [b"group", creator.key().as_ref(), &group_id.to_le_bytes()],
        bump
    )]
    pub group: Account<'info, Group>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct JoinGroup<'info> {
    #[account(mut)]
    pub member: Signer<'info>,
    #[account(mut)]
    pub group: Account<'info, Group>,
}

#[derive(Accounts)]
pub struct ActivateGroup<'info> {
    pub creator: Signer<'info>,
    #[account(mut)]
    pub group: Account<'info, Group>,
}

#[derive(Accounts)]
pub struct Contribute<'info> {
    #[account(mut)]
    pub member: Signer<'info>,
    #[account(mut)]
    pub group: Account<'info, Group>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct Payout<'info> {
    #[account(mut)]
    pub group: Account<'info, Group>,
    /// CHECK: The program checks this account equals the next member in the
    /// stored rotation before moving lamports to it.
    #[account(mut)]
    pub recipient: UncheckedAccount<'info>,
}

#[account]
pub struct Group {
    pub creator: Pubkey,
    pub group_id: u64,
    pub contribution_lamports: u64,
    pub max_members: u8,
    pub member_count: u8,
    pub members: [Pubkey; MAX_MEMBERS],
    pub contributed: [bool; MAX_MEMBERS],
    pub payout_index: u8,
    pub cycle_number: u64,
    pub active: bool,
    pub completed: bool,
    pub bump: u8,
}

impl Group {
    pub const SPACE: usize = 8
        + 32
        + 8
        + 8
        + 1
        + 1
        + (32 * MAX_MEMBERS)
        + MAX_MEMBERS
        + 1
        + 8
        + 1
        + 1
        + 1;
}

#[event]
pub struct PayoutReleased {
    pub group: Pubkey,
    pub recipient: Pubkey,
    pub amount_lamports: u64,
    pub cycle_number: u64,
}

#[error_code]
pub enum StokvelError {
    #[msg("Contribution amount must be greater than zero.")]
    InvalidContribution,
    #[msg("Member limit must be between 2 and 20.")]
    InvalidMemberLimit,
    #[msg("This group is no longer accepting members.")]
    GroupNotJoinable,
    #[msg("The group has reached its member limit.")]
    GroupFull,
    #[msg("Wallet is already a member of this group.")]
    AlreadyMember,
    #[msg("Arithmetic overflow.")]
    ArithmeticOverflow,
    #[msg("Only the group creator may activate the group.")]
    Unauthorized,
    #[msg("Group must contain at least two members.")]
    NotEnoughMembers,
    #[msg("Group is not in an active state.")]
    InvalidGroupState,
    #[msg("Group is not active.")]
    GroupNotActive,
    #[msg("Wallet is not a member of this group.")]
    NotMember,
    #[msg("Member has already contributed in this cycle.")]
    AlreadyContributed,
    #[msg("Every member must contribute before payout.")]
    ContributionsIncomplete,
    #[msg("Payout recipient is not next in the rotation.")]
    IncorrectPayoutRecipient,
    #[msg("Escrow does not contain enough withdrawable lamports.")]
    InsufficientEscrow,
}
