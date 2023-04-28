import json
from typing import List, Optional

from ex2 import *
from ex2.utils import *


def build_tx_message(transaction: Transaction) -> bytes:
    return json.dumps({"input": str(transaction.input), "output": str(transaction.output)}, sort_keys=True).encode()


class VirtualBlockchain:
    def __init__(self, initial_blockchain: List[Block], initial_utxo: List[Transaction]) -> None:
        self.blockchain: List[Block] = initial_blockchain
        self.utxo: List[Transaction] = initial_utxo

    def attempt_reorg(self, new_block_hash: BlockHash, sender: 'Node') -> List[Block]:

        new_chain: List[Block] = self.get_unknown_chain(new_block_hash, sender)
        if new_chain:
            old_chain: List[Block] = self.get_chain_until(new_chain[0])
            if len(new_chain) > len(old_chain):
                for block in old_chain:
                    self.rollback_block(block)
                for block in new_chain:
                    if not self.process_block(block):
                        break
        return self.blockchain

    def get_block(self, block_hash: BlockHash) -> Block:
        """
        This function returns a block object given its hash.
        If the block doesnt exist, a ValueError is raised.
        """
        for block in self.blockchain:
            if block.get_block_hash() == block_hash:
                return block
        raise ValueError("Non-existing block")

    def is_known_block(self, block_hash: BlockHash) -> bool:
        """
        This function returns a block object given its hash.
        If the block doesnt exist, a ValueError is raised.
        """
        if block_hash == GENESIS_BLOCK_PREV:
            return True
        for block in self.blockchain:
            if block.get_block_hash() == block_hash:
                return True
        return False

    def get_unknown_chain(self, block_hash: BlockHash, sender: 'Node') -> List[Block]:  # TODO check
        unknown_chain: List[Block] = []
        current_block_hash: BlockHash = block_hash
        while not self.is_known_block(current_block_hash):
            unknown_block: Block = sender.get_block(current_block_hash)
            unknown_chain.append(unknown_block)
            current_block_hash = unknown_block.get_prev_block_hash()
            if not self.validate_block(unknown_block):
                unknown_chain = []
                continue
        unknown_chain.reverse()
        return unknown_chain

    def validate_block(self, block: Block) -> bool:
        if len(block.get_transactions()) > BLOCK_SIZE:
            return False
        new_coin_counter = 0
        for tx in block.get_transactions():
            if not tx.input:
                new_coin_counter += 1
                continue
            if not self.validate_tx(tx):
                return False
        if new_coin_counter != 1:
            return False
        return True

    def validate_tx(self, transaction: Transaction) -> bool:
        return True

    def get_chain_until(self, split_block: Block) -> List[Block]:
        if not self.blockchain:
            return []
        current_block: Block = self.blockchain[-1]
        chain: List[Block] = []
        while not current_block.get_prev_block_hash() == GENESIS_BLOCK_PREV and not current_block.get_block_hash() == split_block.get_block_hash():
            chain.append(current_block)

            current_block = self.get_block(current_block.get_prev_block_hash())
        return chain

    def rollback_block(self, block: Block) -> None:
        for canceled_tx in block.get_transactions():
            # self.mempool = [tx for tx in self.mempool if tx.input != canceled_tx.get_txid()]
            self.utxo = [tx for tx in self.utxo if
                         tx.get_txid() != canceled_tx.get_txid() and tx.input != canceled_tx.get_txid()]
            if canceled_tx.input_tx:
                self.utxo.append(canceled_tx.input_tx)
        self.blockchain.remove(block)

    def process_block(self, new_block: Block) -> bool:
        for new_tx in new_block.get_transactions():
            if not self.is_transaction_valid(new_tx):
                return False
        self.blockchain.append(new_block)
        self.update_utxo_with_block(new_block)
        return True

    def is_transaction_valid(self, transaction: Transaction) -> bool:  # TODO create money fail
        if transaction.input is None:
            return True
        input_transaction: Optional[Transaction] = next(
            (unspent_transaction for unspent_transaction in self.utxo if
             unspent_transaction.get_txid() == transaction.input), None)
        if input_transaction is None:
            return False
        if not verify(build_tx_message(transaction), transaction.signature, input_transaction.output):
            return False
        return True

    def update_utxo_with_block(self, block: Block) -> None:
        new_transactions: List[Transaction] = block.get_transactions()
        self.utxo.extend(new_transactions)
        new_transactions_input: List[Optional[TxID]] = [transaction.input for transaction in new_transactions]
        self.utxo = [unspent_transaction for unspent_transaction in self.utxo if
                     unspent_transaction.get_txid() not in new_transactions_input]
