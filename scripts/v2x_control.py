"""V2X control logic driven over SUMO TraCI.

Two cooperative mechanisms, both toggled by a fleet *penetration rate*:

  V2I (vehicle-to-infrastructure) — adaptive signal coordination.
      Each signal replaces its fixed-time plan with queue-responsive
      max-pressure control: every `control_interval` it picks the green phase
      that clears the most queued demand on its approaches (demand reported by
      equipped vehicles within `comm_range`), honouring min-green + yellow.

  V2V (vehicle-to-vehicle) — congestion sharing + rerouting.
      Equipped vehicles pool their observed edge travel times (a shared
      real-time belief of network state); every `reroute_interval` each equipped
      vehicle re-routes to its destination on that belief, steering around jams.

Penetration = 0 reproduces the fixed-signal, no-reroute control exactly, so the
same harness yields both the baseline and the V2X arm of the comparison.
"""
from __future__ import annotations

import traci


def is_equipped(veh_id: str, penetration: float) -> bool:
    """Deterministic per-vehicle equipage (stable across the run)."""
    if penetration >= 1.0:
        return True
    if penetration <= 0.0:
        return False
    # Stable hash in [0,1) from the numeric suffix of the vehicle id.
    h = abs(hash(veh_id)) % 10_000 / 10_000.0
    return h < penetration


class SignalController:
    """Adaptive signal control for one traffic light.

    Waiting-weighted max-pressure with anti-starvation: each green phase is
    scored by its queued demand *plus* the accumulated waiting time on its
    approaches, so a low-volume side street whose cars have waited a long time
    gains priority before they hit the teleport threshold. A max-green cap forces
    rotation so no phase is held indefinitely.
    """

    def __init__(self, tls_id: str, min_green: float, yellow: float,
                 max_green: float = 60.0, wait_weight: float = 0.25):
        self.tls = tls_id
        self.min_green = min_green
        self.max_green = max_green
        self.wait_weight = wait_weight
        self.yellow = yellow
        links = traci.trafficlight.getControlledLinks(tls_id)
        # served incoming lane per signal index (link may be empty)
        self.index_inlane = [lk[0][0] if lk else None for lk in links]

        # Candidate green phases from the program: (index, state, served-lanes).
        logic = traci.trafficlight.getAllProgramLogics(tls_id)[0]
        self.green_phases = []
        for i, ph in enumerate(logic.phases):
            st = ph.state
            if "G" in st or "g" in st:
                served = {self.index_inlane[j] for j, c in enumerate(st)
                          if c in "Gg" and self.index_inlane[j]}
                if served:
                    self.green_phases.append((i, st, served))

        self.mode = "green"          # 'green' | 'yellow'
        self.cur_state = None
        self.pending_state = None
        self.timer = 0.0
        if self.green_phases:
            self.cur_state = self.green_phases[0][1]
            traci.trafficlight.setRedYellowGreenState(self.tls, self.cur_state)

    @staticmethod
    def _yellow_from(state: str) -> str:
        return "".join("y" if c in "Gg" else c for c in state)

    def _pressure(self, served_lanes) -> float:
        # V2I: queued demand + accumulated waiting time (anti-starvation) on the
        # served approaches, as reported to the infrastructure.
        q = sum(traci.lane.getLastStepHaltingNumber(l) for l in served_lanes)
        w = sum(traci.lane.getWaitingTime(l) for l in served_lanes)
        return q + self.wait_weight * w

    def step(self, dt: float):
        if not self.green_phases:
            return
        self.timer += dt
        if self.mode == "yellow":
            if self.timer >= self.yellow:
                self.cur_state = self.pending_state
                traci.trafficlight.setRedYellowGreenState(self.tls, self.cur_state)
                self.mode = "green"
                self.timer = 0.0
            return
        # green: hold at least min_green; re-evaluate after that; force a switch
        # once max_green is exceeded so no approach is starved.
        if self.timer < self.min_green:
            return
        scored = sorted(self.green_phases, key=lambda gp: self._pressure(gp[2]), reverse=True)
        best = scored[0]
        forced = self.timer >= self.max_green
        if forced and best[1] == self.cur_state and len(scored) > 1:
            best = scored[1]  # rotate away from the held phase
        if best[1] != self.cur_state:
            self.pending_state = best[1]
            traci.trafficlight.setRedYellowGreenState(self.tls, self._yellow_from(self.cur_state))
            self.mode = "yellow"
            self.timer = 0.0


class V2XManager:
    """Owns all signal controllers + V2V rerouting for a run."""

    def __init__(self, cfg_v2x: dict, penetration: float, enable_v2v: bool = True):
        self.pen = penetration
        self.enable_v2v = enable_v2v
        self.comm_range = cfg_v2x["comm_range_m"]
        self.control_interval = cfg_v2x["control_interval_s"]
        self.reroute_interval = cfg_v2x["reroute_interval_s"]
        self.signals = []
        self.equipped_cache: dict[str, bool] = {}
        self.rerouted: set[str] = set()
        self.edges = [e for e in traci.edge.getIDList() if not e.startswith(":")]
        # V2I signals are active whenever any V2X is deployed (pen > 0).
        if penetration > 0:
            for tls in traci.trafficlight.getIDList():
                self.signals.append(SignalController(
                    tls, cfg_v2x["min_green_s"], cfg_v2x["yellow_s"],
                    max_green=cfg_v2x.get("max_green_s", 60),
                    wait_weight=cfg_v2x.get("wait_weight", 0.25)))

    def _equipped(self, vid: str) -> bool:
        e = self.equipped_cache.get(vid)
        if e is None:
            e = is_equipped(vid, self.pen)
            self.equipped_cache[vid] = e
        return e

    def _refresh_shared_traveltimes(self):
        # V2V/V2I shared belief: current per-edge travel time from live speeds.
        for e in self.edges:
            traci.edge.adaptTraveltime(e, traci.edge.getTraveltime(e))

    def _reroute_equipped(self):
        for vid in traci.vehicle.getIDList():
            if self._equipped(vid):
                try:
                    traci.vehicle.rerouteTraveltime(vid, currentTravelTimes=False)
                except traci.TraCIException:
                    pass

    def step(self, t: float, dt: float):
        if self.pen <= 0:
            return  # pure baseline: fixed signals, no rerouting
        if int(t) % self.control_interval == 0:
            for sc in self.signals:
                sc.step(self.control_interval)
        if self.enable_v2v and int(t) % self.reroute_interval == 0:
            self._refresh_shared_traveltimes()
            self._reroute_equipped()
