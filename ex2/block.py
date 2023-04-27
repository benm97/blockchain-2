import hashlib
import json
from typing import List, cast

from .transaction import Transaction
from .utils import BlockHash


class Block:
    def __init__(self, prev_block_hash: BlockHash, transactions: List[Transaction]) -> None:
        self.__transactions: List[Transaction] = transactions
        self.__prev_block_hash: BlockHash = prev_block_hash

    def get_block_hash(self) -> BlockHash:
        """returns hash of this block"""
        return cast(BlockHash, hashlib.sha256(self.__toJson()).digest())

    def get_transactions(self) -> List[Transaction]:
        """returns the list of transactions in this block."""
        return self.__transactions

    def get_prev_block_hash(self) -> BlockHash:
        """Gets the hash of the previous block in the chain"""
        return self.__prev_block_hash

    def __toJson(self) -> bytes:
        return json.dumps(self, default=lambda o: str(o) if type(o) == bytes else o.__dict__, sort_keys=True).encode()
