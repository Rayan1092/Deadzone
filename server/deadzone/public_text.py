"""Public display text. Machine fields, planner decisions and sensor data stay intact."""
import re


ERRORS = {
    "presenter_required": "Only the console operator can release this control lock.",
    "invalid_controller": "Reconnect before taking control of a robot.",
    "robot_not_found": "Choose a robot from the list.",
    "robot_controlled": "Another operator has control of this robot. Wait for them to release it.",
    "lease_required": "Take control of the robot before sending an instruction.",
    "lease_changed": "Control changed while the instruction was being prepared. Take control and try again.",
    "voice_reset": "The incident restarted. Reconnect and send the instruction again.",
    "request_conflict": "This instruction changed while it was being sent. Send it again as a new instruction.",
    "request_in_progress": "This instruction is still being prepared. Please wait before trying again.",
    "command_busy": "Another instruction is being prepared. Please wait and try again.",
    "ack_not_delivered": "The robot's answer has not reached the command post yet.",
    "speech_busy": "Another spoken answer is being prepared. Please try again shortly.",
    "plan_dispatched": "This plan has already been sent. Save your changes as a new plan.",
    "plan_not_found": "This plan is no longer available. Reopen the current plan and try again.",
    "plan_reset": "The incident restarted. Reconnect before editing the plan.",
    "invalid_plan": "Keep every search area and no-go area inside the building.",
    "invalid_request": "Some details are missing or invalid. Check your entries and try again.",
    "invalid_message": "The instruction could not be read. Reconnect and try again.",
    "invalid_json": "The update could not be read. Reconnect and try again.",
    "unsupported_message": "This action is unavailable on this screen.",
    "read_only_role": "Choose Plan the search to edit or send a plan.",
    "unknown_control": "This action is unavailable. Choose a control from the screen.",
    "invalid_mode": "Choose one search mode and try again.",
    "invalid_reset": "Choose a scenario before restarting the incident.",
    "invalid_speed": "Choose a speed greater than zero.",
    "invalid_director": "Choose an incident action from the screen.",
    "invalid_aftershock": "This aftershock is unavailable here right now. Try another location or wait for the current event to finish.",
    "floorplan_not_found": "Choose an available building from the scenario list.",
    "invalid_scenario": "This building or disaster schedule could not be loaded. Choose another scenario.",
    "unknown_room": "Choose a room from the list.",
    "outside_building": "Choose a point inside the building.",
    "intent_unavailable": "The spoken instruction could not be understood. Use the robot's buttons instead.",
    "stt_unavailable": "Speech could not be transcribed. Use the robot's buttons instead.",
    "unsupported_audio": "This recording format is unsupported. Record the instruction again.",
    "audio_too_large": "This recording is too long. Try a shorter instruction.",
    "empty_audio": "No audio was recorded. Please try again.",
    "sync_not_started": "Open a shared plan before sharing offline edits.",
    "sync_epoch": "The shared plan was replaced. Reopen it before applying your edits.",
    "sync_clock": "These edits conflict with an earlier update. Reopen the shared plan and try again.",
    "sync_limit": "This shared plan has too many edits. Save a new plan after all phones reconnect.",
    "plan_conflict": "Resolve the highlighted plan changes before checking or sending it.",
    "frame_epoch": "This camera image belongs to an earlier incident. Wait for a new image.",
    "frame_time": "This camera image is out of date. Wait for a new image.",
    "frame_rate": "Camera images are arriving too quickly. Wait a moment.",
    "frame_size": "This camera image is too large to share.",
    "invalid_frame": "This camera image could not be read. Share a smaller image and try again.",
    "frame_no_signal": "The robot is out of contact. A new camera image can be shared when it reconnects.",
    "report_reset": "The incident restarted while the answer was being prepared. Please ask again.",
    "relay_limit": "The maximum number of phone relays has been reached. Restart the incident to add more.",
    "relay_destroyed": "This relay is damaged. Restart the incident to restore it.",
}
FEATURES = {
    "DZ_CONTROL_LEASES": "Direct robot control is unavailable for this session.",
    "DZ_VOICE": "This instruction is unavailable for this session. Resume is still available.",
    "DZ_SCENARIO_TIMELINE": "Scheduled disasters are unavailable for this session.",
    "DZ_AFTERSHOCK": "Aftershocks are unavailable for this session.",
    "DZ_CRDT": "Offline plan sharing is unavailable for this session.",
    "DZ_RESCUE_ORDER": "Rescue priority guidance is unavailable for this session.",
}
DISPLAY = {"msg", "say", "text", "plan_state", "detector_reason"}
# These contain structured data or user input, never generated display messages.
OPAQUE = {"floorplan", "grid", "map", "maps", "grids", "camera", "phone_frame", "lidar",
          "pose", "path", "path_home", "path_preview", "tasks", "links", "transcript"}
TOKEN = re.compile(r"\b[A-Za-z0-9_]+(?:[.-][A-Za-z0-9_]+)*\b")


class PublicText:
    def __init__(self, robots, rooms=(), plans=None):
        self.robots = dict(robots)
        self.rooms = {r["id"]: r["name"] for r in rooms}
        self.plans = plans if plans is not None else {}

    def area(self, zone, plan_id=None):
        plan = self.plans.get(plan_id, {})
        for i, region in enumerate(plan.get("zones", []), 1):
            if region["id"] == zone:
                return f"Search area {i}"
        return self.rooms.get(zone, "The search area")

    def message(self, text, *, code=None, plan_id=None):
        if code == "feature_disabled":
            return next((message for flag, message in FEATURES.items() if flag in text),
                        "This feature is unavailable for this session.")
        if code in ERRORS:
            return ERRORS[code]
        text = text.removeprefix("Value error, ")
        if "DZ_PUBLIC_URL" in text:
            return "The phone link is unavailable. Ask the laptop operator to check the Wi-Fi or use a tunnel link."
        if "Build the frontend" in text:
            return "The app is not ready. Ask the laptop operator to finish setup."
        if text == "DETECTOR=sim":
            return "The simulated detector is selected."
        if re.search(r"DZ_|DETECTOR=|torch unavailable|model load failed|no model at", text):
            return "The trained detector is unavailable. Using the simulated detector."
        # Room IDs can overlap survivor IDs. Resolve them only in room-related prose.
        text = re.sub(r"(?i)(searching|exploring|room|heading to) ([A-Za-z0-9_.-]+)",
                      lambda m: f"{m[1]} {self.rooms.get(m[2].rstrip('.'), m[2])}" + ("." if m[2].endswith('.') else ""), text)
        names = dict(self.robots)
        plan = self.plans.get(plan_id, {})
        names.update({z["id"]: f"Search area {i}" for i, z in enumerate(plan.get("zones", []), 1)})
        names.update({z["id"]: f"No-go area {i}" for i, z in enumerate(plan.get("no_go", []), 1)})
        names.update({pid: "the plan" for pid in self.plans})
        text = TOKEN.sub(lambda m: names.get(m[0], m[0]), text)
        text = re.sub(r"\bS(\d+)\b", r"Survivor \1", text)
        text = re.sub(r"\b(?:R\d+|RL\d+|CMD|P-[\w.-]+)\b", "the robot" if code == "lease_required" else "the selected item", text)
        text = re.sub(r"\b(?:phone|judge)-[\w.-]+\b|\bPresenter\b", "another operator", text, flags=re.I)
        text = text.replace("lost_link_ok", "allowing signal loss").replace("robot telemetry", "robot reports").replace("telemetry", "robot reports")
        text = text.replace("SAFE_STOP", "safe stop").replace("OVERCURRENT", "motor overload").replace("LOW_BATTERY", "low battery")
        text = text.replace("STUCK", "stuck").replace("TRAPPED", "trapped").replace("historical faults", "past faults")
        text = text.replace("Request validation failed", "Check your entries and try again.")
        text = text.replace("Message must be valid JSON", "The update could not be read. Reconnect and try again.")
        if re.search(r"/api/|request_id|plan_id|WebSocket|\b(?:base64|KiB)\b", text):
            return "This action could not be completed. Reconnect and try again."
        text = text.replace("_", " ")
        return text[:1].upper() + text[1:]

    def safety_message(self, item, plan_id):
        area = self.area(item.get("zone"), plan_id)
        robot = self.robots.get(item.get("robot"), "The robot")
        rule, value, limit = item.get("rule"), item.get("value"), item.get("limit")
        if rule == "comms_plan":
            return f"{area} may lose radio contact. Add a relay route or allow signal loss for a limited time."
        if rule == "no_go_overlap":
            return f"{area} overlaps a no-go area. Move or resize it before sending the plan."
        if rule == "zone_unreachable":
            return f"A safe route to {area.lower()} and back home cannot be confirmed."
        if rule == "battery_reserve":
            if value is None:
                return f"Wait for a battery report from {robot} before sending this plan."
            return f"{robot} would return with {value}% battery. Keep at least {limit}% in reserve."
        if rule == "capability" and limit is None:
            return "The selected robot is not deployed. Choose another robot."
        return self.message(item["msg"], plan_id=plan_id)

    def payload(self, value, plan_id=None):
        # Numeric arrays, geometry and large image/map strings are never walked or copied.
        if isinstance(value, list):
            return [self.payload(v, plan_id) for v in value] if value and isinstance(value[0], dict) else value
        if not isinstance(value, dict):
            return value
        plan_id = value.get("plan_id", plan_id)
        result = {}
        for key, item in value.items():
            if key in OPAQUE:
                result[key] = item
            elif key == "say" and value.get("status") == "refused" and isinstance(value.get("safety"), dict):
                safety = self.payload(value["safety"], plan_id)
                result[key] = "This instruction was not sent. " + " ".join(v["msg"] for v in safety.get("violations", []))
            elif key == "msg" and "rule" in value and isinstance(item, str):
                result[key] = self.safety_message(value, plan_id)
            elif isinstance(item, str) and (key in DISPLAY or key == "detail"
                    or key == "reason" and value.get("kind") == "scenario_event_failed"):
                result[key] = self.message(item, code=value.get("code") if key == "msg" else None, plan_id=plan_id)
            else:
                result[key] = self.payload(item, plan_id)
        return result
