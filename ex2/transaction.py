import hashlib
import json
from typing import Optional, cast

from .utils import PublicKey, TxID, Signature


class Transaction:
    """Represents a transaction that moves a single coin
    A transaction with no source creates money. It will only be created by the bank."""

    def __init__(self, output: PublicKey, input: Optional[TxID], signature: Signature) -> None:
        # do not change the name of this field:
        self.output: PublicKey = output
        # do not change the name of this field:
        self.input: Optional[TxID] = input
        # do not change the name of this field:
        self.signature: Signature = signature

    def get_txid(self) -> TxID:
        """Returns the identifier of this transaction. This is the SHA256 of the transaction contents."""
        return cast(TxID, hashlib.sha256(self.__toJson()).digest())

    def __toJson(self) -> bytes:
        return json.dumps(self, default=lambda o: str(o) if type(o) == bytes else o.__dict__,
                          sort_keys=True).encode()
