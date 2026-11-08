"""STUB: the robot's `io` on real hardware, through ROS 2. Not run on a robot yet.

Same methods and return shapes as the simulator's RobotIO / RadioIO (server/deadzone/sim.py), so
`Robot.step(dt, io)` runs unchanged. Every TODO marks where a real topic or driver plugs in; see
hardware/README.md for the mapping. rclpy is imported lazily, so this file imports (and its
interface test runs) on machines without ROS 2.

    node = rclpy.create_node("deadzone_robot")
    io = Ros2RobotIO(node, robot_id="R1")
    robot = Robot("R1", "Scout 1", "#2dd4bf", pose, grid_shape, 0.25, entry)
    timer = node.create_timer(0.1, lambda: (io.spin_once(), robot.step(0.1, io), io.flush_outbox(robot)))
"""
import math

N_BEAMS = 72          # what the robot's mapping expects (server/deadzone/robot/lidar.py)
MAX_RANGE = 8.0       # m


class Ros2RadioIO:
    """Mesh radio. TODO: connect to the mesh (e.g. batman-adv or the radio vendor's API)."""

    def __init__(self, node, robot_id):
        self.node, self.robot_id = node, robot_id
        self.inbox = []          # decoded bundles for this robot, filled by the mesh listener
        self.routes = {}         # node id -> next hop, from the mesh routing table
        self.direct = []         # node ids in direct radio range

    def cmd_reachable(self):
        # TODO: refresh self.routes from the mesh; the command post node id is "CMD"
        return "CMD" in self.routes

    def neighbors(self):
        # TODO: refresh self.direct from the mesh neighbour list
        return list(self.direct)

    def receive(self):
        """Delivered messages, highest priority and oldest first (same order as the simulator)."""
        out = sorted(self.inbox, key=lambda b: (b["prio"], b["created"], b["bid"]))
        self.inbox.clear()
        return out


class Ros2RobotIO:
    """The only door between robot software and the world, on hardware."""

    def __init__(self, node, robot_id):
        self.node, self.robot_id = node, robot_id
        self.radio = Ros2RadioIO(node, robot_id)
        self._scan = None        # last sensor_msgs/LaserScan
        self._odom = None        # last nav_msgs/Odometry
        self._hot_spots = []     # last list of hot spots from the thermal pipeline
        self._cmd = None
        self._setup_ros()

    def _setup_ros(self):
        if self.node is None:   # interface tests construct the stub without ROS
            return
        from geometry_msgs.msg import Twist        # noqa: F401  (ROS 2 only)
        from nav_msgs.msg import Odometry
        from sensor_msgs.msg import LaserScan
        self._twist_type = Twist
        self.node.create_subscription(LaserScan, "/scan", lambda m: setattr(self, "_scan", m), 10)
        self.node.create_subscription(Odometry, "/odom", lambda m: setattr(self, "_odom", m), 10)
        self._cmd = self.node.create_publisher(Twist, "/cmd_vel", 10)
        # TODO: subscribe to the thermal camera (sensor_msgs/Image from the FLIR Lepton/PureThermal
        # or Boson driver) and run the hot-spot pipeline that fills self._hot_spots (see thermal()).

    @property
    def time(self):
        if self.node is None:
            return 0.0
        return self.node.get_clock().now().nanoseconds / 1e9

    def lidar(self):
        """(angles, ranges, hits), N_BEAMS beams, angles in the WORLD frame."""
        if self._scan is None:
            return [], [], []
        _, _, theta = self.odometry()["pose"]
        s = self._scan
        angles, ranges, hits = [], [], []
        for k in range(N_BEAMS):
            a_robot = -math.pi + 2 * math.pi * k / N_BEAMS
            i = round((a_robot - s.angle_min) / s.angle_increment)
            r = s.ranges[i] if 0 <= i < len(s.ranges) else float("inf")
            hit = math.isfinite(r) and r < min(s.range_max, MAX_RANGE)
            angles.append(theta + a_robot)          # world frame, as the robot's mapping expects
            ranges.append(r if hit else MAX_RANGE)
            hits.append(hit)
        return angles, ranges, hits

    def odometry(self):
        if self._odom is None:
            return {"pose": (0.0, 0.0, 0.0), "v": 0.0, "blocked": False, "wheel_current": 0.0}
        p, q = self._odom.pose.pose.position, self._odom.pose.pose.orientation
        theta = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        return {"pose": (p.x, p.y, theta), "v": self._odom.twist.twist.linear.x,
                "blocked": False,         # TODO: commanded speed but no motion for ~0.5 s
                "wheel_current": 0.0}     # TODO: motor driver current sense, in A

    def motor_current(self):
        return self.odometry()["wheel_current"]

    def drive(self, v, w):
        if self._cmd is None:
            return
        msg = self._twist_type()
        msg.linear.x, msg.angular.z = float(v), float(w)
        self._cmd.publish(msg)

    def drop_relay(self, beacon_for=None):
        # TODO: actuate the relay dropper, wait for the new node to join the mesh, return its id
        return None

    def thermal(self):
        """Hot spots in the forward camera view: [{"id", "pos": (x, y), "crop", "conf"}, ...].
        TODO: threshold warm blobs in the thermal image, project each to the floor with the camera
        pose, save a crop the detector can read, track ids across frames."""
        return list(self._hot_spots)

    # ---- glue around Robot.step, not part of the robot's io ----
    def spin_once(self):
        if self.node is not None:
            import rclpy
            rclpy.spin_once(self.node, timeout_sec=0.0)

    def flush_outbox(self, robot):
        """Send the robot's outgoing bundles over the mesh, keeping each until the next hop confirms.
        TODO: custody acknowledgements and retry, like server/deadzone/network/dtn.py."""
        robot.outbox.clear()
