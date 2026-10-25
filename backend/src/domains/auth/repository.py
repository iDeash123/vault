import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.models.enums import OAuthProvider, UserRole
from shared.db.models.user import OAuthAccount, RefreshSession, User
from shared.db.models.wallet import Wallet


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.lower())
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_wallet_by_user_id(self, user_id: uuid.UUID) -> Wallet | None:
        stmt = select(Wallet).where(Wallet.user_id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create_wallet(self, user_id: uuid.UUID) -> Wallet:
        wallet = await self.get_wallet_by_user_id(user_id)
        if wallet is not None:
            return wallet
        new_wallet = Wallet(
            user_id=user_id,
            currency="USD",
            available_balance=Decimal("0.00"),
            held_balance=Decimal("0.00"),
            claimable_balance=Decimal("0.00"),
        )
        self._session.add(new_wallet)
        await self._session.flush()
        return new_wallet

    async def create_user_with_wallet(
        self,
        email: str,
        username: str,
        password_hash: str | None,
        role: UserRole = UserRole.MEMBER,
        avatar_url: str | None = None,
        bio: str | None = None,
    ) -> tuple[User, Wallet]:
        user = User(
            email=email.lower(),
            username=username,
            password_hash=password_hash,
            role=role,
            is_active=True,
            avatar_url=avatar_url,
            bio=bio,
        )
        self._session.add(user)
        await self._session.flush()

        wallet = Wallet(
            user_id=user.id,
            currency="USD",
            available_balance=Decimal("0.00"),
            held_balance=Decimal("0.00"),
            claimable_balance=Decimal("0.00"),
        )
        self._session.add(wallet)
        await self._session.flush()
        return user, wallet

    async def create_refresh_session(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> RefreshSession:
        refresh_session = RefreshSession(
            user_id=user_id,
            token_hash=token_hash,
            user_agent=user_agent,
            ip_address=ip_address,
            expires_at=expires_at,
            revoked_at=None,
        )
        self._session.add(refresh_session)
        await self._session.flush()
        return refresh_session

    async def get_refresh_session_by_hash(
        self,
        token_hash: str,
        for_update: bool = False,
    ) -> RefreshSession | None:
        stmt = select(RefreshSession).where(RefreshSession.token_hash == token_hash)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke_refresh_session(
        self,
        session_record: RefreshSession,
        revoked_at: datetime,
    ) -> None:
        session_record.revoked_at = revoked_at
        await self._session.flush()

    async def revoke_all_user_refresh_sessions(
        self,
        user_id: uuid.UUID,
        revoked_at: datetime,
    ) -> None:
        stmt = (
            update(RefreshSession)
            .where(
                RefreshSession.user_id == user_id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def get_oauth_account(
        self,
        provider: OAuthProvider,
        provider_user_id: str,
    ) -> OAuthAccount | None:
        stmt = select(OAuthAccount).where(
            OAuthAccount.provider == provider,
            OAuthAccount.provider_user_id == provider_user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_oauth_account(
        self,
        user_id: uuid.UUID,
        provider: OAuthProvider,
        provider_user_id: str,
        email: str | None,
    ) -> OAuthAccount:
        oauth_account = OAuthAccount(
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
            email=email.lower() if email else None,
        )
        self._session.add(oauth_account)
        await self._session.flush()
        return oauth_account
