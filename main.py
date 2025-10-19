"""
Spotify Downloader API - Sistema Multi-API con Fallback Automático
Versión 3.0 - Octubre 2025

Desarrollado por: El Impaciente
Telegram: https://t.me/Apisimpacientes

Sistema inteligente que prueba múltiples APIs hasta encontrar una disponible
"""

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
from urllib.parse import quote
from typing import Optional, Dict, Any, List
import asyncio
from datetime import datetime

app = FastAPI(
    title="Spotify Downloader API - Multi-Source",
    description="Sistema inteligente con fallback automático entre múltiples APIs",
    version="3.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== CONFIGURACIÓN DE APIS ====================

# Lista de APIs disponibles (ordenadas por prioridad)
API_SOURCES = [
    {
        "name": "SpotifyDown Original",
        "base_url": "https://api.spotifydown.com",
        "metadata_endpoint": "/metadata/track/{track_id}",
        "download_endpoint": "/download/{track_id}",
        "priority": 1,
        "active": True
    },
    {
        "name": "Spotimate",
        "base_url": "https://spotimate.io/api",
        "metadata_endpoint": "/metadata/track/{track_id}",
        "download_endpoint": "/download/{track_id}",
        "priority": 2,
        "active": True
    },
    {
        "name": "SpotiDown Alternative",
        "base_url": "https://api.spotidown.com",
        "metadata_endpoint": "/metadata/track/{track_id}",
        "download_endpoint": "/download/{track_id}",
        "priority": 3,
        "active": True
    },
    {
        "name": "Spotify-Down Web",
        "base_url": "https://spotify-down.com/api",
        "metadata_endpoint": "/track/{track_id}",
        "download_endpoint": "/download/{track_id}",
        "priority": 4,
        "active": True
    },
    {
        "name": "SpotiDownloader",
        "base_url": "https://api.spotidownloader.com",
        "metadata_endpoint": "/metadata/{track_id}",
        "download_endpoint": "/download/{track_id}",
        "priority": 5,
        "active": True
    }
]

# Headers por defecto para las peticiones
DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Linux; Android 14; V2336 Build/UP1A.231005.007) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.135 Mobile Safari/537.36",
    "Accept": "application/json",
    "Origin": "https://spotifydown.com",
    "Referer": "https://spotifydown.com/"
}

# ==================== FUNCIONES AUXILIARES ====================

async def try_api_source(
    client: httpx.AsyncClient,
    source: Dict[str, Any],
    track_id: str,
    endpoint_type: str = "metadata"
) -> Dict[str, Any]:
    """
    Intenta obtener datos de una fuente API específica
    
    Args:
        client: Cliente HTTP
        source: Diccionario con información de la API
        track_id: ID de la canción de Spotify
        endpoint_type: Tipo de endpoint ("metadata" o "download")
    
    Returns:
        Diccionario con resultado de la operación
    """
    if not source.get("active", True):
        return {
            "success": False,
            "error": "API desactivada",
            "source": source["name"]
        }
    
    try:
        endpoint_key = f"{endpoint_type}_endpoint"
        endpoint = source.get(endpoint_key, "")
        url = source["base_url"] + endpoint.format(track_id=track_id)
        
        response = await client.get(
            url,
            headers=DEFAULT_HEADERS,
            timeout=15.0,
            follow_redirects=True
        )
        
        if response.status_code == 200:
            try:
                data = response.json()
                return {
                    "success": True,
                    "data": data,
                    "source": source["name"],
                    "response_time": response.elapsed.total_seconds()
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": f"JSON parse error: {str(e)}",
                    "source": source["name"]
                }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}",
                "source": source["name"]
            }
            
    except httpx.TimeoutException:
        return {
            "success": False,
            "error": "Timeout",
            "source": source["name"]
        }
    except httpx.ConnectError:
        return {
            "success": False,
            "error": "Connection error",
            "source": source["name"]
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "source": source["name"]
        }

async def fetch_with_fallback(
    track_id: str,
    endpoint_type: str = "metadata"
) -> Dict[str, Any]:
    """
    Intenta obtener datos usando múltiples fuentes con fallback automático
    
    Args:
        track_id: ID de la canción de Spotify
        endpoint_type: Tipo de endpoint a consultar
    
    Returns:
        Diccionario con los datos obtenidos o información de error
    """
    # Ordenar fuentes por prioridad
    sorted_sources = sorted(
        [s for s in API_SOURCES if s.get("active", True)],
        key=lambda x: x.get("priority", 999)
    )
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for source in sorted_sources:
            result = await try_api_source(client, source, track_id, endpoint_type)
            
            if result.get("success"):
                return result
        
        # Si todas fallan
        return {
            "success": False,
            "error": "All API sources failed",
            "attempted_sources": [s["name"] for s in sorted_sources],
            "total_sources": len(sorted_sources)
        }

async def get_spotify_metadata(track_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene metadata oficial de Spotify usando su API
    
    Args:
        track_id: ID de la canción
    
    Returns:
        Diccionario con metadata o None si falla
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Obtener token
            token_response = await client.post(
                "https://accounts.spotify.com/api/token",
                data={"grant_type": "client_credentials"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                auth=("anonymous", "anonymous")
            )
            
            if token_response.status_code != 200:
                return None
            
            access_token = token_response.json().get("access_token", "")
            
            # Obtener metadata
            track_response = await client.get(
                f"https://api.spotify.com/v1/tracks/{track_id}",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if track_response.status_code == 200:
                return track_response.json()
            
            return None
            
    except Exception:
        return None

def format_duration(duration_ms: int) -> str:
    """Formatea duración de milisegundos a MM:SS"""
    minutes = duration_ms // 60000
    seconds = (duration_ms % 60000) // 1000
    return f"{minutes}:{seconds:02d}"

# ==================== ENDPOINTS ====================

@app.get("/")
async def root():
    """Endpoint raíz con información de la API"""
    active_sources = [s["name"] for s in API_SOURCES if s.get("active", True)]
    
    return JSONResponse(
        content={
            "status_code": 200,
            "message": "🎵 Spotify Downloader API - Sistema Multi-Source v3.0",
            "version": "3.0",
            "system": "Multi-API con fallback automático",
            "developer": "El Impaciente",
            "telegram_channel": "https://t.me/Apisimpacientes",
            "features": [
                "✅ Sistema de fallback entre múltiples APIs",
                "✅ Detección automática de APIs disponibles",
                "✅ Metadata oficial de Spotify",
                "✅ Búsqueda de canciones",
                "✅ Verificación de estado de APIs"
            ],
            "active_sources": active_sources,
            "total_sources": len(API_SOURCES),
            "endpoints": {
                "/download": "Descargar track - Uso: /download?url=SPOTIFY_URL",
                "/search": "Buscar tracks - Uso: /search?query=CANCION",
                "/metadata": "Obtener metadata - Uso: /metadata?url=SPOTIFY_URL",
                "/check-sources": "Verificar estado de todas las APIs",
                "/health": "Estado de salud de la API"
            },
            "timestamp": datetime.utcnow().isoformat()
        },
        status_code=200
    )

@app.get("/download")
async def download_track(url: str = Query(default="", description="Spotify track URL")):
    """
    Endpoint principal para descargar tracks
    Intenta múltiples APIs hasta encontrar una que funcione
    """
    if not url or url.strip() == "":
        return JSONResponse(
            content={
                "status_code": 400,
                "message": "Parameter 'url' is required",
                "developer": "El Impaciente",
                "telegram_channel": "https://t.me/Apisimpacientes",
                "example": "/download?url=https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp"
            },
            status_code=400
        )
    
    try:
        # Extraer track ID
        track_id = url.split('/')[-1].split('?')[0]
        
        # Obtener metadata oficial de Spotify (siempre disponible)
        spotify_metadata = await get_spotify_metadata(track_id)
        
        if not spotify_metadata:
            return JSONResponse(
                content={
                    "status_code": 404,
                    "message": "Track not found on Spotify",
                    "developer": "El Impaciente",
                    "telegram_channel": "https://t.me/Apisimpacientes"
                },
                status_code=404
            )
        
        # Intentar obtener enlace de descarga con fallback
        download_result = await fetch_with_fallback(track_id, "download")
        
        if not download_result.get("success"):
            # Si todas las APIs de descarga fallan
            return JSONResponse(
                content={
                    "status_code": 503,
                    "message": "⚠️ Todas las fuentes de descarga están temporalmente no disponibles",
                    "track_info": {
                        "title": spotify_metadata.get("name", "Unknown"),
                        "artists": ", ".join([a.get("name", "") for a in spotify_metadata.get("artists", [])]),
                        "album": spotify_metadata.get("album", {}).get("name", "Unknown"),
                        "cover": spotify_metadata.get("album", {}).get("images", [{}])[0].get("url", "")
                    },
                    "attempted_sources": download_result.get("attempted_sources", []),
                    "suggestion": "Las APIs externas están caídas. Intenta de nuevo en unos minutos.",
                    "alternative": "Considera usar spotDL: https://github.com/spotDL/spotify-downloader",
                    "developer": "El Impaciente",
                    "telegram_channel": "https://t.me/Apisimpacientes"
                },
                status_code=503
            )
        
        # Construir respuesta exitosa
        download_data = download_result.get("data", {})
        download_url = download_data.get("link", "") or download_data.get("download_url", "") or download_data.get("url", "")
        
        duration_ms = spotify_metadata.get("duration_ms", 0)
        
        return JSONResponse(
            content={
                "status_code": 200,
                "title": spotify_metadata.get("name", "Unknown"),
                "artists": ", ".join([a.get("name", "") for a in spotify_metadata.get("artists", [])]),
                "album": spotify_metadata.get("album", {}).get("name", "Unknown"),
                "cover": spotify_metadata.get("album", {}).get("images", [{}])[0].get("url", ""),
                "duration": format_duration(duration_ms),
                "release_date": spotify_metadata.get("album", {}).get("release_date", "Unknown"),
                "explicit": spotify_metadata.get("explicit", False),
                "popularity": spotify_metadata.get("popularity", 0),
                "download_url": download_url,
                "source_used": download_result.get("source", "Unknown"),
                "response_time": f"{download_result.get('response_time', 0):.2f}s",
                "developer": "El Impaciente",
                "telegram_channel": "https://t.me/Apisimpacientes"
            },
            status_code=200
        )
        
    except httpx.TimeoutException:
        return JSONResponse(
            content={
                "status_code": 408,
                "message": "Request timeout",
                "developer": "El Impaciente",
                "telegram_channel": "https://t.me/Apisimpacientes"
            },
            status_code=408
        )
    except Exception as e:
        return JSONResponse(
            content={
                "status_code": 500,
                "message": "Error processing track",
                "error": str(e),
                "developer": "El Impaciente",
                "telegram_channel": "https://t.me/Apisimpacientes"
            },
            status_code=500
        )

@app.get("/metadata")
async def get_metadata(url: str = Query(default="", description="Spotify track URL")):
    """
    Obtiene solo la metadata de un track sin descargarlo
    Útil para previsualización
    """
    if not url or url.strip() == "":
        return JSONResponse(
            content={
                "status_code": 400,
                "message": "Parameter 'url' is required",
                "developer": "El Impaciente",
                "telegram_channel": "https://t.me/Apisimpacientes",
                "example": "/metadata?url=https://open.spotify.com/track/TRACK_ID"
            },
            status_code=400
        )
    
    try:
        track_id = url.split('/')[-1].split('?')[0]
        spotify_metadata = await get_spotify_metadata(track_id)
        
        if not spotify_metadata:
            return JSONResponse(
                content={
                    "status_code": 404,
                    "message": "Track not found",
                    "developer": "El Impaciente",
                    "telegram_channel": "https://t.me/Apisimpacientes"
                },
                status_code=404
            )
        
        return JSONResponse(
            content={
                "status_code": 200,
                "title": spotify_metadata.get("name", "Unknown"),
                "artists": ", ".join([a.get("name", "") for a in spotify_metadata.get("artists", [])]),
                "album": spotify_metadata.get("album", {}).get("name", "Unknown"),
                "cover": spotify_metadata.get("album", {}).get("images", [{}])[0].get("url", ""),
                "duration": format_duration(spotify_metadata.get("duration_ms", 0)),
                "release_date": spotify_metadata.get("album", {}).get("release_date", "Unknown"),
                "explicit": spotify_metadata.get("explicit", False),
                "popularity": spotify_metadata.get("popularity", 0),
                "preview_url": spotify_metadata.get("preview_url", None),
                "spotify_url": url,
                "developer": "El Impaciente",
                "telegram_channel": "https://t.me/Apisimpacientes"
            },
            status_code=200
        )
        
    except Exception as e:
        return JSONResponse(
            content={
                "status_code": 500,
                "message": "Error fetching metadata",
                "error": str(e),
                "developer": "El Impaciente",
                "telegram_channel": "https://t.me/Apisimpacientes"
            },
            status_code=500
        )

@app.get("/search")
async def search_track(query: str = Query(default="", description="Search query")):
    """
    Busca tracks en Spotify
    """
    if not query or query.strip() == "":
        return JSONResponse(
            content={
                "status_code": 400,
                "message": "Parameter 'query' is required",
                "developer": "El Impaciente",
                "telegram_channel": "https://t.me/Apisimpacientes",
                "example": "/search?query=bohemian rhapsody"
            },
            status_code=400
        )
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Obtener token
            token_response = await client.post(
                "https://accounts.spotify.com/api/token",
                data={"grant_type": "client_credentials"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
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
            
            # Buscar
            search_response = await client.get(
                f"https://api.spotify.com/v1/search?q={quote(query)}&type=track&limit=10",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
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
                    "artists": ", ".join([a.get("name", "") for a in item.get("artists", [])]),
                    "album": item.get("album", {}).get("name", "Unknown"),
                    "cover": item.get("album", {}).get("images", [{}])[0].get("url", ""),
                    "url": item.get("external_urls", {}).get("spotify", ""),
                    "duration": format_duration(item.get("duration_ms", 0)),
                    "popularity": item.get("popularity", 0),
                    "explicit": item.get("explicit", False)
                })
            
            return JSONResponse(
                content={
                    "status_code": 200,
                    "query": query,
                    "results": len(tracks),
                    "tracks": tracks,
                    "developer": "El Impaciente",
                    "telegram_channel": "https://t.me/Apisimpacientes"
                },
                status_code=200
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

@app.get("/check-sources")
async def check_sources():
    """
    Verifica el estado de todas las fuentes API
    Útil para monitoreo y debugging
    """
    results = []
    
    # Track ID de prueba (canción popular)
    test_track_id = "3n3Ppam7vgaVa1iaRUc9Lp"  # Mr. Brightside - The Killers
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        for source in API_SOURCES:
            if not source.get("active", True):
                results.append({
                    "name": source["name"],
                    "priority": source.get("priority", 999),
                    "status": "disabled",
                    "metadata_available": False,
                    "download_available": False
                })
                continue
            
            # Probar metadata
            metadata_result = await try_api_source(client, source, test_track_id, "metadata")
            
            # Probar download
            download_result = await try_api_source(client, source, test_track_id, "download")
            
            results.append({
                "name": source["name"],
                "priority": source.get("priority", 999),
                "base_url": source["base_url"],
                "metadata_available": metadata_result.get("success", False),
                "metadata_error": metadata_result.get("error") if not metadata_result.get("success") else None,
                "metadata_response_time": metadata_result.get("response_time"),
                "download_available": download_result.get("success", False),
                "download_error": download_result.get("error") if not download_result.get("success") else None,
                "download_response_time": download_result.get("response_time"),
                "status": "✅ online" if download_result.get("success") else "❌ offline"
            })
    
    # Ordenar por prioridad
    results.sort(key=lambda x: x.get("priority", 999))
    
    available_sources = [r for r in results if r["download_available"]]
    
    return JSONResponse(
        content={
            "status_code": 200,
            "timestamp": datetime.utcnow().isoformat(),
            "total_sources": len(API_SOURCES),
            "available_sources": len(available_sources),
            "offline_sources": len(results) - len(available_sources),
            "sources": results,
            "recommendation": (
                f"✅ Usando: {available_sources[0]['name']}" if available_sources 
                else "⚠️ Todas las fuentes están caídas - considera usar spotDL"
            ),
            "developer": "El Impaciente",
            "telegram_channel": "https://t.me/Apisimpacientes"
        },
        status_code=200
    )

@app.get("/health")
async def health_check():
    """
    Health check endpoint
    Verifica el estado general de la API
    """
    active_sources = [s for s in API_SOURCES if s.get("active", True)]
    
    return JSONResponse(
        content={
            "status": "healthy",
            "service": "Spotify Downloader API - Multi-Source",
            "version": "3.0",
            "system": "Multi-API Fallback System",
            "total_sources": len(API_SOURCES),
            "active_sources": len(active_sources),
            "timestamp": datetime.utcnow().isoformat(),
            "developer": "El Impaciente",
            "telegram_channel": "https://t.me/Apisimpacientes"
        },
        status_code=200
    )

# Entry point para Vercel
app = app
