import json
import os
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class RecoveryState:
    """Recovery state information"""
    current_date: str
    processed_days: int
    total_days: int
    last_completed_operation: str
    timestamp: str
    config_hash: str
    travel_from: str
    travel_to: str
    round_trip_enabled: bool


class RecoveryManager:
    """Manages recovery state for timeout restarts"""

    def __init__(self, recovery_file: str = ".scraper_recovery_state.json"):
        self.recovery_file = recovery_file
        self.config_hash = None

    def _calculate_config_hash(self, config: Dict[str, Any]) -> str:
        """Calculate hash of configuration to detect changes"""
        # Only include configuration that affects scraping behavior
        relevant_config = {
            'TRAVEL_FROM': config.get('TRAVEL_FROM'),
            'TRAVEL_TO': config.get('TRAVEL_TO'),
            'TRAVEL_DAYS': config.get('TRAVEL_DAYS'),
            'TRAVEL_START_DATE': config.get('TRAVEL_START_DATE'),
            'ROUND_TRIP_ENABLED': config.get('ROUND_TRIP_ENABLED'),
            'TRAVEL_RENFE_PRICE_CHANGE_NOTIFICATION': config.get('TRAVEL_RENFE_PRICE_CHANGE_NOTIFICATION')
        }

        config_str = json.dumps(relevant_config, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()

    def save_state(self, state: RecoveryState) -> None:
        """Save the current recovery state"""
        try:
            state_dict = {
                'current_date': state.current_date,
                'processed_days': state.processed_days,
                'total_days': state.total_days,
                'last_completed_operation': state.last_completed_operation,
                'timestamp': state.timestamp,
                'config_hash': state.config_hash,
                'travel_from': state.travel_from,
                'travel_to': state.travel_to,
                'round_trip_enabled': state.round_trip_enabled
            }

            with open(self.recovery_file, 'w') as f:
                json.dump(state_dict, f, indent=2)

        except Exception as e:
            # Don't fail the main process if recovery save fails
            print(f"⚠️ Warning: Could not save recovery state: {e}")

    def load_state(self) -> Optional[RecoveryState]:
        """Load the recovery state if it exists"""
        try:
            if not os.path.exists(self.recovery_file):
                return None

            with open(self.recovery_file, 'r') as f:
                data = json.load(f)

            return RecoveryState(
                current_date=data['current_date'],
                processed_days=data['processed_days'],
                total_days=data['total_days'],
                last_completed_operation=data['last_completed_operation'],
                timestamp=data['timestamp'],
                config_hash=data['config_hash'],
                travel_from=data['travel_from'],
                travel_to=data['travel_to'],
                round_trip_enabled=data['round_trip_enabled']
            )

        except Exception as e:
            print(f"⚠️ Warning: Could not load recovery state: {e}")
            return None

    def should_recover(self, current_config: Dict[str, Any]) -> tuple[bool, Optional[RecoveryState]]:
        """
        Determine if we should recover from a previous state

        Returns:
            (should_recover: bool, recovery_state: Optional[RecoveryState])
        """
        recovery_state = self.load_state()

        if not recovery_state:
            return False, None

        # Calculate current config hash
        current_hash = self._calculate_config_hash(current_config)

        # If configuration changed, don't recover (start fresh)
        if recovery_state.config_hash != current_hash:
            print("🔄 Configuration changed - starting fresh (not recovering)")
            self.clear_state()
            return False, None

        # Check if the recovery state is recent (within last hour)
        try:
            state_time = datetime.fromisoformat(recovery_state.timestamp)
            now = datetime.now()
            time_diff = (now - state_time).total_seconds()

            # If state is older than 1 hour, assume it's stale
            if time_diff > 3600:  # 1 hour
                print(f"⏰ Recovery state is too old ({time_diff/60:.1f} minutes) - starting fresh")
                self.clear_state()
                return False, None

        except Exception as e:
            print(f"⚠️ Could not parse recovery timestamp: {e}")
            return False, None

        return True, recovery_state

    def clear_state(self) -> None:
        """Clear the recovery state file"""
        try:
            if os.path.exists(self.recovery_file):
                os.remove(self.recovery_file)
        except Exception as e:
            print(f"⚠️ Warning: Could not clear recovery state: {e}")

    def update_config_hash(self, config: Dict[str, Any]) -> None:
        """Update the stored config hash"""
        self.config_hash = self._calculate_config_hash(config)


def create_recovery_config(travel_from: str, travel_to: str, travel_days: int,
                          travel_start_date: Optional[str], round_trip_enabled: bool,
                          renfe_price_change_notification: bool) -> Dict[str, Any]:
    """Create configuration dict for recovery system"""
    return {
        'TRAVEL_FROM': travel_from,
        'TRAVEL_TO': travel_to,
        'TRAVEL_DAYS': travel_days,
        'TRAVEL_START_DATE': travel_start_date,
        'ROUND_TRIP_ENABLED': round_trip_enabled,
        'TRAVEL_RENFE_PRICE_CHANGE_NOTIFICATION': renfe_price_change_notification
    }
