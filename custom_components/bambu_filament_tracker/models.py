"""Data models for Bambu Filament Tracker."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from .const import PHASE_IDLE, SPOOL_STATUS_LOADED


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid4())


@dataclass
class Spool:
    spool_id: str = field(default_factory=_new_id)
    color_hex: str = ""
    material_type: str = "PLA"
    name: str = ""
    brand: str = ""
    initial_weight_g: float = 1000.0
    remaining_weight_g: float = 1000.0
    status: str = SPOOL_STATUS_LOADED
    tray_index: int | None = None
    tag_uid: str | None = None
    created_at: str = field(default_factory=_utcnow_iso)
    updated_at: str = field(default_factory=_utcnow_iso)
    total_consumed_g: float = 0.0
    print_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "spool_id": self.spool_id,
            "color_hex": self.color_hex,
            "material_type": self.material_type,
            "name": self.name,
            "brand": self.brand,
            "initial_weight_g": self.initial_weight_g,
            "remaining_weight_g": self.remaining_weight_g,
            "status": self.status,
            "tray_index": self.tray_index,
            "tag_uid": self.tag_uid,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "total_consumed_g": self.total_consumed_g,
            "print_ids": list(self.print_ids),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Spool:
        return cls(
            spool_id=data.get("spool_id", _new_id()),
            color_hex=data.get("color_hex", ""),
            material_type=data.get("material_type", "PLA"),
            name=data.get("name", ""),
            brand=data.get("brand", ""),
            initial_weight_g=data.get("initial_weight_g", 1000.0),
            remaining_weight_g=data.get("remaining_weight_g", 1000.0),
            status=data.get("status", SPOOL_STATUS_LOADED),
            tray_index=data.get("tray_index"),
            tag_uid=data.get("tag_uid"),
            created_at=data.get("created_at", _utcnow_iso()),
            updated_at=data.get("updated_at", _utcnow_iso()),
            total_consumed_g=data.get("total_consumed_g", 0.0),
            print_ids=list(data.get("print_ids", [])),
        )


@dataclass
class PrintRecord:
    record_id: str = field(default_factory=_new_id)
    timestamp: str = field(default_factory=_utcnow_iso)
    gcode_file: str = ""
    status: str = "completed"
    print_percentage: int = 100
    total_weight_g: float = 0.0
    tray_usage: dict[int, float] = field(default_factory=dict)
    duration_seconds: int | None = None

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "timestamp": self.timestamp,
            "gcode_file": self.gcode_file,
            "status": self.status,
            "print_percentage": self.print_percentage,
            "total_weight_g": self.total_weight_g,
            "tray_usage": {str(k): v for k, v in self.tray_usage.items()},
            "duration_seconds": self.duration_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PrintRecord:
        return cls(
            record_id=data.get("record_id", _new_id()),
            timestamp=data.get("timestamp", _utcnow_iso()),
            gcode_file=data.get("gcode_file", ""),
            status=data.get("status", "completed"),
            print_percentage=data.get("print_percentage", 100),
            total_weight_g=data.get("total_weight_g", 0.0),
            tray_usage={int(k): v for k, v in data.get("tray_usage", {}).items()},
            duration_seconds=data.get("duration_seconds"),
        )


@dataclass
class TrackerState:
    phase: str = PHASE_IDLE
    print_start_time: str | None = None
    gcode_file: str | None = None
    print_percentage: int = 0
    pre_print_remaining: dict[int, float] = field(default_factory=dict)
    last_print_weight: float = 0.0

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "print_start_time": self.print_start_time,
            "gcode_file": self.gcode_file,
            "print_percentage": self.print_percentage,
            "pre_print_remaining": {str(k): v for k, v in self.pre_print_remaining.items()},
            "last_print_weight": self.last_print_weight,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TrackerState:
        return cls(
            phase=data.get("phase", PHASE_IDLE),
            print_start_time=data.get("print_start_time"),
            gcode_file=data.get("gcode_file"),
            print_percentage=data.get("print_percentage", 0),
            pre_print_remaining={int(k): v for k, v in data.get("pre_print_remaining", {}).items()},
            last_print_weight=data.get("last_print_weight", 0.0),
        )

    def reset(self) -> None:
        self.phase = PHASE_IDLE
        self.print_start_time = None
        self.gcode_file = None
        self.print_percentage = 0
        self.pre_print_remaining = {}
        self.last_print_weight = 0.0
