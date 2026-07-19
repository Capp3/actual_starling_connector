"""Pydantic models for Starling Customer API responses."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Money(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    currency: str
    minor_units: int = Field(alias="minorUnits")


class StarlingAccount(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    account_uid: str = Field(alias="accountUid")
    default_category_uid: str = Field(alias="defaultCategory")
    currency: str
    name: str | None = None
    account_type: str | None = Field(default=None, alias="accountType")


class AccountsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    accounts: list[StarlingAccount]


class AccountHolder(BaseModel):
    """Account holder bound to the access token (not an account row)."""

    model_config = ConfigDict(populate_by_name=True)

    account_holder_uid: str = Field(alias="accountHolderUid")
    account_holder_type: str = Field(alias="accountHolderType")


class FeedItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    feed_item_uid: str = Field(alias="feedItemUid")
    category_uid: str = Field(alias="categoryUid")
    amount: Money
    source_amount: Money = Field(alias="sourceAmount")
    direction: str
    transaction_time: datetime = Field(alias="transactionTime")
    updated_at: datetime = Field(alias="updatedAt")
    status: str
    counter_party_name: str | None = Field(default=None, alias="counterPartyName")
    reference: str | None = None
    settlement_time: datetime | None = Field(default=None, alias="settlementTime")


class FeedItemsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    feed_items: list[FeedItem] = Field(default_factory=list, alias="feedItems")
