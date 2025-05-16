from pathlib import Path

from jitabi import JITContext
from jitabi.json import ABI

# import json as js
# from jitabi.utils import JSONHexEncoder

'''
Samples used in test:

actual_result = {
    "head": {
        "block_num": 23,
        "block_id": "00000017d1359487a1d12277aec6a0d50207a7fa3a46a0b18ad11a6a093594b4"
    },
    "last_irreversible": {
        "block_num": 21,
        "block_id": "0000001522ebe6ddc1f00b426e69faa006026c7dcf59815d0282cb579c8e21d1"
    },
    "this_block": {
        "block_num": 10,
        "block_id": "0000000ac54a7ca25f05f01a1caa35040d73e8a1298fbfadc9ad3bf18694243a"
    },
    "prev_block": {
        "block_num": 9,
        "block_id": "00000009485ad52d4d4d387b27c562a911790007288231fc107f80c77ebee29b"
    },
    "block": "be92725e0000000000ea3055000000000009485ad52d4d4d387b27c562a911790007288231fc107f80c77ebee29b0000000000000000000000000000000000000000000000000000000000000000d007eefcb4c20a0ee78d2dfe8446527d91ab984240edea8fc5a7062100e4dedb00000000000000202ea20c87518fc9bfa42deb7bb1791e81657cca8c52f30042960690b480cd067e2b454c73eebda1087394fbffc9a606043fd89f8a4601abeedebd853873e5c9fa0000",
    "traces": None,
    "deltas": None,
    "type": "get_blocks_result_v0"
}

actual_signed_block = {
    "previous": "00000016da8c9c17de0607fb22bbcccdfc2f95b9c85461d7ccde1fc2c097410e",
    "new_producers": null,
    "header_extensions": [],
    "timestamp": 1599457177,
    "schedule_version": 0,
    "action_mroot": "439dd15b0ea5bf1a1a399e9f3423ad1e6041810cde302e40931adfccded25013",
    "producer": 6138663577826885632,
    "producer_signature": "001f56003fdde5c4ead202d7dde4e7af74ae087aed3a699b5cc6745c9aa6beb14f36761919302cdd6a88cf410a8390fbd2cb76dd4ea0441f30b1fee0b781f11e812b",
    "block_extensions": [],
    "transaction_mroot": "fec74205e7462bb45dba6e21443ceb7ccd0c68dd9e6dcafddcb6c18b5c0f7d44",
    "transactions": [
        {
            "cpu_usage_us": 1103,
            "net_usage_words": 42,
            "status": 0,
            "trx": {
                "packed_context_free_data": "",
                "signatures": [
                    "001f1678ccbb248596e3aecb7c37fa5569a37db46d7f09563e1231aaa9bed40fac730c2a2eecd58434cb683dbcdd2f854ab4cc854e874f9f8a4a3695971f66e7d6fc"
                ],
                "packed_trx": "d02a18681500f507a3a200ff0000030000000000ea305500409e9a2264b89a010000000000ea305500000000a8ed3232660000000000ea305550352ab4a9d177570100000001000216321ff9740bec8421cc2b0279c3a1852ea46e1e7b8159df3c937ad44e2fb6d6010000000100000001000216321ff9740bec8421cc2b0279c3a1852ea46e1e7b8159df3c937ad44e2fb6d6010000000000000000ea305500b0cafe4873bd3e010000000000ea305500000000a8ed3232140000000000ea305550352ab4a9d17757809698000000000000ea305500003f2a1ba6a24a010000000000ea305500000000a8ed3232310000000000ea305550352ab4a9d17757a08601000000000004544c4f53000000a08601000000000004544c4f530000000100",
                "type": 1,
                "compression": 0
            }
        },
        {
            "trx": {
                "compression": 0,
                "packed_trx": "d02a18681500f507a3a200ff00000100a6823403ea3055000000572d3ccdcd010000000000ea305500000000a8ed3232210000000000ea305550352ab4a9d17757a08601000000000004544c4f530000000000",
                "type": 1,
                "packed_context_free_data": "",
                "signatures": [
                    "001f71e1c8ec416f658f0a59d48e435ce9f539a72f980cd922407315277594e6c70f071a86ad33138b3dd37fdfc38434b3254c0dba17625f239de6c7ac7a7e7fb03e"
                ]
            },
            "status": 0,
            "cpu_usage_us": 129,
            "net_usage_words": 16
        }
    ],
    "confirmed": 0
}
'''


ABI_DIR = Path(__file__).with_name('abis')


def test_std_abi():
    jit = JITContext(cache_path='tests/.jitabi')

    abi = ABI.from_file(ABI_DIR / 'std_abi.json')


    actual_block_raw = bytes.fromhex('99c7555f0000000000ea3055000000000016da8c9c17de0607fb22bbcccdfc2f95b9c85461d7ccde1fc2c097410efec74205e7462bb45dba6e21443ceb7ccd0c68dd9e6dcafddcb6c18b5c0f7d44439dd15b0ea5bf1a1a399e9f3423ad1e6041810cde302e40931adfccded25013000000000000001f56003fdde5c4ead202d7dde4e7af74ae087aed3a699b5cc6745c9aa6beb14f36761919302cdd6a88cf410a8390fbd2cb76dd4ea0441f30b1fee0b781f11e812b02004f0400002a0101001f1678ccbb248596e3aecb7c37fa5569a37db46d7f09563e1231aaa9bed40fac730c2a2eecd58434cb683dbcdd2f854ab4cc854e874f9f8a4a3695971f66e7d6fc0000a102d02a18681500f507a3a200ff0000030000000000ea305500409e9a2264b89a010000000000ea305500000000a8ed3232660000000000ea305550352ab4a9d177570100000001000216321ff9740bec8421cc2b0279c3a1852ea46e1e7b8159df3c937ad44e2fb6d6010000000100000001000216321ff9740bec8421cc2b0279c3a1852ea46e1e7b8159df3c937ad44e2fb6d6010000000000000000ea305500b0cafe4873bd3e010000000000ea305500000000a8ed3232140000000000ea305550352ab4a9d17757809698000000000000ea305500003f2a1ba6a24a010000000000ea305500000000a8ed3232310000000000ea305550352ab4a9d17757a08601000000000004544c4f53000000a08601000000000004544c4f5300000001000081000000100101001f71e1c8ec416f658f0a59d48e435ce9f539a72f980cd922407315277594e6c70f071a86ad33138b3dd37fdfc38434b3254c0dba17625f239de6c7ac7a7e7fb03e000053d02a18681500f507a3a200ff00000100a6823403ea3055000000572d3ccdcd010000000000ea305500000000a8ed3232210000000000ea305550352ab4a9d17757a08601000000000004544c4f53000000000000')
    actual_raw_result = bytes.fromhex('011700000000000017d1359487a1d12277aec6a0d50207a7fa3a46a0b18ad11a6a093594b4150000000000001522ebe6ddc1f00b426e69faa006026c7dcf59815d0282cb579c8e21d1010a0000000000000ac54a7ca25f05f01a1caa35040d73e8a1298fbfadc9ad3bf18694243a010900000000000009485ad52d4d4d387b27c562a911790007288231fc107f80c77ebee29b01b801be92725e0000000000ea3055000000000009485ad52d4d4d387b27c562a911790007288231fc107f80c77ebee29b0000000000000000000000000000000000000000000000000000000000000000d007eefcb4c20a0ee78d2dfe8446527d91ab984240edea8fc5a7062100e4dedb00000000000000202ea20c87518fc9bfa42deb7bb1791e81657cca8c52f30042960690b480cd067e2b454c73eebda1087394fbffc9a606043fd89f8a4601abeedebd853873e5c9fa00000000')
    actual_raw_result_block = bytes.fromhex("be92725e0000000000ea3055000000000009485ad52d4d4d387b27c562a911790007288231fc107f80c77ebee29b0000000000000000000000000000000000000000000000000000000000000000d007eefcb4c20a0ee78d2dfe8446527d91ab984240edea8fc5a7062100e4dedb00000000000000202ea20c87518fc9bfa42deb7bb1791e81657cca8c52f30042960690b480cd067e2b454c73eebda1087394fbffc9a606043fd89f8a4601abeedebd853873e5c9fa0000")

    def test_with_module(std):
        # result
        unpacked_result = std.unpack_result(actual_raw_result)
        packed_result = std.pack_result(unpacked_result)

        assert packed_result == actual_raw_result

        # signed block
        unpacked = std.unpack_signed_block(actual_block_raw)
        packed = std.pack_signed_block(unpacked)

        assert packed == actual_block_raw

        # signed block inside result
        unpacked = std.unpack_signed_block(actual_raw_result_block)
        packed = std.pack_signed_block(unpacked)

        assert packed == actual_raw_result_block
        assert packed == unpacked_result['block']

        # print(js.dumps(unpacked, indent=4, cls=JSONHexEncoder))

    # no cache
    standard = jit.module_for_abi(
        'standard',
        abi,
        # debug=True,
        use_cache=False
    )
    test_with_module(standard)

    # cache
    standard = jit.module_for_abi('standard', abi)
    test_with_module(standard)
