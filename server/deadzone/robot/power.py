"""Battery and motor model (first pass, return-home logic lands at 6 PM)."""

CAPACITY_WH = 90.0
P_IDLE_W = 8.0
P_COMPUTE_W = 5.0
P_RADIO_W = 2.0
P_DRIVE_W_PER_MPS = 30.0
RESERVE_PCT = 20.0


class Battery:
    def __init__(self, wh=CAPACITY_WH):
        self.wh = wh

    @property
    def pct(self):
        return 100.0 * self.wh / CAPACITY_WH

    def drain(self, dt, v):
        p = P_IDLE_W + P_COMPUTE_W + P_RADIO_W + P_DRIVE_W_PER_MPS * abs(v)
        self.wh = max(0.0, self.wh - p * dt / 3600.0)

    @staticmethod
    def pct_to_drive(meters, v=0.8):
        """Battery percent needed to drive this far at cruise, with a 1.25 margin."""
        seconds = meters / max(v, 0.1)
        p = P_IDLE_W + P_COMPUTE_W + P_RADIO_W + P_DRIVE_W_PER_MPS * v
        return 100.0 * 1.25 * p * seconds / 3600.0 / CAPACITY_WH


def wheel_current(v, blocked):
    return 1.5 + 2.5 * abs(v) + (6.0 if blocked else 0.0)
