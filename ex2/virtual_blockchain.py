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
        self.new_chain: List[Block] = []
        self.old_chain: List[Block] = []
        self.deleted_txs: List[Transaction] = []

    def attempt_reorg(self, new_block_hash: BlockHash, sender: 'Node') -> List[Block]:
        split_hash: BlockHash = self.get_split_hash(new_block_hash, sender)
        if self.new_chain:
            self.compute_old_chain_until(split_hash)
            if len(self.new_chain) > len(self.old_chain):
                for block in self.old_chain:
                    self.rollback_block(block)
                    self.deleted_txs.extend(block.get_transactions())
                prev_block_hash = GENESIS_BLOCK_PREV
                if self.blockchain:
                    prev_block_hash = self.blockchain[-1]
                for block in self.new_chain:
                    # if block.get_prev_block_hash() != prev_block_hash: #TODO reactivate
                    #     break
                    if not self.process_block(block):
                        break
                    prev_block_hash = block.get_block_hash()
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
        if block_hash == GENESIS_BLOCK_PREV:
            return True
        for block in self.blockchain:
            if block.get_block_hash() == block_hash:
                return True
        return False

    def get_split_hash(self, block_hash: BlockHash, sender: 'Node') -> Optional[BlockHash]:  # TODO check
        current_block_hash: BlockHash = block_hash
        while not self.is_known_block(current_block_hash):
            try:
                unknown_block: Block = sender.get_block(current_block_hash)
                self.new_chain.append(unknown_block)
                current_block_hash = unknown_block.get_prev_block_hash()
                if current_block_hash is None:
                    raise ValueError
            except ValueError:
                self.new_chain = []
                return None
        self.new_chain.reverse()
        return current_block_hash

    def compute_old_chain_until(self, split_block: BlockHash) -> None:
        if not self.blockchain:
            return
        current_block: Block = self.blockchain[-1]
        while not current_block.get_prev_block_hash() == GENESIS_BLOCK_PREV and not current_block.get_block_hash() == split_block:
            self.old_chain.append(current_block)
            current_block = self.get_block(current_block.get_prev_block_hash())

    def validate_block(self, block: Block) -> bool:
        if len(block.get_transactions()) > BLOCK_SIZE:
            return False
        new_coin_counter = 0
        for tx in block.get_transactions():
            if not tx.input:
                new_coin_counter += 1
                continue
            if not self.is_transaction_valid(tx):
                return False
        if new_coin_counter != 1:
            return False
        return True

    def rollback_block(self, block: Block) -> None:
        for canceled_tx in block.get_transactions():
            # self.mempool = [tx for tx in self.mempool if tx.input != canceled_tx.get_txid()]
            self.utxo = [tx for tx in self.utxo if
                         tx.get_txid() != canceled_tx.get_txid() and tx.input != canceled_tx.get_txid()]
            if canceled_tx.input_tx:
                self.utxo.append(canceled_tx.input_tx)
        self.blockchain.remove(block)

    def process_block(self, new_block: Block) -> bool:
        if not self.validate_block(new_block):
            return False
        self.blockchain.append(new_block)
        self.update_utxo_with_block(new_block)
        return True

    def is_transaction_valid(self, transaction: Transaction) -> bool:
        if not transaction.output or not transaction.signature:
            return False
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
