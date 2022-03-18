import gate_api
from gate_api.exceptions import ApiException, GateApiException

import hashlib
import hmac
import logging
import time
from collections import defaultdict
from json.decoder import JSONDecodeError
from typing import TYPE_CHECKING, Any, DefaultDict, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import requests

from rotkehlchen.accounting.ledger_actions import LedgerAction, LedgerActionType
from rotkehlchen.accounting.structures import Balance
from rotkehlchen.assets.asset import Asset
from rotkehlchen.assets.converters import asset_from_gateio
from rotkehlchen.constants.misc import ZERO
from rotkehlchen.constants.timing import DEFAULT_TIMEOUT_TUPLE
from rotkehlchen.errors import DeserializationError, RemoteError, UnknownAsset, UnsupportedAsset
from rotkehlchen.exchanges.data_structures import AssetMovement, MarginPosition, Trade
from rotkehlchen.exchanges.exchange import ExchangeInterface, ExchangeQueryBalances
from rotkehlchen.exchanges.utils import deserialize_asset_movement_address, get_key_if_has_val
from rotkehlchen.inquirer import Inquirer
from rotkehlchen.logging import RotkehlchenLogsAdapter
from rotkehlchen.serialization.deserialize import (
    deserialize_asset_amount,
    deserialize_asset_amount_force_positive,
    deserialize_asset_movement_category,
    deserialize_fee,
    deserialize_timestamp_from_date,
)
from rotkehlchen.types import (
    ApiKey,
    ApiSecret,
    AssetAmount,
    AssetMovementCategory,
    Fee,
    Location,
    Price,
    Timestamp,
    TradeType,
)
from rotkehlchen.user_messages import MessagesAggregator
from rotkehlchen.utils.mixins.cacheable import cache_response_timewise
from rotkehlchen.utils.mixins.lockable import protect_with_lock
from rotkehlchen.utils.serialization import jsonloads_dict

if TYPE_CHECKING:
    from rotkehlchen.db.dbhandler import DBHandler

logger = logging.getLogger(__name__)
log = RotkehlchenLogsAdapter(logger)


class GatePermissionError(Exception):
    pass


class Gate(ExchangeInterface):  # lgtm[py/missing-call-to-init]

    def validate_api_key(self) -> Tuple[bool, str]:
        pass

    def query_online_trade_history(self, start_ts: Timestamp, end_ts: Timestamp) -> Tuple[
        List[Trade], Tuple[Timestamp, Timestamp]]:
        pass

    def query_online_margin_history(self, start_ts: Timestamp, end_ts: Timestamp) -> List[MarginPosition]:
        pass

    def query_online_deposits_withdrawals(self, start_ts: Timestamp, end_ts: Timestamp) -> List[AssetMovement]:
        pass

    def query_online_income_loss_expense(self, start_ts: Timestamp, end_ts: Timestamp) -> List[LedgerAction]:
        pass

    def __init__(
            self,
            name: str,
            api_key: ApiKey,
            secret: ApiSecret,
            database: 'DBHandler',
            msg_aggregator: MessagesAggregator,
    ):
        super().__init__(
            name=name,
            location=Location.GATEIO,
            api_key=api_key,
            secret=secret,
            database=database,
        )
        self.apiversion = 'v4'
        self.base_uri = 'https://api.gateio.ws/api/v4'
        self.msg_aggregator = msg_aggregator
        # self.session.headers.update({'GATEIO-ACCESS-KEY': self.api_key})

    def first_connection(self) -> None:
        self.first_connection_made = True

    def edit_exchange_credentials(
            self,
            api_key: Optional[ApiKey],
            api_secret: Optional[ApiSecret],
            passphrase: Optional[str],
    ) -> bool:
        changed = super().edit_exchange_credentials(api_key, api_secret, passphrase)
        #if api_key is not None:
        #    self.session.headers.update({'GATEIO-ACCESS-KEY': self.api_key})
        return changed

    @protect_with_lock()
    @cache_response_timewise()
    def query_balances(self) -> ExchangeQueryBalances:
        returned_balances: DefaultDict[Asset, Balance] = defaultdict(Balance)
        returned_balances[Asset('USDT')] += Balance(
            amount=0,
            usd_value=0,
        )
        return dict(returned_balances), ''