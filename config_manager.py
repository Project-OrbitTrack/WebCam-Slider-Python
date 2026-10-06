import yaml
import sys
from pathlib import Path

class ConfigManager:
    DEFAULTS = {
        'camera': {'index': 0, 'width': 320, 'height': 240},
        'window': {'width': 1280, 'height': 720, 'fullscreen': False},
        'wave_detection': {'sensitivity': 5, 'frame_rate_ms': 45},
        'wave_animation': {'phase_speed': 0.02, 'boost_increase': 0.15, 'boost_decay': 0.94},
        'colors': {
            'deep': [58, 42, 11],
            'ink': [31, 22, 6],
            'sand': [166, 217, 242]
        }
    }
    
    def __init__(self, config_path='config.yaml'):
        self.config_path = Path(config_path)
        self.config = self.load()
    
    def load(self):
        """Load config from YAML, fall back to defaults if missing."""
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    user_config = yaml.safe_load(f) or {}
                return self._merge_defaults(user_config)
            except Exception as e:
                print(f"Error reading {self.config_path}: {e}")
                print("Using defaults.")
                return self.DEFAULTS.copy()
        else:
            self._write_defaults()
            return self.DEFAULTS.copy()
    
    def _merge_defaults(self, user_config):
        """Recursively merge user config with defaults."""
        result = self.DEFAULTS.copy()
        for key, value in user_config.items():
            if isinstance(value, dict) and key in result:
                result[key].update(value)
            else:
                result[key] = value
        return result
    
    def _write_defaults(self):
        """Write default config to file."""
        with open(self.config_path, 'w') as f:
            yaml.dump(self.DEFAULTS, f, default_flow_style=False)
        print(f"Created {self.config_path} with defaults.")
    
    def get(self, *keys):
        """Get nested value: config.get('camera', 'index')"""
        val = self.config
        for key in keys:
            if isinstance(val, dict):
                val = val.get(key)
            else:
                return None
        return val
    
    def validate(self):
        """Check settings are in valid ranges."""
        sens = self.get('wave_detection', 'sensitivity')
        if not isinstance(sens, int) or not (1 <= sens <= 10):
            print(f"Warning: sensitivity {sens} not in 1-10, using default 5")
            self.config['wave_detection']['sensitivity'] = 5
