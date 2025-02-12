#!/usr/bin/env python3
import os
import shutil
import filecmp
from git import Repo
import tempfile
import argparse
import json
from typing import Dict, List, Tuple, Set

# Load the configuration file
with open("conf.json") as f:
    c = json.load(f)

OC_SERVICES_TEMPLATES = os.getenv("OC_SERVICES_TEMPLATES", c["oc_services_templates"])

class SyncConfig:
    def __init__(self, folders: Set[str], files: Set[str]):
        self.folders = folders
        self.files = files

    def __str__(self):
        parts = []
        if self.folders:
            parts.append(f"Folders: {', '.join(self.folders)}")
        if self.files:
            parts.append(f"Files: {', '.join(self.files)}")
        return " | ".join(parts)


class ChangeTracker:
    def __init__(self):
        self.to_add: List[str] = []
        self.to_update: List[str] = []
        
    def add_file(self, path: str):
        self.to_add.append(path)
        
    def update_file(self, path: str):
        self.to_update.append(path)
        
    def has_changes(self) -> bool:
        return bool(self.to_add or self.to_update)
        
    def print_plan(self):
        if not self.has_changes():
            print("\nNo changes detected.")
            return

        print("\nChanges to apply:")
        print("================")
        
        if self.to_add:
            print("\nNew files:")
            for f in sorted(self.to_add):
                print(f"  + {f}")
                
        if self.to_update:
            print("\nUpdated files:")
            for f in sorted(self.to_update):
                print(f"  ~ {f}")
                
        print(f"\nSummary: {len(self.to_add)} additions, {len(self.to_update)} updates")


def load_sync_config() -> SyncConfig:
    """
    Load sync configuration from config.json
    Returns a SyncConfig object containing sets of folders and files to sync
    """
    try:
        with open("conf.json") as f:
            config = json.load(f)
            
        sync_config = config.get("sync", {
            "folders": ["static"],
            "files": []
        })
        
        folders = set(sync_config.get("folders", ["static"]))
        files = set(sync_config.get("files", []))
        
        config = SyncConfig(folders, files)
        print(f"Loaded sync configuration: {config}")
        return config
            
    except FileNotFoundError:
        print("Warning: conf.json not found, using default sync path: 'static'")
        return SyncConfig({"static"}, set())
    except json.JSONDecodeError:
        print("Warning: Invalid conf.json format, using default sync path: 'static'")
        return SyncConfig({"static"}, set())
    except Exception as e:
        print(f"Warning: Error loading conf.json ({str(e)}), using default sync path: 'static'")
        return SyncConfig({"static"}, set())


def check_file_update(src: str, dst: str) -> bool:
    """
    Check if a file needs to be updated based on modification time and content
    """
    if not os.path.exists(dst):
        return True
    
    src_time = os.path.getmtime(src)
    dst_time = os.path.getmtime(dst)
    
    return src_time > dst_time and not filecmp.cmp(src, dst, shallow=False)


def should_sync_path(path: str, config: SyncConfig) -> bool:
    """
    Check if a path should be synced based on the configuration
    """
    path = path.rstrip(os.sep)
    
    # Check if the path is a specific file that should be synced
    if path in config.files:
        return True
        
    # Check if the path is within a folder that should be synced
    return any(
        path == folder or path.startswith(folder + os.sep)
        for folder in config.folders
    )


def scan_changes(src_dir: str, dst_dir: str, tracker: ChangeTracker, config: SyncConfig) -> None:
    """
    Scan for changes between source and destination directories
    """
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir)

    for item in os.listdir(src_dir):
        if item == '.git':
            continue
            
        src_path = os.path.join(src_dir, item)
        dst_path = os.path.join(dst_dir, item)
        rel_path = os.path.relpath(dst_path, os.getcwd())
        
        # Skip if path is not in sync configuration
        if not should_sync_path(rel_path, config):
            continue
            
        if os.path.isdir(src_path):
            scan_changes(src_path, dst_path, tracker, config)
        else:
            if not os.path.exists(dst_path):
                tracker.add_file(rel_path)
            elif check_file_update(src_path, dst_path):
                tracker.update_file(rel_path)


def sync_files(src_dir: str, dst_dir: str, config: SyncConfig) -> None:
    """
    Synchronize files from source to destination directory
    """
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir)
        print(f"Created directory: {dst_dir}")

    for item in os.listdir(src_dir):
        if item == '.git':
            continue
            
        src_path = os.path.join(src_dir, item)
        dst_path = os.path.join(dst_dir, item)
        rel_path = os.path.relpath(dst_path, os.getcwd())
        
        # Skip if path is not in sync configuration
        if not should_sync_path(rel_path, config):
            continue
            
        if os.path.isdir(src_path):
            sync_files(src_path, dst_path, config)
        elif check_file_update(src_path, dst_path):
            action = "Added" if not os.path.exists(dst_path) else "Updated"
            shutil.copy2(src_path, dst_path)
            print(f"{action}: {rel_path}")


def sync_repository(auto_mode: bool = False) -> None:
    """
    Main function to handle repository synchronization
    """
    cwd = os.getcwd()
    print(f"Working directory: {cwd}")
    
    # Load sync configuration
    config = load_sync_config()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            print(f"Cloning {OC_SERVICES_TEMPLATES}...")
            Repo.clone_from(OC_SERVICES_TEMPLATES, temp_dir)
            
            if not auto_mode:
                tracker = ChangeTracker()
                print("\nAnalyzing repository...")
                scan_changes(temp_dir, cwd, tracker, config)
                
                tracker.print_plan()
                
                if not tracker.has_changes():
                    return
                    
                if input("\nProceed with these changes? [y/N]: ").lower() != 'y':
                    print("Operation cancelled.")
                    return
                
                print("\nApplying changes...")
            
            sync_files(temp_dir, cwd, config)
            print("\nSync completed successfully!")
            
        except Exception as e:
            print(f"Error: {str(e)}")


def main():
    parser = argparse.ArgumentParser(
        description='Sync files from oc_services_templates repository'
    )
    parser.add_argument(
        '--auto',
        action='store_true',
        help='run in automatic mode without confirmation'
    )
    
    args = parser.parse_args()
    sync_repository(args.auto)


if __name__ == "__main__":
    main()