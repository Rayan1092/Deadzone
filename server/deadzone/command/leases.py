"""Exclusive direct-command leases; timeouts use wall time, never sim ticks."""
import secrets
import time

from pydantic import Field, field_validator

from .plan import Identifier, Model, PlanError

TTL_S = 15.0


class RobotRef(Model):
    robot: Identifier


class LeaseClaim(RobotRef):
    name: str = Field(min_length=1, max_length=64, strict=True)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Controller name must not be blank")
        return value


class PresenterRelease(RobotRef):
    presenter_token: str = Field(min_length=1, max_length=256, strict=True)


class RobotGroup(Model):
    robots: list[Identifier] = Field(min_length=1, max_length=3)

    @field_validator("robots")
    @classmethod
    def distinct_robots(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Robot IDs must be distinct")
        return value


class LeaseGroupClaim(RobotGroup):
    name: str = Field(min_length=1, max_length=64, strict=True)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value):
        return LeaseClaim.trim_name(value)


class LeaseTable:
    """Mutate only on the Hub event loop, with no await between auth and enqueue."""

    def __init__(self, robots, *, clock=time.monotonic, wall=time.time):
        self.robots = tuple(robots)
        self.clock, self.wall = clock, wall
        self.controllers = {}
        self.leases = {}
        self.revision = 0

    def register(self, client):
        token = secrets.token_urlsafe(32)
        self.controllers[token] = client
        return token

    def actor(self, token):
        if not isinstance(token, str) or not token or token not in self.controllers:
            raise PlanError("invalid_controller", "Connect a controller WebSocket first", 403)
        return self.controllers[token]

    def robot(self, robot):
        if robot not in self.robots:
            raise PlanError("robot_not_found", f"Unknown robot: {robot}", 404)

    def expire(self):
        expired = [r for r, lease in self.leases.items() if lease["deadline"] <= self.clock()]
        for robot in expired:
            del self.leases[robot]
        if expired:
            self.revision += 1
        return bool(expired)

    def claim(self, robot, token, name):
        self.robot(robot)
        self.actor(token)
        self.expire()
        old = self.leases.get(robot)
        if old and old["token"] != token:
            raise PlanError("robot_controlled", f"{robot} is controlled by {old['name']}", 409)
        self.leases[robot] = {"token": token, "name": name, "deadline": self.clock() + TTL_S}
        self.revision += 1

    def require(self, robot, token):
        self.robot(robot)
        self.actor(token)
        lease = self.leases.get(robot)
        if not lease or lease["deadline"] <= self.clock() or lease["token"] != token:
            raise PlanError("lease_required", f"Take control of {robot} before sending a command", 403)

    def heartbeat(self, robot, token):
        self.require(robot, token)
        self.leases[robot]["deadline"] = self.clock() + TTL_S
        self.revision += 1

    def release(self, robot, token):
        self.robot(robot)
        self.actor(token)
        self.expire()
        if robot not in self.leases:
            return
        self.require(robot, token)
        del self.leases[robot]
        self.revision += 1

    def group(self, action, robots, token, name=None):
        """Preflight the whole group before changing any grant; no await here."""
        self.actor(token)
        for robot in robots:
            self.robot(robot)
        self.expire()
        if action == "claim":
            for robot in robots:
                old = self.leases.get(robot)
                if old and old["token"] != token:
                    raise PlanError("robot_controlled", f"{robot} is controlled by {old['name']}", 409)
            deadline = self.clock() + TTL_S
            self.leases.update({robot: {"token": token, "name": name, "deadline": deadline}
                                for robot in robots})
        elif action in ("heartbeat", "release"):
            for robot in robots:
                if action == "heartbeat" or robot in self.leases:
                    self.require(robot, token)
            if action == "heartbeat":
                deadline = self.clock() + TTL_S
                for robot in robots:
                    self.leases[robot]["deadline"] = deadline
            else:
                if not any(robot in self.leases for robot in robots):
                    return
                for robot in robots:
                    self.leases.pop(robot, None)
        else:
            raise ValueError("Unsupported lease group operation")
        self.revision += 1

    def override(self, robot):
        self.robot(robot)
        if self.leases.pop(robot, None) is not None:
            self.revision += 1

    def disconnect(self, token):
        self.controllers.pop(token, None)
        owned = [r for r, lease in self.leases.items() if lease["token"] == token]
        for robot in owned:
            del self.leases[robot]
        if owned:
            self.revision += 1
        return bool(owned)

    def reset(self):
        self.leases.clear()
        self.revision += 1

    def snapshot(self, enabled):
        now, wall = self.clock(), self.wall()
        robots = []
        for robot in self.robots:
            lease = self.leases.get(robot)
            live = enabled and lease and lease["deadline"] > now
            robots.append({"robot": robot,
                "controller": {"client": self.controllers[lease["token"]], "name": lease["name"]} if live else None,
                "expires_at": wall + lease["deadline"] - now if live else None})
        return {"enabled": enabled, "ttl_s": TTL_S, "revision": self.revision,
                "server_time": wall, "robots": robots}
