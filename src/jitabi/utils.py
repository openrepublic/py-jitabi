import json


class JSONHexEncoder(json.JSONEncoder):
    def default(self, obj):
        # hex string on bytes
        if isinstance(obj, (bytes, bytearray)):
            return obj.hex()

        return super().default(obj)
