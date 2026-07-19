"""One-shot synchronisation cycle (Starling → Actual → checkpoint)."""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from actual_starling_connector.actual.client import ActualClient
from actual_starling_connector.actual.mapping import map_feed_items_to_actual
from actual_starling_connector.config import Settings, SyncChannel
from actual_starling_connector.logging import get_logger
from actual_starling_connector.starling.client import StarlingClient
from actual_starling_connector.starling.models import FeedItem
from actual_starling_connector.state import SyncCheckpoint, SyncStateStore

FIRST_SYNC_LOOKBACK_DAYS = 90

ActualFactory = Callable[[], AbstractContextManager[ActualClient]]
StarlingChannelFactory = Callable[[SyncChannel], AbstractContextManager[StarlingClient]]


@dataclass(frozen=True, slots=True)
class SyncCycleResult:
    """Aggregated outcome of a multi-channel sync cycle."""

    fetched: int
    imported: int
    updated: int
    skipped: int
    duration_seconds: float
    last_transaction_id: str | None
    channels_succeeded: int
    channels_failed: int


def _latest_feed_item_uid(items: list[FeedItem]) -> str | None:
    if not items:
        return None
    latest = max(items, key=lambda item: item.transaction_time)
    return latest.feed_item_uid


class SyncWorker:
    """Orchestrates one multi-channel synchronisation cycle."""

    def __init__(
        self,
        settings: Settings,
        state_store: SyncStateStore,
        *,
        starling_factory: StarlingChannelFactory,
        actual_factory: ActualFactory,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._state_store = state_store
        self._starling_factory = starling_factory
        self._actual_factory = actual_factory
        self._clock = clock or (lambda: datetime.now(UTC))
        self._log = get_logger("sync")

    def run_once(self) -> SyncCycleResult:
        """Sync each enabled channel; save checkpoints only for successful ones."""
        started = time.perf_counter()
        channels = self._settings.enabled_channels()
        self._log.info(
            "sync_cycle_start",
            channels=[c.holder_type for c in channels],
        )

        fetched = imported = updated = skipped = 0
        last_transaction_id: str | None = None
        succeeded = 0
        failed = 0
        errors: list[BaseException] = []

        with self._actual_factory() as actual:
            for channel in channels:
                try:
                    channel_result = self._run_channel(channel, actual)
                except Exception as exc:
                    failed += 1
                    errors.append(exc)
                    self._log.exception(
                        "sync_channel_failed",
                        holder_type=channel.holder_type,
                    )
                    continue

                succeeded += 1
                fetched += channel_result.fetched
                imported += channel_result.imported
                updated += channel_result.updated
                skipped += channel_result.skipped
                if channel_result.last_transaction_id is not None:
                    last_transaction_id = channel_result.last_transaction_id

        duration = round(time.perf_counter() - started, 3)
        if succeeded == 0:
            self._log.error(
                "sync_cycle_failed",
                duration_seconds=duration,
                channels_failed=failed,
            )
            if errors:
                raise errors[0]
            msg = "No sync channels succeeded"
            raise RuntimeError(msg)

        result = SyncCycleResult(
            fetched=fetched,
            imported=imported,
            updated=updated,
            skipped=skipped,
            duration_seconds=duration,
            last_transaction_id=last_transaction_id,
            channels_succeeded=succeeded,
            channels_failed=failed,
        )
        self._log.info(
            "sync_cycle_finish",
            fetched=result.fetched,
            imported=result.imported,
            updated=result.updated,
            skipped=result.skipped,
            channels_succeeded=result.channels_succeeded,
            channels_failed=result.channels_failed,
            duration_seconds=result.duration_seconds,
        )
        return result

    def _run_channel(
        self,
        channel: SyncChannel,
        actual: ActualClient,
    ) -> SyncCycleResult:
        now = self._clock()
        checkpoint = self._state_store.get(channel.holder_type)
        changes_since = checkpoint.last_success_at or (
            now - timedelta(days=FIRST_SYNC_LOOKBACK_DAYS)
        )

        self._log.info(
            "sync_channel_start",
            holder_type=channel.holder_type,
            changes_since=changes_since.isoformat(),
            has_checkpoint=checkpoint.last_success_at is not None,
        )

        with self._starling_factory(channel) as starling:
            account = starling.get_primary_account()
            items = starling.list_feed_items(
                account.account_uid,
                account.default_category_uid,
                changes_since,
                settled_only=True,
            )

        mapped = map_feed_items_to_actual(items)
        import_result = actual.import_transactions(
            channel.actual_account_id,
            mapped,
        )

        finished_at = self._clock()
        last_txn_id = _latest_feed_item_uid(items)
        self._state_store.save(
            channel.holder_type,
            SyncCheckpoint(
                last_success_at=finished_at,
                last_transaction_id=last_txn_id,
                imported_count=import_result.added,
                skipped_count=import_result.unchanged,
            ),
        )

        result = SyncCycleResult(
            fetched=len(items),
            imported=import_result.added,
            updated=import_result.updated,
            skipped=import_result.unchanged,
            duration_seconds=0.0,
            last_transaction_id=last_txn_id,
            channels_succeeded=1,
            channels_failed=0,
        )
        self._log.info(
            "sync_channel_finish",
            holder_type=channel.holder_type,
            fetched=result.fetched,
            imported=result.imported,
            updated=result.updated,
            skipped=result.skipped,
            last_transaction_id=result.last_transaction_id,
        )
        return result


def default_starling_factory(_settings: Settings) -> StarlingChannelFactory:
    def factory(channel: SyncChannel) -> StarlingClient:
        return StarlingClient(channel.access_token, channel.holder_type)

    return factory


def default_actual_factory(settings: Settings) -> ActualFactory:
    def factory() -> ActualClient:
        extra_headers: dict[str, str] | None = None
        if (
            settings.actual_cf_access_client_id
            and settings.actual_cf_access_client_secret
        ):
            extra_headers = {
                "CF-Access-Client-Id": settings.actual_cf_access_client_id,
                "CF-Access-Client-Secret": settings.actual_cf_access_client_secret,
            }
        return ActualClient(
            settings.actual_server_url,
            settings.actual_sync_password,
            settings.actual_budget_sync_id,
            data_dir=settings.actual_data_dir,
            encryption_password=settings.actual_encryption_password,
            extra_headers=extra_headers,
        )

    return factory
