import json
import secrets
from typing import Set, Optional, List, cast

from .block import Block
from .transaction import Transaction
from .utils import *
from .virtual_blockchain import VirtualBlockchain


def new_coin_tx(target: PublicKey) -> Transaction:
    return Transaction(target, None, cast(Signature, secrets.token_bytes(48)))


def build_message(coin: Transaction, target: PublicKey) -> dict:
    return {"input": str(coin.get_txid()),
            "output": str(target)}


def build_tx_message(transaction: Transaction) -> bytes:
    return json.dumps({"input": str(transaction.input), "output": str(transaction.output)}, sort_keys=True).encode()


class Node:
    def __init__(self) -> None:
        """Creates a new node with an empty mempool and no connections to others.
        Blocks mined by this node will reward the miner with a single new coin,
        created out of thin air and associated with the mining reward address"""  # TODO reward
        keys: Tuple[PrivateKey, PublicKey] = gen_keys()
        self.__private_key: PrivateKey = keys[0]
        self.__public_key: PublicKey = keys[1]

        self.__blockchain: List[Block] = []
        self.__mempool: List[Transaction] = []
        self.__utxo: List[Transaction] = []

        self.__connected_nodes: Set[Node] = set()

    def connect(self, other: 'Node') -> None:
        """connects this node to another node for block and transaction updates.
        Connections are bi-directional, so the other node is connected to this one as well.
        Raises an exception if asked to connect to itself.
        The connection itself does not trigger updates about the mempool,
        but nodes instantly notify of their latest block to each other (see notify_of_block)"""
        if other.get_address() == self.get_address():
            raise Exception("Connection to itself")

        self.__connected_nodes.add(other)
        if self not in other.get_connections():
            other.connect(self)
        other.notify_of_block(self.get_latest_hash(), self)

    def disconnect_from(self, other: 'Node') -> None:
        """Disconnects this node from the other node. If the two were not connected, then nothing happens"""
        if other in self.__connected_nodes:
            self.__connected_nodes.remove(other)
            other.disconnect_from(self)

    def get_connections(self) -> Set['Node']:
        """Returns a set containing the connections of this node."""
        return self.__connected_nodes

    def add_transaction_to_mempool(self, transaction: Transaction) -> bool:
        """
        This function inserts the given transaction to the mempool.
        It will return False iff any of the following conditions hold:
        (i) the transaction is invalid (the signature fails)
        (ii) the source doesn't have the coin that it tries to spend
        (iii) there is contradicting tx in the mempool.

        If the transaction is added successfully, then it is also sent to neighboring nodes.
        Transactions that create money (with no inputs) are not placed in the mempool, and not propagated. 
        """

        if self.__is_transaction_valid(transaction):  # TODO create money fail
            self.__mempool.append(transaction)
            self.__propagate_tx(transaction)
            return True
        return False

    def notify_of_block(self, block_hash: BlockHash, sender: 'Node') -> None:
        """This method is used by a node's connection to inform it that it has learned of a
        new block (or created a new block). If the block is unknown to the current Node, The block is requested.
        We assume the sender of the message is specified, so that the node can choose to request this block if
        it wishes to do so.
        (if it is part of a longer unknown chain, these blocks are requested as well, until reaching a known block).
        Upon receiving new blocks, they are processed and and checked for validity (check all signatures, hashes,
        block size , etc).
        If the block is on the longest chain, the mempool and utxo change accordingly (ties, i.e., chains of similar length to that of this node are not adopted).
        If the block is indeed the tip of the longest chain,
        a notification of this block is sent to the neighboring nodes of this node.
        (no need to notify of previous blocks -- the nodes will fetch them if needed)

        A reorg may be triggered by this block's introduction. In this case the utxo is rolled back to the split point,
        and then rolled forward along the new branch.
        Be careful -- the new branch may contain invalid blocks.
        These and blocks that point to them should not be accepted to the blockchain (but earlier valid blocks may still form a longer chain)
        the mempool is similarly emptied of transactions that cannot be executed now.
        transactions that were rolled back and can still be executed are re-introduced into the mempool if they do
        not conflict.
        """

        virtual_chain: VirtualBlockchain = VirtualBlockchain(self.__blockchain.copy(), self.__utxo.copy())
        if len(virtual_chain.attempt_reorg(block_hash, sender)) > len(self.__blockchain):
            self.__blockchain = virtual_chain.blockchain
            self.__utxo = virtual_chain.utxo
            mempool_backup = self.__mempool.copy()
            self.__mempool = []
            self.__mempool = [tx for tx in mempool_backup if self.__is_transaction_valid(tx)]
            self.__propagate_block(self.__blockchain[-1])

    def mine_block(self) -> BlockHash:
        """"
        This function allows the node to create a single block.
        The block should contain BLOCK_SIZE transactions (unless there aren't enough in the mempool). Of these,
        BLOCK_SIZE-1 transactions come from the mempool and one addtional transaction will be included that creates
        money and adds it to the address of this miner.
        Money creation transactions have None as their input, and instead of a signature, contain 48 random bytes.
        If a new block is created, all connections of this node are notified by calling their notify_of_block() method.
        The method returns the new block hash.
        """
        last_index = BLOCK_SIZE - 1 if len(self.__mempool) > BLOCK_SIZE - 1 else len(self.__mempool)
        new_block: Block = Block(self.get_latest_hash(),
                                 self.__mempool[:last_index] + [new_coin_tx(self.get_address())])
        self.__blockchain.append(new_block)
        self.__propagate_block(new_block)
        self.__mempool = self.__mempool[last_index:]
        self.__update_utxo_with_block(new_block)  # TODO Update utxo?
        return self.get_latest_hash()

    def get_block(self, block_hash: BlockHash) -> Block:
        """
        This function returns a block object given its hash.
        If the block doesnt exist, a ValueError is raised.
        """
        for block in self.__blockchain:
            if block.get_block_hash() == block_hash:
                return block
        raise ValueError("Non-existing block")

    def get_latest_hash(self) -> BlockHash:
        """
        This function returns the last block hash known to this node (the tip of its current chain).
        """
        if len(self.__blockchain) == 0:
            return GENESIS_BLOCK_PREV
        return self.__blockchain[-1].get_block_hash()

    def get_mempool(self) -> List[Transaction]:
        """
        This function returns the list of transactions that didn't enter any block yet.
        """
        return self.__mempool

    def get_utxo(self) -> List[Transaction]:
        """
        This function returns the list of unspent transactions.
        """
        return self.__utxo

    # ------------ Formerly wallet methods: -----------------------

    def create_transaction(self, target: PublicKey) -> Optional[Transaction]:
        """
        This function returns a signed transaction that moves an unspent coin to the target.
        It chooses the coin based on the unspent coins that this node has.
        If the node already tried to spend a specific coin, and such a transaction exists in its mempool,
        but it did not yet get into the blockchain then it should'nt try to spend it again (until clear_mempool() is
        called -- which will wipe the mempool and thus allow to attempt these re-spends).
        The method returns None if there are no outputs that have not been spent already.

        The transaction is added to the mempool (and as a result is also published to neighboring nodes)
        """
        available_coin: Optional[Transaction] = next(
            (transaction for transaction in self.get_utxo() if
             transaction.output == self.get_address() and transaction not in self.get_mempool()), None)
        if available_coin is None:
            return None
        signature: Signature = sign(json.dumps(build_message(available_coin, target), sort_keys=True).encode(),
                                    self.__private_key)
        tx: Transaction = Transaction(target, available_coin.get_txid(), signature)
        tx.input_tx = available_coin
        self.add_transaction_to_mempool(tx)
        return tx

    def clear_mempool(self) -> None:
        """
        Clears the mempool of this node. All transactions waiting to be entered into the next block are gone.
        """
        self.__mempool.clear()

    def get_balance(self) -> int:
        """
        This function returns the number of coins that this node owns according to its view of the blockchain.
        Coins that the node owned and sent away will still be considered as part of the balance until the spending
        transaction is in the blockchain.
        """
        return len([tx for tx in self.__utxo if tx.output == self.get_address()])

    def get_address(self) -> PublicKey:
        """
        This function returns the public address of this node (its public key).
        """
        return self.__public_key

    def __is_transaction_valid(self, transaction: Transaction) -> bool:  # TODO create money fail
        if transaction.input is None:
            return False
        if transaction.input in [transaction.input for transaction in self.__mempool]:
            return False
        input_transaction: Optional[Transaction] = next(
            (unspent_transaction for unspent_transaction in self.get_utxo() if
             unspent_transaction.get_txid() == transaction.input), None)
        if input_transaction is None:
            return False
        if not verify(build_tx_message(transaction), transaction.signature, input_transaction.output):
            return False
        return True

    def __propagate_tx(self, transaction: Transaction) -> None:
        for node in self.__connected_nodes:
            node.add_transaction_to_mempool(transaction)

    def __propagate_block(self, block: Block) -> None:
        for node in self.__connected_nodes:
            node.notify_of_block(block.get_block_hash(), self)

    def __update_utxo_with_block(self, block: Block) -> None:
        new_transactions: List[Transaction] = block.get_transactions()
        self.__utxo.extend(new_transactions)
        new_transactions_input: List[Optional[TxID]] = [transaction.input for transaction in new_transactions]
        self.__utxo = [unspent_transaction for unspent_transaction in self.__utxo if
                       unspent_transaction.get_txid() not in new_transactions_input]


"""
Importing this file should NOT execute code. It should only create definitions for the objects above.
Write any tests you have in a different file.
You may add additional methods, classes and files but be sure no to change the signatures of methods
included in this template.
"""
