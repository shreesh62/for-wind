"""Training controller for learning login flows and authentication patterns.

This module allows Jarvis to LEARN login flows instead of hardcoding them.
Credentials are stored securely in the encrypted vault.
"""

from __future__ import annotations

import getpass
import time
from typing import Optional

from security.credential_vault import get_vault
from automation.ui_pattern_memory import get_ui_pattern_memory


class TrainingController:
    """Manages training sessions for learning authentication flows."""
    
    def __init__(self, awareness_state=None):
        """Initialize training controller.
        
        Args:
            awareness_state: StateCache for capturing WorldState snapshots
        """
        self.awareness_state = awareness_state
        self.vault = get_vault()
        self.ui_memory = get_ui_pattern_memory()
    
    def train_taskbar_chrome(self) -> str:
        """Train Chrome taskbar icon using visual anchoring.
        
        Replaced train_chrome_login with taskbar-anchored visual system.
        
        Returns:
            Status message
        """
        from automation.taskbar_trainer import train_taskbar_chrome
        return train_taskbar_chrome()
    
    def train_chrome_login(self) -> str:
        """OBSOLETE: Replaced by train_taskbar_chrome.
        
        Returns:
            Status message
        """
        print("\n" + "="*60)
        print("TRAINING: Chrome Profile Login")
        print("="*60)
        
        # 2️⃣ BLOCK TRAINING IF PERCEPTION NOT LIVE
        if not self.awareness_state:
            print("\n❌ CRITICAL: No awareness system available.")
            print("Training requires live perception to capture UI patterns.")
            return "Training failed: Awareness system not initialized"
        
        try:
            snapshot = self.awareness_state.get_snapshot()
            if not snapshot or not snapshot.get("active_window"):
                print("\n⚠️ No live perception detected.")
                print("Please ensure:")
                print("  1. Jarvis awareness system is running")
                print("  2. You have a window open (Chrome, WhatsApp, etc.)")
                print("  3. UI Automation is working")
                return "Training failed: No live perception"
        except Exception as e:
            print(f"\n❌ Cannot access perception: {e}")
            return "Training failed: Perception unavailable"
        
        from core.focus_watcher import FocusWatcher
        from awareness.perception_snapshot import PerceptionSnapshot
        import time
        
        watcher = FocusWatcher(self.awareness_state)
        
        # PASSIVE FLOW: Wait for Chrome to appear
        print("\n" + "-"*60)
        print("STEP 1: Passive Detection")
        print("-"*60)
        print("\nOpen Chrome and navigate to the profile selection screen.")
        print("Jarvis will detect Chrome automatically.")
        print("")
        
        try:
            print("Waiting for Chrome to appear...")
            watcher.wait_for_window("chrome.exe", timeout=30.0)
            print("✓ Chrome detected")
            
            time.sleep(0.5)
            before_snapshot = watcher.get_current_snapshot()
            
            if not before_snapshot:
                raise RuntimeError("❌ Cannot capture before snapshot")
            
            print(f"✓ Profile screen captured (hash: {before_snapshot.screen_hash[:8]}...)")
            
        except RuntimeError as e:
            print(f"\n❌ {e}")
            return "Training aborted: Chrome not detected"
        
        # Step 1: Get profile name
        print("\n" + "-"*60)
        print("STEP 2: Enter Credentials")
        print("-"*60)
        profile_name = input("\nEnter Chrome profile name (or press Enter for 'Default'): ").strip()
        if not profile_name:
            profile_name = "Default"
        
        # Step 2: Get password securely (no echo)
        print("\nEnter password (input will be hidden):")
        password = getpass.getpass("Password: ")
        
        if not password:
            return "Training cancelled: No password provided"
        
        # Step 3: Store in vault
        vault_key = f"chrome_profile_{profile_name}"
        self.vault.set(vault_key, password)
        print(f"\n✓ Credential stored in encrypted vault")
        
        # 3️⃣ & 5️⃣ CAPTURE UI PATTERNS DURING TRAINING
        print("\n" + "-"*60)
        print("STEP 3: Capture Visual Login Flow")
        print("-"*60)
        
        try:
            world = self.awareness_state.build_world_state()
            from awareness.perception_snapshot import PerceptionSnapshot
            snapshot = PerceptionSnapshot.from_world_state(world)
            
            # 5️⃣ PERSIST INTO UI_MEMORY.JSON
            import json
            from pathlib import Path
            
            memory_file = Path("memory/ui_memory.json")
            if memory_file.exists():
                with open(memory_file, 'r') as f:
                    memory_data = json.load(f)
            else:
                memory_data = {"version": "1.0", "patterns": [], "repairs": []}
            
            if "login_flows" not in memory_data:
                memory_data["login_flows"] = []
            
            # Store complete login flow
            login_flow = {
                "service": "chrome",
                "profile": profile_name,
                "snapshot": snapshot.to_dict(),
                "vault_key": vault_key,
                "verification": ["url_changed", "element_visible"],
                "timestamp": snapshot.timestamp,
                "screen_hash": snapshot.screen_hash,
            }
            
            memory_data["login_flows"].append(login_flow)
            
            with open(memory_file, 'w') as f:
                json.dump(memory_data, f, indent=2)
            
            print(f"\n✓ Perception snapshot captured")
            print(f"  Active window: {snapshot.active_window_title}")
            print(f"  Elements detected: {len(snapshot.elements)}")
            print(f"  Screen hash: {snapshot.screen_hash}")
            print(f"\n✓ Visual login flow recorded")
            print(f"  Service: chrome")
            print(f"  Profile: {profile_name}")
            print(f"  Vault key: {vault_key}")
            print(f"\n✓ Credential bound to UI memory")
            
            # 6️⃣ VERIFICATION: Wait for login to complete
            print("\n" + "-"*60)
            print("STEP 4: Verify Training")
            print("-"*60)
            print("\nNow type the password in Chrome and log in.")
            print("Jarvis will detect the login automatically.")
            print("")
            
            try:
                print("Waiting for login...")
                watcher.wait_for_screen_change(snapshot.screen_hash, timeout=30.0)
                print("✓ Login detected")
                
                time.sleep(0.5)
                after_snapshot = watcher.get_current_snapshot()
                
                if not after_snapshot:
                    raise RuntimeError("❌ Cannot capture after snapshot")
                
                print(f"✓ Logged in screen captured (hash: {after_snapshot.screen_hash[:8]}...)")
                print(f"\n✅ Training verified successfully")
                
            except RuntimeError as e:
                print(f"\n❌ {e}")
                return f"Training completed with warnings for profile: {profile_name}"
            
        except Exception as e:
            print(f"\n❌ CRITICAL: Could not capture UI snapshot: {e}")
            print(f"  Password stored in vault, but UI pattern NOT saved")
            print(f"  This will prevent auto-login from working.")
            return f"Training incomplete: UI pattern not captured ({e})"
        
        return "OBSOLETE: Use 'train taskbar_chrome' instead"
    
    def train_chrome_extension_unlock(self) -> str:
        """OBSOLETE: Replaced by train_taskbar_chrome.
        
        Uses passive focus detection - NO terminal interaction required.
        
        Returns:
            Status message
        """
        print("\n" + "="*60)
        print("TRAINING: Chrome Extension Unlock")
        print("="*60)
        
        if not self.awareness_state:
            print("\n❌ CRITICAL: No awareness system available.")
            return "Training failed: Awareness system not initialized"
        
        from core.focus_watcher import FocusWatcher
        from awareness.perception_snapshot import PerceptionSnapshot
        import time
        
        watcher = FocusWatcher(self.awareness_state)
        
        # Get password first (only terminal interaction)
        print("\n" + "-"*60)
        print("STEP 1: Enter Password")
        print("-"*60)
        password = getpass.getpass("\nEnter Chrome extension password: ")
        
        if not password:
            return "Training cancelled: No password provided"
        
        # Store in vault
        vault_key = "chrome_extension_lock"
        self.vault.set(vault_key, password)
        print(f"\n✓ Credential stored in encrypted vault")
        
        # PASSIVE FLOW: Wait for Chrome to appear
        print("\n" + "-"*60)
        print("STEP 2: Passive Detection")
        print("-"*60)
        print("\nOpen Chrome and unlock it normally.")
        print("Jarvis will detect the unlock automatically.")
        print("")
        
        try:
            # Wait for Chrome to be focused
            print("Waiting for Chrome to appear...")
            watcher.wait_for_window("chrome.exe", timeout=30.0)
            print("✓ Chrome detected")
            
            # Capture BEFORE snapshot
            time.sleep(0.5)
            before_snapshot = watcher.get_current_snapshot()
            
            if not before_snapshot:
                raise RuntimeError("❌ Cannot capture before snapshot")
            
            print(f"✓ Lock screen captured (hash: {before_snapshot.screen_hash[:8]}...)")
            
        except RuntimeError as e:
            print(f"\n❌ {e}")
            return "Training aborted: Chrome not detected"
        
        # Wait for screen to change (unlock happens)
        try:
            print("\nWaiting for unlock...")
            watcher.wait_for_screen_change(before_snapshot.screen_hash, timeout=15.0)
            print("✓ Unlock detected")
            
            # Capture AFTER snapshot
            time.sleep(0.5)
            after_snapshot = watcher.get_current_snapshot()
            
            if not after_snapshot:
                raise RuntimeError("❌ Cannot capture after snapshot")
            
            print(f"✓ Unlocked screen captured (hash: {after_snapshot.screen_hash[:8]}...)")
            
        except RuntimeError as e:
            print(f"\n❌ {e}")
            return "Training aborted: Unlock not detected"
        
        # Save to UI memory
        try:
            import json
            from pathlib import Path
            
            memory_file = Path("memory/ui_memory.json")
            if memory_file.exists():
                with open(memory_file, 'r') as f:
                    memory_data = json.load(f)
            else:
                memory_data = {"version": "1.0", "patterns": [], "repairs": []}
            
            if "login_flows" not in memory_data:
                memory_data["login_flows"] = []
            
            login_flow = {
                "service": "chrome",
                "unlock_type": "passive_extension",
                "snapshot_before": before_snapshot.to_dict(),
                "snapshot_after": after_snapshot.to_dict(),
                "vault_key": vault_key,
                "verification": ["screen_changed"],
                "timestamp": after_snapshot.timestamp,
            }
            
            memory_data["login_flows"].append(login_flow)
            
            with open(memory_file, 'w') as f:
                json.dump(memory_data, f, indent=2)
            
            print(f"\n✓ Visual pattern captured")
            print(f"✓ Credential bound to UI memory")
            print(f"\n✅ Training complete")
            
        except Exception as e:
            print(f"\n❌ Failed to save: {e}")
            return f"Training incomplete: {e}"
        
        return "OBSOLETE: Use 'train taskbar_chrome' instead"
    
    def train_whatsapp_unlock(self) -> str:
        """Train WhatsApp unlock flow.
        
        Returns:
            Status message
        """
        print("\n" + "="*60)
        print("TRAINING: WhatsApp Unlock")
        print("="*60)
        
        # 2️⃣ BLOCK TRAINING IF PERCEPTION NOT LIVE
        if not self.awareness_state:
            print("\n❌ CRITICAL: No awareness system available.")
            return "Training failed: Awareness system not initialized"
        
        try:
            snapshot = self.awareness_state.get_snapshot()
            if not snapshot or not snapshot.get("active_window"):
                print("\n⚠️ No live perception detected.")
                return "Training failed: No live perception"
        except Exception as e:
            print(f"\n❌ Cannot access perception: {e}")
            return "Training failed: Perception unavailable"
        
        from core.focus_watcher import FocusWatcher
        from awareness.perception_snapshot import PerceptionSnapshot
        import time
        
        watcher = FocusWatcher(self.awareness_state)
        
        # PASSIVE FLOW: Wait for WhatsApp to appear
        print("\n" + "-"*60)
        print("STEP 1: Passive Detection")
        print("-"*60)
        print("\nOpen WhatsApp and navigate to the unlock screen.")
        print("Jarvis will detect WhatsApp automatically.")
        print("")
        
        try:
            print("Waiting for WhatsApp to appear...")
            watcher.wait_for_window("whatsapp", timeout=30.0)
            print("✓ WhatsApp detected")
            
            time.sleep(0.5)
            before_snapshot = watcher.get_current_snapshot()
            
            if not before_snapshot:
                raise RuntimeError("❌ Cannot capture before snapshot")
            
            print(f"✓ Unlock screen captured (hash: {before_snapshot.screen_hash[:8]}...)")
            
        except RuntimeError as e:
            print(f"\n❌ {e}")
            return "Training aborted: WhatsApp not detected"
        
        # Step 1: Get unlock method
        print("\n" + "-"*60)
        print("STEP 2: Select Unlock Method")
        print("-"*60)
        print("\nWhatsApp unlock method:")
        print("  1. PIN")
        print("  2. Password")
        print("  3. Biometric (fingerprint/face)")
        
        method = input("\nSelect method (1-3): ").strip()
        
        if method == "3":
            print("\nBiometric unlock cannot be automated.")
            return "Training cancelled: Biometric unlock not supported"
        
        unlock_type = "pin" if method == "1" else "password"
        
        # Step 2: Get credential securely
        print(f"\nEnter WhatsApp {unlock_type} (input will be hidden):")
        credential = getpass.getpass(f"{unlock_type.upper()}: ")
        
        if not credential:
            return f"Training cancelled: No {unlock_type} provided"
        
        # Step 3: Store in vault
        vault_key = f"whatsapp_{unlock_type}"
        self.vault.set(vault_key, credential)
        print(f"\n✓ Credential stored in encrypted vault")
        
        # 3️⃣ & 5️⃣ CAPTURE UI PATTERNS
        print("\n" + "-"*60)
        print("STEP 3: Capture Visual Unlock Flow")
        print("-"*60)
        
        try:
            world = self.awareness_state.build_world_state()
            from awareness.perception_snapshot import PerceptionSnapshot
            snapshot = PerceptionSnapshot.from_world_state(world)
            
            # 5️⃣ PERSIST INTO UI_MEMORY.JSON
            import json
            from pathlib import Path
            
            memory_file = Path("memory/ui_memory.json")
            if memory_file.exists():
                with open(memory_file, 'r') as f:
                    memory_data = json.load(f)
            else:
                memory_data = {"version": "1.0", "patterns": [], "repairs": []}
            
            if "login_flows" not in memory_data:
                memory_data["login_flows"] = []
            
            login_flow = {
                "service": "whatsapp",
                "unlock_type": unlock_type,
                "snapshot": snapshot.to_dict(),
                "vault_key": vault_key,
                "verification": ["state_changed", "unlock_screen_gone"],
                "timestamp": snapshot.timestamp,
                "screen_hash": snapshot.screen_hash,
            }
            
            memory_data["login_flows"].append(login_flow)
            
            with open(memory_file, 'w') as f:
                json.dump(memory_data, f, indent=2)
            
            print(f"\n✓ Perception snapshot captured")
            print(f"  Active window: {snapshot.active_window_title}")
            print(f"  Elements detected: {len(snapshot.elements)}")
            print(f"\n✓ Visual unlock flow recorded")
            print(f"\n✓ Credential bound to UI memory")
            
            # 6️⃣ VERIFICATION: Wait for unlock to complete
            print("\n" + "-"*60)
            print("STEP 4: Verify Training")
            print("-"*60)
            print(f"\nNow enter the {unlock_type} in WhatsApp.")
            print("Jarvis will detect the unlock automatically.")
            print("")
            
            try:
                print("Waiting for unlock...")
                watcher.wait_for_screen_change(snapshot.screen_hash, timeout=30.0)
                print("✓ Unlock detected")
                
                time.sleep(0.5)
                after_snapshot = watcher.get_current_snapshot()
                
                if not after_snapshot:
                    raise RuntimeError("❌ Cannot capture after snapshot")
                
                print(f"✓ Unlocked screen captured (hash: {after_snapshot.screen_hash[:8]}...)")
                print(f"\n✅ Training verified successfully")
                
            except RuntimeError as e:
                print(f"\n❌ {e}")
                return f"Training completed with warnings ({unlock_type})"
            
        except Exception as e:
            print(f"\n❌ CRITICAL: Could not capture UI snapshot: {e}")
            return f"Training incomplete: UI pattern not captured ({e})"
        
        return f"WhatsApp unlock trained and verified ({unlock_type})"
    
    def train_generic_login(self, service_name: str) -> str:
        """Train a generic login flow for any service.
        
        Args:
            service_name: Name of the service (e.g., "instagram", "twitter")
            
        Returns:
            Status message
        """
        print("\n" + "="*60)
        print(f"TRAINING: {service_name.title()} Login")
        print("="*60)
        
        # Step 1: Get username/email
        username = input(f"\nEnter {service_name} username/email: ").strip()
        if not username:
            return "Training cancelled: No username provided"
        
        # Step 2: Get password securely
        print("\nEnter password (input will be hidden):")
        password = getpass.getpass("Password: ")
        
        if not password:
            return "Training cancelled: No password provided"
        
        # Step 3: Store in vault
        vault_key_user = f"{service_name}_username"
        vault_key_pass = f"{service_name}_password"
        
        self.vault.set(vault_key_user, username)
        self.vault.set(vault_key_pass, password)
        
        # Step 4: Capture current WorldState
        if self.awareness_state:
            try:
                world = self.awareness_state.build_world_state()
                ui_hash = world.compute_hash()
                
                # Step 5: Save as UI pattern
                self.ui_memory.record_success(
                    world_state=world,
                    goal_intent=f"{service_name}_login",
                    action_type="type_text",
                    element_text="login_form",
                    element_type="Form"
                )
                
                print(f"\n✓ Trained {service_name} login")
                print(f"  Vault keys: {vault_key_user}, {vault_key_pass}")
                print(f"  UI hash: {ui_hash}")
                print(f"  Credentials stored securely (encrypted)")
                
            except Exception as e:
                print(f"\n⚠ Warning: Could not capture UI snapshot: {e}")
                print(f"  Credentials stored in vault, but UI pattern not saved")
        else:
            print(f"\n✓ Credentials stored in vault")
            print(f"  Username: {vault_key_user}")
            print(f"  Password: {vault_key_pass}")
        
        return f"{service_name.title()} login trained"
    
    def list_trained_flows(self) -> str:
        """List all trained authentication flows.
        
        Returns:
            Formatted list of trained flows
        """
        keys = self.vault.list_keys()
        
        if not keys:
            return "No trained authentication flows found."
        
        print("\n" + "="*60)
        print("TRAINED AUTHENTICATION FLOWS")
        print("="*60)
        
        flows = {}
        for key in keys:
            if "_" in key:
                service = key.split("_")[0]
                if service not in flows:
                    flows[service] = []
                flows[service].append(key)
        
        for service, service_keys in sorted(flows.items()):
            print(f"\n{service.upper()}:")
            for key in service_keys:
                print(f"  - {key}")
        
        print(f"\nTotal: {len(keys)} credentials stored")
        print("="*60)
        
        return f"Found {len(flows)} trained services with {len(keys)} credentials"
    
    def delete_all_credentials(self) -> str:
        """Delete ALL stored credentials.
        
        Returns:
            Status message
        """
        all_keys = self.vault.list_keys()
        
        if not all_keys:
            return "No credentials to delete."
        
        print(f"\n⚠️  WARNING: This will delete {len(all_keys)} credentials:")
        for key in all_keys:
            print(f"  - {key}")
        
        confirm = input("\nType 'DELETE ALL' to confirm: ").strip()
        
        if confirm == "DELETE ALL":
            deleted = []
            for key in all_keys:
                try:
                    self.vault.delete(key)
                    deleted.append(key)
                except Exception as e:
                    print(f"  Failed to delete {key}: {e}")
            
            # Also clear ui_memory.json login_flows
            try:
                import json
                from pathlib import Path
                
                memory_file = Path("memory/ui_memory.json")
                if memory_file.exists():
                    with open(memory_file, 'r') as f:
                        memory_data = json.load(f)
                    
                    if "login_flows" in memory_data:
                        memory_data["login_flows"] = []
                        with open(memory_file, 'w') as f:
                            json.dump(memory_data, f, indent=2)
                        print("\n✓ Cleared UI memory login flows")
            except Exception as e:
                print(f"\n⚠️  Could not clear UI memory: {e}")
            
            return f"Deleted {len(deleted)} credentials"
        else:
            return "Deletion cancelled"
    
    def delete_trained_flow(self, vault_key: str) -> str:
        """Delete a trained authentication flow.
        
        Args:
            vault_key: The vault key to delete (case-insensitive)
            vault_key: The vault key to delete (case-sensitive)
            
        Returns:
            Status message
        """
        # Check exact match first
        if self.vault.exists(vault_key):
            confirm = input(f"\nDelete credential '{vault_key}'? (yes/no): ").strip().lower()
            
            if confirm == "yes":
                self.vault.delete(vault_key)
                return f"Deleted: {vault_key}"
            else:
                return "Deletion cancelled"
        
        # Try case-insensitive match
        all_keys = self.vault.list_keys()
        matches = [k for k in all_keys if k.lower() == vault_key.lower()]
        
        if not matches:
            return f"Credential not found: {vault_key}"
        
        # Found case-insensitive match
        actual_key = matches[0]
        print(f"\nFound (case-insensitive): {actual_key}")
        confirm = input(f"Delete credential '{actual_key}'? (yes/no): ").strip().lower()
        
        if confirm == "yes":
            self.vault.delete(actual_key)
            return f"Deleted: {actual_key}"
        else:
            return "Deletion cancelled"
    
    def train_repair(self) -> str:
        """4️⃣ Train Jarvis to repair a specific failure.
        
        Interactive mode where user breaks automation, Jarvis repairs it,
        and the successful repair is saved for future use.
        
        Returns:
            Status message
        """
        print("\n" + "="*60)
        print("TRAINING: Self-Repair Strategy")
        print("="*60)
        
        # Step 1: Get intent
        print("\nWhat were you trying to do when it failed?")
        intent = input("Intent (e.g., 'open github', 'click login'): ").strip()
        
        if not intent:
            return "Training cancelled: No intent provided"
        
        # Step 2: Get diagnosis
        print("\nWhat went wrong? Select all that apply (comma-separated):")
        print("  1. element_not_found")
        print("  2. blocked_by_dialog")
        print("  3. wrong_window")
        print("  4. wrong_tab")
        print("  5. focus_lost")
        print("  6. state_unchanged")
        print("  7. keyboard_input_missing")
        print("  8. browser_not_foreground")
        
        diagnosis_input = input("\nSelect (e.g., 1,2): ").strip()
        
        diagnosis_map = {
            "1": "element_not_found",
            "2": "blocked_by_dialog",
            "3": "wrong_window",
            "4": "wrong_tab",
            "5": "focus_lost",
            "6": "state_unchanged",
            "7": "keyboard_input_missing",
            "8": "browser_not_foreground",
        }
        
        selected = [diagnosis_map.get(n.strip()) for n in diagnosis_input.split(",")]
        selected = [s for s in selected if s]
        
        if not selected:
            return "Training cancelled: No diagnosis selected"
        
        # Step 3: Get repair strategy
        print("\nWhat repair strategy worked?")
        print("  1. dismiss_dialog")
        print("  2. bring_browser_front")
        print("  3. refocus_window")
        print("  4. retry_navigation")
        print("  5. refocus_and_retry")
        print("  6. expand_search_scope")
        print("  7. retype")
        print("  8. reexecute_with_delay")
        
        strategy_input = input("\nSelect (1-8): ").strip()
        
        strategy_map = {
            "1": "dismiss_dialog",
            "2": "bring_browser_front",
            "3": "refocus_window",
            "4": "retry_navigation",
            "5": "refocus_and_retry",
            "6": "expand_search_scope",
            "7": "retype",
            "8": "reexecute_with_delay",
        }
        
        strategy = strategy_map.get(strategy_input)
        if not strategy:
            return "Training cancelled: Invalid strategy"
        
        # Step 4: Capture current WorldState
        if self.awareness_state:
            try:
                world = self.awareness_state.build_world_state()
                from awareness.perception_snapshot import PerceptionSnapshot
                snapshot = PerceptionSnapshot.from_world_state(world)
                
                # Step 5: Save repair pattern
                import json
                from pathlib import Path
                
                memory_file = Path("memory/ui_memory.json")
                if memory_file.exists():
                    with open(memory_file, 'r') as f:
                        memory_data = json.load(f)
                else:
                    memory_data = {"version": "1.0", "patterns": [], "repairs": []}
                
                if "repairs" not in memory_data:
                    memory_data["repairs"] = []
                
                # Build diagnosis dict
                diagnosis_dict = {key: (key in selected) for key in [
                    "element_not_found", "blocked_by_dialog", "wrong_window",
                    "wrong_tab", "focus_lost", "state_unchanged",
                    "keyboard_input_missing", "browser_not_foreground"
                ]}
                
                memory_data["repairs"].append({
                    "intent": intent,
                    "diagnosis": diagnosis_dict,
                    "strategy": strategy,
                    "snapshot_hash": snapshot.screen_hash,
                    "timestamp": snapshot.timestamp,
                })
                
                with open(memory_file, 'w') as f:
                    json.dump(memory_data, f, indent=2)
                
                print(f"\n✓ Trained repair strategy")
                print(f"  Intent: {intent}")
                print(f"  Diagnosis: {', '.join(selected)}")
                print(f"  Strategy: {strategy}")
                print(f"  Snapshot hash: {snapshot.screen_hash}")
                
            except Exception as e:
                print(f"\n⚠ Warning: Could not save repair pattern: {e}")
        else:
            print(f"\n⚠ Awareness state not available")
        
        return f"Repair strategy trained: {strategy} for {intent}"


def run_training_session(awareness_state=None):
    """Run an interactive training session.
    
    Args:
        awareness_state: Optional StateCache for capturing UI snapshots
    """
    # 1️⃣ CRITICAL FIX: Start AwarenessController for live perception
    if awareness_state is None:
        print("\n" + "="*60)
        print("INITIALIZING LIVE PERCEPTION")
        print("="*60)
        print("Starting awareness system for UI pattern capture...")
        
        try:
            from awareness.controller import AwarenessController
            from awareness.state_cache import StateCache
            
            state_cache = StateCache()
            awareness = AwarenessController(
                enable_ui_monitor=True,
                enable_process_watcher=False  # Not needed for training
            )
            awareness.start()
            awareness_state = state_cache
            
            print("✓ Awareness system started")
            print("✓ Live perception active")
            
            # Give UIA time to initialize
            import time
            time.sleep(2.0)
            
        except Exception as e:
            print(f"\n❌ CRITICAL: Cannot start awareness system: {e}")
            print("Training requires live perception to capture UI patterns.")
            print("Please ensure you're running on Windows with UI Automation available.")
            return
    
    controller = TrainingController(awareness_state)
    
    print("\n" + "="*60)
    print("JARVIS TRAINING MODE")
    print("="*60)
    print("\nAvailable training commands:")
    print("  1. train taskbar_chrome")
    print("  2. train whatsapp_unlock")
    print("  3. train <service_name>")
    print("  4. train repair")
    print("  5. list")
    print("  6. delete <vault_key>")
    print("  7. delete all")
    print("  8. exit")
    print("="*60)
    
    while True:
        command = input("\nTraining> ").strip().lower()
        
        if not command:
            continue
        
        if command == "exit" or command == "quit":
            print("\nExiting training mode...")
            break
        
        elif command == "train taskbar_chrome" or command == "1":
            result = controller.train_taskbar_chrome()
            print(f"\n{result}")
        
        elif command == "train whatsapp_unlock" or command == "2":
            result = controller.train_whatsapp_unlock()
            print(f"\n{result}")
        
        elif command == "train repair" or command == "4":
            result = controller.train_repair()
            print(f"\n{result}")
        
        elif command.startswith("train "):
            service = command.replace("train ", "").strip()
            if service != "repair":
                result = controller.train_generic_login(service)
                print(f"\n{result}")
        
        elif command == "list" or command == "5":
            controller.list_trained_flows()
        
        elif command == "delete all" or command == "7":
            result = controller.delete_all_credentials()
            print(f"\n{result}")
        
        elif command.startswith("delete "):
            vault_key = command.replace("delete ", "").strip()
            result = controller.delete_trained_flow(vault_key)
            print(f"\n{result}")
        
        elif command == "exit" or command == "quit" or command == "8":
            print("\nExiting training mode...")
            break
        
        else:
            print(f"\nUnknown command: {command}")
            print("Type 'exit' to quit or see available commands above")


if __name__ == "__main__":
    run_training_session()
