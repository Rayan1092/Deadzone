"""Command's radio prediction: public prior plus delivered relay reports only."""
import base64
from copy import deepcopy
import zlib

import numpy as np

from ..floorplan import FloorPlan
from ..network.propagation import rssi_grid


class CoverageGrid:
    def __init__(self, prior):
        # Own a sanitized snapshot, even if a caller accidentally passes truth.
        # Occupancy reports cannot establish a wall's radio material/loss.
        self.prior = FloorPlan(prior.planning_data())
        self.relays = {}
        self._grids = {}
        self._key = None
        self._encoded = None

    def report_relay(self, payload):
        # Called only after CommandPost accepts the delivered report's version.
        # Relay radios use the fixed 20 dBm model, as in Sim._nodes.
        self.relays[payload["id"]] = (tuple(payload["pos"]), bool(payload.get("on", True)))

    def view(self):
        sources = {"CMD": (self.prior.cmd_pos, self.prior.cmd_tx)}
        sources.update({rid: (pos, 20.0) for rid, (pos, on) in self.relays.items() if on})
        key = tuple(sorted(sources.items()))
        if key != self._key:
            # Cache by position/power, not report timestamp: stationary relays
            # need no new propagation work when they report again.
            for rid in self._grids.keys() - sources.keys():
                del self._grids[rid]
            for rid, source in sources.items():
                if rid not in self._grids or self._grids[rid][0] != source:
                    self._grids[rid] = (source, rssi_grid(self.prior, *source))
            strongest = np.maximum.reduce([entry[1] for entry in self._grids.values()])
            raw = np.clip(np.rint(strongest), -128, 127).astype(np.int8).tobytes()
            self._encoded = {
                "w": self.prior.w, "h": self.prior.h, "cell": self.prior.cell,
                "encoding": "zlib-base64", "dtype": "int8", "unit": "dBm",
                "predicted": True, "sources": sorted(sources),
                "data": base64.b64encode(zlib.compress(raw)).decode("ascii"),
            }
            self._key = key
        return deepcopy(self._encoded)
