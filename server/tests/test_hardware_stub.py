"""hardware/ros2_bridge.py stays a drop-in `io`: the robot's io calls exist on the stub with the
simulator's names, and the stub imports without ROS 2."""
import ast
import importlib.util
import inspect
import re
from pathlib import Path

from deadzone.sim import RadioIO, RobotIO

ROOT = Path(__file__).resolve().parents[2]


def load_stub():
    spec = importlib.util.spec_from_file_location("ros2_bridge", ROOT / "hardware" / "ros2_bridge.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def public(cls):
    return {n for n, _ in inspect.getmembers(cls) if not n.startswith("_")}


def test_stub_has_every_io_call_the_robot_makes():
    stub = load_stub()
    robot_src = (ROOT / "server" / "deadzone" / "robot" / "robot.py").read_text(encoding="utf-8")
    calls = set(re.findall(r"\bio\.([a-z_]+)", robot_src)) - {"radio"}
    radio_calls = set(re.findall(r"\bio\.radio\.([a-z_]+)", robot_src))
    assert calls and radio_calls
    assert calls <= public(stub.Ros2RobotIO) and calls <= public(RobotIO)
    assert radio_calls <= public(stub.Ros2RadioIO) and radio_calls <= public(RadioIO)
    assert {"lidar", "odometry", "drive", "thermal", "drop_relay", "time"} <= public(stub.Ros2RobotIO)


def test_stub_works_without_ros_and_returns_the_simulators_shapes():
    stub = load_stub()
    io = stub.Ros2RobotIO(None, "R1")
    assert io.lidar() == ([], [], [])
    odo = io.odometry()
    assert set(odo) >= {"pose", "v", "blocked", "wheel_current"} and len(odo["pose"]) == 3
    assert io.thermal() == [] and io.drop_relay() is None
    assert io.radio.cmd_reachable() is False and io.radio.neighbors() == [] and io.radio.receive() == []
    tree = ast.parse((ROOT / "hardware" / "ros2_bridge.py").read_text(encoding="utf-8"))
    top_imports = {a.name.split(".")[0] for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))
                   for a in getattr(n, "names", [])} | {n.module.split(".")[0] for n in tree.body
                                                         if isinstance(n, ast.ImportFrom) and n.module}
    assert not top_imports & {"rclpy", "sensor_msgs", "nav_msgs", "geometry_msgs"}, "ROS imports stay lazy"
