import json as stdjson
from pathlib import Path

from jitabi import JITContext
from jitabi.json import ABI
from jitabi.utils import JSONHexEncoder

ABI_DIR = Path(__file__).with_name('abis')


def test_std_abi():
    jit = JITContext(cache_path='tests/.jitabi')

    abi = ABI.from_file(ABI_DIR / 'std_abi.json')

    # no cache
    standard = jit.module_for_abi(
        'standard',
        abi,
        debug=True,
        use_cache=False
    )

    raw_result = bytes.fromhex('011700000000000017d1359487a1d12277aec6a0d50207a7fa3a46a0b18ad11a6a093594b4150000000000001522ebe6ddc1f00b426e69faa006026c7dcf59815d0282cb579c8e21d1010a0000000000000ac54a7ca25f05f01a1caa35040d73e8a1298fbfadc9ad3bf18694243a010900000000000009485ad52d4d4d387b27c562a911790007288231fc107f80c77ebee29b01b801be92725e0000000000ea3055000000000009485ad52d4d4d387b27c562a911790007288231fc107f80c77ebee29b0000000000000000000000000000000000000000000000000000000000000000d007eefcb4c20a0ee78d2dfe8446527d91ab984240edea8fc5a7062100e4dedb00000000000000202ea20c87518fc9bfa42deb7bb1791e81657cca8c52f30042960690b480cd067e2b454c73eebda1087394fbffc9a606043fd89f8a4601abeedebd853873e5c9fa00000000')

    result = standard.unpack_result(raw_result)

    print(stdjson.dumps(result, cls=JSONHexEncoder, indent=4))

    re_packed_result = standard.pack_result(result)

    print(re_packed_result)

    assert raw_result == re_packed_result

    re_unpacked_result = standard.unpack_result(re_packed_result)

    assert result == re_unpacked_result

    # cache
    standard = jit.module_for_abi('standard', abi)

    raw_result = bytes.fromhex('011700000000000017d1359487a1d12277aec6a0d50207a7fa3a46a0b18ad11a6a093594b4150000000000001522ebe6ddc1f00b426e69faa006026c7dcf59815d0282cb579c8e21d1010a0000000000000ac54a7ca25f05f01a1caa35040d73e8a1298fbfadc9ad3bf18694243a010900000000000009485ad52d4d4d387b27c562a911790007288231fc107f80c77ebee29b01b801be92725e0000000000ea3055000000000009485ad52d4d4d387b27c562a911790007288231fc107f80c77ebee29b0000000000000000000000000000000000000000000000000000000000000000d007eefcb4c20a0ee78d2dfe8446527d91ab984240edea8fc5a7062100e4dedb00000000000000202ea20c87518fc9bfa42deb7bb1791e81657cca8c52f30042960690b480cd067e2b454c73eebda1087394fbffc9a606043fd89f8a4601abeedebd853873e5c9fa00000000')

    result = standard.unpack_result(raw_result)

    print(stdjson.dumps(result, cls=JSONHexEncoder, indent=4))
