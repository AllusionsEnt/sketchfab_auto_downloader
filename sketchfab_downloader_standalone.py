#!/usr/bin/env python3
"""
Sketchfab Author Model Downloader - STANDALONE VERSION
Downloads models with licenses: CC0, CC-BY, Free Standard, Standard
"""

import requests
import os
import json
import time
from pathlib import Path

class SketchfabDownloader:
    def __init__(self, api_token=None):
        """Initialize the downloader"""
        self.api_token = api_token
        self.base_url = "https://api.sketchfab.com/v3"
        self.headers = {}
        if api_token:
            self.headers["Authorization"] = f"Token {api_token}"
    
    def get_user_models(self, username):
        """Get all models from a user"""
        models = []
        url = f"{self.base_url}/models"
        params = {
            "user": username,
            "count": 100
        }
        
        print(f"Fetching models for user: {username}")
        
        while url:
            response = requests.get(url, params=params, headers=self.headers)
            
            if response.status_code != 200:
                print(f"Error fetching models: {response.status_code}")
                print(response.text)
                break
            
            data = response.json()
            results = data.get("results", [])
            models.extend(results)
            
            print(f"Found {len(results)} models (Total: {len(models)})")
            
            url = data.get("next")
            params = None
            
            time.sleep(0.2)
        
        return models
    
    def download_author_models(self, username, output_dir="downloads", allowed_licenses=None):
        """Download all models from an author with license filtering"""
        if not self.api_token:
            print("Error: API token is required for downloading models")
            return
        
        # Default allowed licenses
        if allowed_licenses is None:
            allowed_licenses = ['cc0', 'by', 'free standard', 'standard']
        
        allowed_licenses = [lic.lower() for lic in allowed_licenses]
        
        # Create output directory
        output_path = Path(output_dir) / username
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Get all models
        models = self.get_user_models(username)
        
        if not models:
            print("No models found or unable to fetch models")
            return
        
        print(f"\nFound {len(models)} total models")
        print(f"Downloading to: {output_path}")
        print("-" * 60)
        
        # Save metadata
        metadata_file = output_path / "models_metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(models, f, indent=2)
        print(f"Saved metadata to: {metadata_file}")
        
        # Download each model
        successful = 0
        failed = 0
        skipped_license = 0
        
        for i, model in enumerate(models, 1):
            model_uid = model.get("uid")
            model_name = model.get("name", "unknown")
            is_downloadable = model.get("isDownloadable", False)
            license_info = model.get("license", {})
            license_label = license_info.get("label", "unknown").lower()
            
            # Sanitize filename
            safe_name = "".join(c for c in model_name if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_name = safe_name[:100]
            
            print(f"\n[{i}/{len(models)}] {model_name}")
            print(f"  UID: {model_uid}")
            print(f"  License: {license_info.get('label', 'Unknown')}")
            print(f"  Downloadable: {is_downloadable}")
            
            # Check license
            license_label_lower = license_label.lower().strip()
            license_matches = False
            
            for allowed in allowed_licenses:
                allowed_lower = allowed.lower().strip()
                
                # Exact match
                if license_label_lower == allowed_lower:
                    license_matches = True
                    break
                
                # Normalized match
                license_normalized = license_label_lower.replace('-', ' ').replace('_', ' ')
                allowed_normalized = allowed_lower.replace('-', ' ').replace('_', ' ')
                
                if license_normalized == allowed_normalized:
                    license_matches = True
                    break
                
                # CC BY variations (including "CC Attribution")
                if allowed_lower == 'by':
                    if 'attribution' in license_normalized or ('cc' in license_normalized and 'by' in license_normalized):
                        # But not "by-nc" or "by-nd" or "by-sa"
                        if 'nc' not in license_normalized and 'nd' not in license_normalized and 'sa' not in license_normalized and 'noncommercial' not in license_normalized and 'noderivatives' not in license_normalized and 'sharealike' not in license_normalized:
                            license_matches = True
                            break
                
                # CC0 variations
                if allowed_lower == 'cc0' and ('cc0' in license_normalized or 'cc 0' in license_normalized):
                    license_matches = True
                    break
            
            if not license_matches:
                print(f"  Skipped: License not in allowed list")
                skipped_license += 1
                continue
            
            if not is_downloadable:
                print("  Skipped: Model not downloadable")
                failed += 1
                continue
            
            # Download immediately
            try:
                # Get download URL
                url = f"{self.base_url}/models/{model_uid}/download"
                response = requests.get(url, headers=self.headers, timeout=10)
                
                if response.status_code != 200:
                    print(f"  ✗ Failed: Could not get download URL (status {response.status_code})")
                    failed += 1
                    continue
                
                data = response.json()
                
                # Get URL
                download_url = None
                if "source" in data and "url" in data["source"]:
                    download_url = data["source"]["url"]
                elif "gltf" in data and "url" in data["gltf"]:
                    download_url = data["gltf"]["url"]
                
                if not download_url:
                    print("  ✗ Failed: No download URL available")
                    failed += 1
                    continue
                
                # Determine file extension
                ext = ".zip"
                if "." in download_url.split("/")[-1]:
                    ext = "." + download_url.split(".")[-1].split("?")[0]
                
                filepath = output_path / f"{safe_name}_{model_uid}{ext}"
                
                # Check if file already exists
                if filepath.exists():
                    file_size = filepath.stat().st_size
                    print(f"  ⊙ Already exists ({file_size:,} bytes) - Skipping")
                    successful += 1  # Count as successful since we have it
                    time.sleep(0.1)
                    continue
                
                # Download immediately
                dl_response = requests.get(download_url, stream=True, timeout=30)
                dl_response.raise_for_status()
                
                total_size = int(dl_response.headers.get('content-length', 0))
                
                with open(filepath, 'wb') as f:
                    if total_size == 0:
                        f.write(dl_response.content)
                    else:
                        downloaded = 0
                        for chunk in dl_response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                percent = (downloaded / total_size) * 100
                                print(f"\r  Progress: {percent:.1f}%", end='', flush=True)
                print()
                print(f"  ✓ Success! Saved to: {filepath.name}")
                successful += 1
                
            except Exception as e:
                print(f"  ✗ Failed: {e}")
                failed += 1
            
            time.sleep(0.3)
        
        print("\n" + "=" * 60)
        print(f"Download complete!")
        print(f"Successful: {successful}")
        print(f"Failed/Not downloadable: {failed}")
        print(f"Skipped (license): {skipped_license}")
        print(f"Total: {len(models)}")
        print(f"\nAllowed licenses: {', '.join([lic.upper() for lic in allowed_licenses])}")


def main():
    # Check requests library
    try:
        import requests
    except ImportError:
        print("ERROR: The 'requests' library is not installed.")
        print("Please install it by running:")
        print("  pip install requests")
        return
    
    print("=" * 60)
    print("Sketchfab Downloader - Standalone Version")
    print("=" * 60)
    print()
    print("This will download ONLY these licenses:")
    print("  ✓ CC0 (Public Domain)")
    print("  ✓ CC-BY (Attribution)")
    print("  ✓ Free Standard")
    print("  ✓ Standard")
    print()
    
    # Get API token
    print("To download models, you need a Sketchfab API token.")
    print("Get yours at: https://sketchfab.com/settings/password")
    print()
    
    api_token = input("Enter your API token: ").strip()
    
    if not api_token:
        print("Error: API token is required")
        return
    
    # Get username
    username = input("\nEnter Sketchfab username: ").strip()
    
    if not username:
        print("Error: Username is required")
        return
    
    # Get output directory
    output_dir = input("Enter output directory (default: downloads): ").strip()
    if not output_dir:
        output_dir = "downloads"
    
    # Pre-configured licenses
    allowed_licenses = ['cc0', 'by', 'free standard', 'standard']
    
    print(f"\n✓ Will download models with these licenses: {', '.join([l.upper() for l in allowed_licenses])}")
    print()
    
    # Create downloader and start
    downloader = SketchfabDownloader(api_token)
    downloader.download_author_models(username, output_dir, allowed_licenses=allowed_licenses)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDownload cancelled by user.")
    except Exception as e:
        print(f"\n\nError occurred: {e}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
    finally:
        input("\nPress Enter to close this window...")
