#!/usr/bin/env python3
"""Test script to analyze what path information Navidrome APIs return.

This script connects to your Navidrome server and examines the path data
returned by different API endpoints to help diagnose path resolution issues.

Usage:
    python scripts/test_navidrome_paths.py --url http://192.168.1.250:4534 --user admin --password yourpass --playlist "Best Hip Hop"
    
Or test a specific song ID:
    python scripts/test_navidrome_paths.py --url http://192.168.1.250:4534 --user admin --password yourpass --song-id abc123
"""

import argparse
import asyncio
import hashlib
import json
import secrets

import httpx


def generate_auth_params(username: str, password: str) -> dict[str, str]:
    """Generate Subsonic API auth params using token method."""
    salt = secrets.token_hex(8)
    token = hashlib.md5((password + salt).encode()).hexdigest()
    return {
        "u": username,
        "t": token,
        "s": salt,
        "v": "1.16.1",
        "c": "navidisc-test",
        "f": "json",
    }


async def test_subsonic_api(client: httpx.AsyncClient, base_url: str, auth_params: dict, song_id: str) -> dict:
    """Test what the Subsonic API getSong returns for path info."""
    print(f"\n{'='*60}")
    print(f"TESTING SUBSONIC API: getSong (ID: {song_id})")
    print(f"{'='*60}")
    
    url = f"{base_url}/rest/getSong"
    params = {**auth_params, "id": song_id}
    
    try:
        response = await client.get(url, params=params)
        data = response.json()
        
        if "subsonic-response" in data and data["subsonic-response"].get("status") == "ok":
            song = data["subsonic-response"].get("song", {})
            
            print(f"\nSubsonic API Response for song:")
            print(f"  Title: {song.get('title')}")
            print(f"  Artist: {song.get('artist')}")
            print(f"  Album: {song.get('album')}")
            
            # Key path fields
            print(f"\n  PATH FIELDS:")
            print(f"    path: {song.get('path', 'NOT PRESENT')}")
            print(f"    file: {song.get('file', 'NOT PRESENT')}")
            print(f"    musicBrainzId: {song.get('musicBrainzId', 'NOT PRESENT')}")
            
            # All fields for reference
            print(f"\n  ALL FIELDS: {list(song.keys())}")
            
            return song
        else:
            print(f"  ERROR: {data}")
            return {}
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        return {}


async def test_navidrome_native_api(client: httpx.AsyncClient, base_url: str, username: str, password: str, song_id: str) -> dict:
    """Test what Navidrome's native API returns for path info."""
    print(f"\n{'='*60}")
    print(f"TESTING NAVIDROME NATIVE API: /api/inspect (ID: {song_id})")
    print(f"{'='*60}")
    
    # First, get JWT token
    try:
        auth_url = f"{base_url}/auth/login"
        auth_response = await client.post(auth_url, json={"username": username, "password": password})
        
        if auth_response.status_code != 200:
            print(f"  Auth failed: {auth_response.status_code} - {auth_response.text[:200]}")
            return {}
            
        auth_data = auth_response.json()
        token = auth_data.get("token")
        
        if not token:
            print(f"  No token in response: {auth_data}")
            return {}
            
        print(f"  Got JWT token: {token[:20]}...")
        
        # Now call /api/inspect
        inspect_url = f"{base_url}/api/inspect"
        headers = {"x-nd-authorization": f"Bearer {token}"}
        params = {"id": song_id}
        
        response = await client.get(inspect_url, headers=headers, params=params)
        print(f"\n  Inspect API status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n  INSPECT API Response:")
            print(f"    file: {data.get('file', 'NOT PRESENT')}")
            print(f"    path: {data.get('path', 'NOT PRESENT')}")
            
            # Show all top-level keys
            print(f"\n  ALL TOP-LEVEL KEYS: {list(data.keys())}")
            
            # Pretty print the full response
            print(f"\n  FULL RESPONSE:")
            print(json.dumps(data, indent=4, default=str)[:2000])
            
            return data
        else:
            print(f"  Error: {response.status_code} - {response.text[:500]}")
            return {}
            
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return {}


async def test_navidrome_song_api(client: httpx.AsyncClient, base_url: str, username: str, password: str, song_id: str) -> dict:
    """Test Navidrome's native song API endpoint."""
    print(f"\n{'='*60}")
    print(f"TESTING NAVIDROME NATIVE API: /api/song/{song_id}")
    print(f"{'='*60}")
    
    try:
        # Get JWT token
        auth_url = f"{base_url}/auth/login"
        auth_response = await client.post(auth_url, json={"username": username, "password": password})
        
        if auth_response.status_code != 200:
            print(f"  Auth failed: {auth_response.status_code}")
            return {}
            
        token = auth_response.json().get("token")
        
        # Call /api/song/{id}
        song_url = f"{base_url}/api/song/{song_id}"
        headers = {"x-nd-authorization": f"Bearer {token}"}
        
        response = await client.get(song_url, headers=headers)
        print(f"\n  Song API status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n  SONG API Response:")
            print(f"    path: {data.get('path', 'NOT PRESENT')}")
            print(f"    file: {data.get('file', 'NOT PRESENT')}")
            print(f"\n  ALL KEYS: {list(data.keys())}")
            
            # Show path-related fields
            for key in data.keys():
                if 'path' in key.lower() or 'file' in key.lower():
                    print(f"    {key}: {data[key]}")
                    
            return data
        else:
            print(f"  Error: {response.status_code} - {response.text[:500]}")
            return {}
            
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        return {}


async def test_navidrome_mediafile_api(client: httpx.AsyncClient, base_url: str, username: str, password: str, song_id: str) -> dict:
    """Test Navidrome's native mediaFile API endpoint."""
    print(f"\n{'='*60}")
    print(f"TESTING NAVIDROME NATIVE API: /api/mediaFile (ID: {song_id})")
    print(f"{'='*60}")
    
    try:
        # Get JWT token
        auth_url = f"{base_url}/auth/login"
        auth_response = await client.post(auth_url, json={"username": username, "password": password})
        
        if auth_response.status_code != 200:
            print(f"  Auth failed: {auth_response.status_code}")
            return {}
            
        token = auth_response.json().get("token")
        headers = {"x-nd-authorization": f"Bearer {token}"}
        
        # Try different endpoints that might exist
        endpoints = [
            f"/api/mediaFile/{song_id}",
            f"/api/mediafile/{song_id}",
            f"/api/media_file/{song_id}",
            f"/api/song/{song_id}",
        ]
        
        for endpoint in endpoints:
            url = f"{base_url}{endpoint}"
            response = await client.get(url, headers=headers)
            
            print(f"\n  {endpoint}: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"    SUCCESS! Keys: {list(data.keys())}")
                for key in data.keys():
                    if 'path' in key.lower() or 'file' in key.lower():
                        print(f"    {key}: {data[key]}")
                return data
                
        return {}
            
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        return {}


async def get_playlist_track(client: httpx.AsyncClient, base_url: str, auth_params: dict, playlist_name: str) -> str | None:
    """Get the first track ID from a playlist."""
    print(f"\n{'='*60}")
    print(f"Getting track from playlist: {playlist_name}")
    print(f"{'='*60}")
    
    # Get playlists
    url = f"{base_url}/rest/getPlaylists"
    response = await client.get(url, params=auth_params)
    data = response.json().get("subsonic-response", {})
    
    playlists = data.get("playlists", {}).get("playlist", [])
    if isinstance(playlists, dict):
        playlists = [playlists]
    
    # Find the playlist
    playlist_id = None
    for p in playlists:
        if p.get("name", "").lower() == playlist_name.lower():
            playlist_id = p.get("id")
            print(f"  Found playlist: {p.get('name')} (ID: {playlist_id})")
            break
    
    if not playlist_id:
        print(f"  Playlist not found: {playlist_name}")
        print(f"  Available playlists: {[p.get('name') for p in playlists]}")
        return None
    
    # Get playlist tracks
    url = f"{base_url}/rest/getPlaylist"
    params = {**auth_params, "id": playlist_id}
    response = await client.get(url, params=params)
    data = response.json().get("subsonic-response", {})
    
    tracks = data.get("playlist", {}).get("entry", [])
    if isinstance(tracks, dict):
        tracks = [tracks]
    
    if not tracks:
        print(f"  No tracks in playlist")
        return None
        
    # Return first track ID
    track = tracks[0]
    print(f"  First track: {track.get('title')} by {track.get('artist')}")
    print(f"  Track ID: {track.get('id')}")
    print(f"  Subsonic path field: {track.get('path', 'NOT PRESENT')}")
    
    return track.get("id")


async def main():
    parser = argparse.ArgumentParser(description="Test Navidrome API path resolution")
    parser.add_argument("--url", required=True, help="Navidrome server URL (e.g., http://192.168.1.250:4534)")
    parser.add_argument("--user", required=True, help="Username")
    parser.add_argument("--password", required=True, help="Password")
    parser.add_argument("--playlist", help="Playlist name to test (will use first track)")
    parser.add_argument("--song-id", help="Specific song ID to test")
    
    args = parser.parse_args()
    
    base_url = args.url.rstrip("/")
    auth_params = generate_auth_params(args.user, args.password)
    
    print(f"\n{'#'*60}")
    print(f"NAVIDROME PATH RESOLUTION TEST")
    print(f"Server: {base_url}")
    print(f"{'#'*60}")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Get a song ID to test
        song_id = args.song_id
        
        if not song_id and args.playlist:
            song_id = await get_playlist_track(client, base_url, auth_params, args.playlist)
        
        if not song_id:
            print("\nNo song ID provided and no playlist specified. Use --song-id or --playlist")
            return
        
        # Test all APIs
        subsonic_data = await test_subsonic_api(client, base_url, auth_params, song_id)
        native_inspect = await test_navidrome_native_api(client, base_url, args.user, args.password, song_id)
        native_song = await test_navidrome_song_api(client, base_url, args.user, args.password, song_id)
        native_mediafile = await test_navidrome_mediafile_api(client, base_url, args.user, args.password, song_id)
        
        # Summary
        print(f"\n{'#'*60}")
        print(f"SUMMARY")
        print(f"{'#'*60}")
        print(f"\nSubsonic API 'path' field:")
        print(f"  {subsonic_data.get('path', 'NOT PRESENT')}")
        print(f"\nNavidrome /api/inspect 'file' field:")
        print(f"  {native_inspect.get('file', 'NOT PRESENT')}")
        print(f"\nNavidrome /api/song 'path' field:")
        print(f"  {native_song.get('path', 'NOT PRESENT')}")
        
        print(f"\n{'#'*60}")
        print("If the paths above differ from your actual filesystem paths,")
        print("it may be due to Docker volume mappings. Check your docker-compose:")
        print("  - Navidrome sees:    /music/Artist/Album/track.flac")  
        print("  - Host filesystem:   /actual/path/Artist/Album/track.flac")
        print(f"{'#'*60}")


if __name__ == "__main__":
    asyncio.run(main())
