"""Real RS(255,223) coding and CRC validation of serialized bundle payloads."""
import base64
import json
import zlib

import numpy as np
from reedsolo import RSCodec, ReedSolomonError

N, K = 255, 223


class DecodeFailure(ValueError):
    def __init__(self, corrected=0, failed=1):
        super().__init__("FEC/CRC failed; sender must retain custody")
        self.corrected, self.failed = corrected, failed


def _encode_array(value):
    if isinstance(value, np.ndarray):
        return {"__dz_array__": True, "dtype": value.dtype.str, "shape": value.shape,
                "data": base64.b64encode(value.tobytes()).decode("ascii")}
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Unsupported payload value: {type(value).__name__}")


def _decode_array(value):
    if value.get("__dz_array__") is True:
        return np.frombuffer(base64.b64decode(value["data"]), dtype=value["dtype"]).reshape(value["shape"]).copy()
    return value


class PayloadCodec:
    def __init__(self):
        self.rs = RSCodec(N - K, nsize=N)

    def encode(self, payload):
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True, allow_nan=False,
                         default=_encode_array).encode("utf-8")
        packet = zlib.crc32(raw).to_bytes(4, "big") + raw
        return bytes(self.rs.encode(packet)), len(raw)

    def corrupt(self, wire, rssi, rng):
        """Seeded byte-error channel; FEC gets no error-location hint."""
        probability = .004 + .021 * max(0, min(1, (-80 - rssi) / 8))
        damaged, count = bytearray(wire), 0
        for i in range(len(damaged)):
            if rng.random() < probability:
                damaged[i] ^= rng.randrange(1, 256)
                count += 1
        return bytes(damaged), count

    def decode(self, damaged):
        packet, corrected, failed = bytearray(), 0, 0
        for start in range(0, len(damaged), N):
            try:
                decoded, _, positions = self.rs.decode(damaged[start:start + N])
                packet.extend(decoded)
                corrected += len(positions)
            except ReedSolomonError:
                failed += 1
        if failed:
            raise DecodeFailure(corrected, failed)
        raw = packet[4:]
        if len(packet) < 4 or zlib.crc32(raw) != int.from_bytes(packet[:4], "big"):
            raise DecodeFailure(corrected)
        try:
            return json.loads(raw, object_hook=_decode_array), corrected
        except (ValueError, TypeError, KeyError):
            raise DecodeFailure(corrected) from None
