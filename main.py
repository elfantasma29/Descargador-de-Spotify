from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
from urllib.parse import quote

app = FastAPI(title="Spotify Downloader API - Vercel")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

EXTERNAL_API = "https://api.spotifydown.com/download"
METADATA_API = "https://api.spotifydown.com/metadata/track"

@app.get("/")
async def root():
    return JSONResponse(
        content={
            "status_code": 200,
            "message": "Spotify Downloader API",
            "developer": "El Impaciente",
            "telegram_channel": "https://t.me/Apisimpacientes",
            "endpoints": {
                "/download": "Download Spotify tracks - Use: /download?url=SPOTIFY_URL",
                "/search": "Search Spotify tracks - Use: /search?query=SONG_NAME",
                "/health": "Check API health status"
            }
        },
        status_code=200
    )

@app.get("/download")
async def download_track(url: str = Query(default="", description="Spotify track URL")):
    if not url or url.strip() == "":
        return JSONResponse(
            content={
                "status_code": 400,
                "message": "Parameter 'url' is required",
                "developer": "El Impaciente",
                "telegram_channel": "https://t.me/Apisimpacientes",
                "example": "/download?url=https://open.spotify.com/track/TRACK_ID"
            },
            status_code=400
        )
    
    try:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Linux; Android 14; V2336 Build/UP1A.231005.007) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.135 Mobile Safari/537.36",
            "Accept": "application/json",
            "Origin": "https://spotifydown.com",
            "Referer": "https://spotifydown.com/"
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            metadata_response = await client.get(
                f"{METADATA_API}/{url.split('/')[-1].split('?')[0]}",
                headers=headers
            )
            
            if metadata_response.status_code != 200:
                return JSONResponse(
                    content={
                        "status_code": 400,
                        "message": "Error fetching track data. Verify the Spotify URL is valid",
                        "developer": "El Impaciente",
                        "telegram_channel": "https://t.me/Apisimpacientes"
                    },
                    status_code=400
                )
            
            track_data = metadata_response.json()
            
            download_response = await client.get(
                f"{EXTERNAL_API}/{url.split('/')[-1].split('?')[0]}",
                headers=headers
            )
            
            if download_response.status_code != 200:
                return JSONResponse(
                    content={
                        "status_code": 400,
                        "message": "Error generating download link",
                        "developer": "El Impaciente",
                        "telegram_channel": "https://t.me/Apisimpacientes"
                    },
                    status_code=400
                )
            
            download_data = download_response.json()
            
            title = track_data.get("title", "Unknown")
            artists = ", ".join([artist.get("name", "") for artist in track_data.get("artists", [])])
            album = track_data.get("album", {}).get("name", "Unknown")
            cover = track_data.get("album", {}).get("images", [{}])[0].get("url", "")
            duration = track_data.get("duration_ms", 0) // 1000
            download_url = download_data.get("link", "")
            
            return JSONResponse(
                content={
                    "status_code": 200,
                    "title": title,
                    "artists": artists,
                    "album": album,
                    "cover": cover,
                    "duration": f"{duration // 60}:{duration % 60:02d}",
                    "download_url": download_url,
                    "developer": "El Impaciente",
                    "telegram_channel": "https://t.me/Apisimpacientes"
                },
                status_code=200
            )
        
    except httpx.TimeoutException:
        return JSONResponse(
            content={
                "status_code": 408,
                "message": "Request timeout. The external API took too long to respond",
                "developer": "El Impaciente",
                "telegram_channel": "https://t.me/Apisimpacientes"
            },
            status_code=408
        )
    except Exception as e:
        return JSONResponse(
            content={
                "status_code": 500,
                "message": "Error processing track. Verify the URL is correct",
                "error": str(e),
                "developer": "El Impaciente",
                "telegram_channel": "https://t.me/Apisimpacientes"
            },
            status_code=500
        )

@app.get("/search")
async def search_track(query: str = Query(default="", description="Search query for track")):
    if not query or query.strip() == "":
        return JSONResponse(
            content={
                "status_code": 400,
                "message": "Parameter 'query' is required",
                "developer": "El Impaciente",
                "telegram_channel": "https://t.me/Apisimpacientes",
                "example": "/search?query=song name artist"
            },
            status_code=400
        )
    
    try:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Linux; Android 14; V2336 Build/UP1A.231005.007) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.135 Mobile Safari/537.36",
            "Accept": "application/json"
        }
        
        search_url = f"https://api.spotify.com/v1/search?q={quote(query)}&type=track&limit=10"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            token_response = await client.post(
                "https://accounts.spotify.com/api/token",
                data={"grant_type": "client_credentials"},
                auth=("anonymous", "anonymous")
            )
            
            if token_response.status_code != 200:
                return JSONResponse(
                    content={
                        "status_code": 400,
                        "message": "Error authenticating with Spotify",
                        "developer": "El Impaciente",
                        "telegram_channel": "https://t.me/Apisimpacientes"
                    },
                    status_code=400
                )
            
            access_token = token_response.json().get("access_token", "")
            headers["Authorization"] = f"Bearer {access_token}"
            
            search_response = await client.get(search_url, headers=headers)
            
            if search_response.status_code != 200:
                return JSONResponse(
                    content={
                        "status_code": 400,
                        "message": "Error searching tracks",
                        "developer": "El Impaciente",
                        "telegram_channel": "https://t.me/Apisimpacientes"
                    },
                    status_code=400
                )
            
            search_data = search_response.json()
            tracks = []
            
            for item in search_data.get("tracks", {}).get("items", []):
                tracks.append({
                    "title": item.get("name", "Unknown"),
                    "artists": ", ".join([artist.get("name", "") for artist in item.get("artists", [])]),
                    "album": item.get("album", {}).get("name", "Unknown"),
                    "cover": item.get("album", {}).get("images", [{}])[0].get("url", ""),
                    "url": item.get("external_urls", {}).get("spotify", ""),
                    "duration": f"{item.get('duration_ms', 0) // 60000}:{(item.get('duration_ms', 0) % 60000) // 1000:02d}"
                })
            
            return JSONResponse(
                content={
                    "status_code": 200,
                    "results": len(tracks),
                    "tracks": tracks,
                    "developer": "El Impaciente",
                    "telegram_channel": "https://t.me/Apisimpacientes"
                },
                status_code=200
            )
        
    except httpx.TimeoutException:
        return JSONResponse(
            content={
                "status_code": 408,
                "message": "Request timeout. The search took too long to respond",
                "developer": "El Impaciente",
                "telegram_channel": "https://t.me/Apisimpacientes"
            },
            status_code=408
        )
    except Exception as e:
        return JSONResponse(
            content={
                "status_code": 500,
                "message": "Error searching tracks",
                "error": str(e),
                "developer": "El Impaciente",
                "telegram_channel": "https://t.me/Apisimpacientes"
            },
            status_code=500
        )

@app.get("/health")
async def health_check():
    return JSONResponse(
        content={
            "status": "healthy",
            "service": "Spotify Downloader API - Vercel",
            "developer": "El Impaciente",
            "telegram_channel": "https://t.me/Apisimpacientes"
        },
        status_code=200
    )

app = app