#!/usr/bin/env python3
import os
import shutil
import filecmp
from git import Repo
import tempfile
import argparse
from typing import Dict, List, Tuple

OC_SERVICES_TEMPLATES = 'https://github.com/opencitations/oc_services_templates'

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


def check_file_update(src: str, dst: str) -> bool:
    if not os.path.exists(dst):
        return True
    
    src_time = os.path.getmtime(src)
    dst_time = os.path.getmtime(dst)
    
    return src_time > dst_time and not filecmp.cmp(src, dst, shallow=False)


def scan_changes(src_dir: str, dst_dir: str, tracker: ChangeTracker) -> None:
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir)

    for item in os.listdir(src_dir):
        if item == '.git':
            continue
            
        src_path = os.path.join(src_dir, item)
        dst_path = os.path.join(dst_dir, item)
        rel_path = os.path.relpath(dst_path, os.getcwd())
        
        if os.path.isdir(src_path):
            scan_changes(src_path, dst_path, tracker)
        else:
            if not os.path.exists(dst_path):
                tracker.add_file(rel_path)
            elif check_file_update(src_path, dst_path):
                tracker.update_file(rel_path)


def sync_files(src_dir: str, dst_dir: str) -> None:
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir)
        print(f"Created directory: {dst_dir}")

    for item in os.listdir(src_dir):
        if item == '.git':
            continue
            
        src_path = os.path.join(src_dir, item)
        dst_path = os.path.join(dst_dir, item)
        rel_path = os.path.relpath(dst_path, os.getcwd())
        
        if os.path.isdir(src_path):
            sync_files(src_path, dst_path)
        elif check_file_update(src_path, dst_path):
            action = "Added" if not os.path.exists(dst_path) else "Updated"
            shutil.copy2(src_path, dst_path)
            print(f"{action}: {rel_path}")


def sync_repository(auto_mode: bool = False) -> None:
    cwd = os.getcwd()
    print(f"Working directory: {cwd}")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            print(f"Cloning {OC_SERVICES_TEMPLATES}...")
            Repo.clone_from(OC_SERVICES_TEMPLATES, temp_dir)
            
            if not auto_mode:
                tracker = ChangeTracker()
                print("\nAnalyzing repository...")
                scan_changes(temp_dir, cwd, tracker)
                
                tracker.print_plan()
                
                if not tracker.has_changes():
                    return
                    
                if input("\nProceed with these changes? [y/N]: ").lower() != 'y':
                    print("Operation cancelled.")
                    return
                
                print("\nApplying changes...")
            
            sync_files(temp_dir, cwd)
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