from binascii import hexlify
from bitpost.interface import BitpostInterface
from bit.network.meta import Unspent
from bit.transaction import calc_txid, deserialize
import binascii
import hashlib


class BitpostInterfaceForBit(BitpostInterface):

    def __init__(self, wallettoken=None, api_key=None, testnet=False):
        super().__init__(wallettoken=wallettoken, api_key=api_key, testnet=testnet)

    def get_change_utxos_from_bitpost(self):
        raw_change = super().get_change_utxos_from_bitpost()
        for request_group in raw_change:
            for request_change in request_group['change']:
                utxos = request_change.pop('utxos')
                request_change['utxos'] = [self._raw_utxos_to_unspents(raw_utxos_in_tx) for raw_utxos_in_tx in utxos]
        return raw_change

    def verify_change(self) -> (bool, str):
        all_PSTs = self.get_psts_for_verification()
        utxos = self.get_change_utxos_from_bitpost()

        inputs_per_broadcast_group = [{[TxInput(**utxo)]} for utxo in utxos]

        try:
            while len(inputs_per_broadcast_group) > 1:
                parent_psts_per_broadcast_group = VerificationUtils.get_parent_psts(inputs_per_broadcast_group, all_PSTs)
                psts = [pst for psts_in_group in parent_psts_per_broadcast_group for pst in psts_in_group]
                inputs_per_pst = VerificationUtils.psts_to_inputs(psts)
                inputs_per_broadcast_group = VerificationUtils.make_broadcast_groups(inputs_per_pst)
            return True, ""
        except Exception as ex:
            return False, ex.args[0]

    def _raw_utxo_to_unspent(self, raw_utxo):
        unspent = Unspent(amount=int(raw_utxo['amount']*100_000_000), confirmations=1,  # not relevant
                       script=raw_utxo['scriptPubKey'], txid=raw_utxo['txid'], txindex=raw_utxo['vout'])

        if '76a9' == raw_utxo['scriptPubKey'][:4]:
            unspent.set_type('p2pkh')
        else:
            unspent.set_type('np2wkh')
        return unspent

    def _raw_utxos_to_unspents(self, raw_utxos):
        unspents = []
        for raw_utxo in raw_utxos:
            if isinstance(raw_utxo, Unspent):
                unspents.append(raw_utxo)
            else:
                unspents.append(self._raw_utxo_to_unspent(raw_utxo))
        return unspents

    def get_feerates(self, max_feerate, size=50, can_reduce_fee=False, target=None):
        feerates = super().get_feerates(max_feerate, size, can_reduce_fee, target)
        return [int(feerate) for feerate in feerates]

class TxInput:

    def __init__(self, txid, vout, **kwargs):
        self.txid = txid
        self.vout = vout

    def __eq__(self, other):
        if isinstance(other, TxInput):
            return (self.txid == other.txid) and (self.vout == other.vout)
        else:
            return False

    def __repr__(self):
        return "TxInput(%s, %s)" % (self.txid, self.vout)

    def __hash__(self):
        return hash(self.__repr__())


class VerificationUtils:

    @classmethod
    def make_broadcast_groups(cls, input_sets):
        input_groups = []
        for utxos in input_sets:
            for i in range(len(input_groups)):
                if len(input_groups[i].intersection(utxos)):
                    input_groups[i] = input_groups[i].intersection(utxos)
                    break
            input_groups.append(utxos)
        return input_groups

    @classmethod
    def psts_to_inputs(cls, psts):
        input_sets = []
        for pst in psts:
            tx = deserialize(pst)
            utxos = [TxInput(hexlify(input.txid), hexlify(input.txindex)) for input in tx.TxIn]
            input_sets.append(set(utxos))
        return input_sets

    @classmethod
    def get_parent_psts(cls, inputs_per_broadcast_group, all_PSTs):
        parent_psts = []
        for inputs in inputs_per_broadcast_group:
            psts = set([])
            for input in inputs:
                if input.txid not in all_PSTs:
                    continue
                if input.txid == calc_txid(all_PSTs[input.txid]):
                    psts.add(all_PSTs[input.txid])
                else:
                    raise Exception("TxID provided doesn't match raw transaction! txid=" + input.txid)
            if len(psts) == 0:
                raise Exception('Referenced pre-signed transaction(s) not found!')
            parent_psts.append(psts)
        return parent_psts


class AddressUtils:

    @classmethod
    def HASH160(cls, hex):
        hash1 = hashlib.sha256(binascii.unhexlify(hex))
        hash2 = hashlib.new('ripemd160', hash1.digest())
        return hash2.hexdigest()
