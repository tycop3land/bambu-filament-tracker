"""Constants for Bambu Filament Tracker."""

DOMAIN = "bambu_filament_tracker"
STORAGE_KEY = "bambu_filament_tracker"
STORAGE_VERSION = 1

SIGNAL_FILAMENT_UPDATE = f"{DOMAIN}_update"

CONF_ENTITY_PREFIX = "entity_prefix"
CONF_DEVICE_NAME = "device_name"
CONF_LOW_THRESHOLD_PCT = "low_threshold_pct"
CONF_DEFAULT_SPOOL_WEIGHT_G = "default_spool_weight_g"
CONF_TARGET_AMS = "target_ams"

DEFAULT_LOW_THRESHOLD_PCT = 10
DEFAULT_SPOOL_WEIGHT_G = 1000
DEFAULT_TARGET_AMS = 1

NUM_TRAYS = 4

PHASE_IDLE = "idle"
PHASE_PRINT_STARTING = "print_starting"
PHASE_PRINTING = "printing"
PHASE_INTERRUPTED = "interrupted"
PHASE_RECOVERING = "recovering"
PHASE_PRINT_COMPLETING = "print_completing"

SPOOL_STATUS_LOADED = "loaded"
SPOOL_STATUS_STORED = "stored"
SPOOL_STATUS_EMPTY = "empty"
SPOOL_STATUS_ARCHIVED = "archived"

PRINT_STATUS_COMPLETED = "completed"
PRINT_STATUS_FAILED = "failed"
PRINT_STATUS_CANCELLED = "cancelled"
PRINT_STATUS_UNTRACKED = "untracked"
