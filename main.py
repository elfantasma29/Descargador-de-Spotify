from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
import base64
import re
from datetime import datetime
from typing import List, Dict, Any
import time
from collections import deque

app = FastAPI(title="Gemini TTS API - Multi-Speaker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"

VOICES = [
    'Kore', 'Puck', 'Charon', 'Leda', 'Achernar', 'Aoede', 'Autonoe',
    'Callirrhoe', 'Despina', 'Erinome', 'Gacrux', 'Laomedeia',
    'Pulcherrima', 'Sulafat', 'Vindemiatrix', 'Zephyr', 'Achird',
    'Algenib', 'Algieba', 'Alnilam', 'Enceladus', 'Fenrir', 'Iapetus',
    'Orus', 'Rasalgethi', 'Sadachbia', 'Sadaltager', 'Schedar',
    'Umbriel', 'Zubenelgenubi'
]

class RateLimiter:
    def __init__(self, rpm: int = 5, max_concurrent: int = 3):
        self.rpm = rpm
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.request_times = deque()
        self.lock = asyncio.Lock()
    
    async def acquire(self):
        async with self.lock:
            now = time.time()
            while self.request_times and self.request_times[0] < now - 60:
                self.request_times.popleft()
            
            if len(self.request_times) >= self.rpm:
                sleep_time = 60 - (now - self.request_times[0])
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    return await self.acquire()
            
            self.request_times.append(now)
        
        await self.semaphore.acquire()
    
    def release(self):
        self.semaphore.release()

rate_limiter = RateLimiter(rpm=5, max_concurrent=3)

def parse_text_to_segments(text: str) -> List[Dict[str, str]]:
    voice_regex = re.compile(r'\{\{@(\w+)\}\}')
    segments = []
    last_index = 0
    current_voice = None
    
    for match in voice_regex.finditer(text):
        voice_name = match.group(1)
        
        if voice_name not in VOICES:
            continue
        
        if current_voice and last_index < match.start():
            content = text[last_index:match.start()].strip()
            if content:
                segments.append({
                    'voice': current_voice,
                    'text': re.sub(r'\s+', ' ', content)
                })
        
        current_voice = voice_name
        last_index = match.end()
    
    if current_voice and last_index < len(text):
        content = text[last_index:].strip()
        if content:
            segments.append({
                'voice': current_voice,
                'text': re.sub(r'\s+', ' ', content)
            })
    
    return segments

def group_segments_by_voice_pairs(segments: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    if not segments:
        return []
    
    groups = []
    voices_in_group = set()
    current_group = []
    
    for segment in segments:
        if segment['voice'] in voices_in_group:
            current_group.append(segment)
        elif len(voices_in_group) < 2:
            voices_in_group.add(segment['voice'])
            current_group.append(segment)
        else:
            groups.append({
                'segments': current_group,
                'voices': list(voices_in_group)
            })
            voices_in_group = {segment['voice']}
            current_group = [segment]
    
    if current_group:
        groups.append({
            'segments': current_group,
            'voices': list(voices_in_group)
        })
    
    return groups

def format_group_for_api(group: Dict[str, Any]) -> str:
    text_parts = []
    for segment in group['segments']:
        text_parts.append(f"{segment['voice']}: {segment['text']}")
    return '\n'.join(text_parts)

async def generate_audio_for_group(api_key: str, group: Dict[str, Any], group_index: int) -> Dict[str, Any]:
    conversation_text = format_group_for_api(group)
    
    speaker_voice_configs = [
        {
            "speaker": voice_name,
            "voiceConfig": {
                "prebuiltVoiceConfig": {
                    "voiceName": voice_name
                }
            }
        }
        for voice_name in group['voices']
    ]
    
    payload = {
        "contents": [{
            "parts": [{
                "text": conversation_text
            }]
        }],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "multiSpeakerVoiceConfig": {
                    "speakerVoiceConfigs": speaker_voice_configs
                }
            }
        }
    }
    
    await rate_limiter.acquire()
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{GEMINI_API_URL}?key={api_key}",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code != 200:
                error_data = response.json() if response.text else {}
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Gemini API error: {error_data.get('error', {}).get('message', 'Unknown error')}"
                )
            
            data = response.json()
            
            if not data.get('candidates') or not data['candidates'][0].get('content'):
                raise HTTPException(status_code=500, detail="Invalid API response structure")
            
            audio_data = data['candidates'][0]['content']['parts'][0]['inlineData']['data']
            
            return {
                'success': True,
                'audio_data': audio_data,
                'group_index': group_index
            }
    
    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail=f"Timeout generating audio for group {group_index + 1}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Network error: {str(e)}")
    finally:
        rate_limiter.release()

def extract_pcm_data(base64_audio: str) -> bytes:
    return base64.b64decode(base64_audio)

def concatenate_pcm_data(pcm_arrays: List[bytes]) -> bytes:
    return b''.join(pcm_arrays)

def add_wav_header(pcm_data: bytes, sample_rate: int = 24000, channels: int = 1, bits_per_sample: int = 16) -> bytes:
    data_size = len(pcm_data)
    file_size = 36 + data_size
    byte_rate = sample_rate * channels * (bits_per_sample // 8)
    block_align = channels * (bits_per_sample // 8)
    
    header = bytearray(44)
    
    header[0:4] = b'RIFF'
    header[4:8] = file_size.to_bytes(4, 'little')
    header[8:12] = b'WAVE'
    header[12:16] = b'fmt '
    header[16:20] = (16).to_bytes(4, 'little')
    header[20:22] = (1).to_bytes(2, 'little')
    header[22:24] = channels.to_bytes(2, 'little')
    header[24:28] = sample_rate.to_bytes(4, 'little')
    header[28:32] = byte_rate.to_bytes(4, 'little')
    header[32:34] = block_align.to_bytes(2, 'little')
    header[34:36] = bits_per_sample.to_bytes(2, 'little')
    header[36:40] = b'data'
    header[40:44] = data_size.to_bytes(4, 'little')
    
    return bytes(header) + pcm_data

@app.get("/")
async def root():
    return JSONResponse(
        content={
            "status_code": 200,
            "service": "Gemini TTS API - Multi-Speaker",
            "version": "1.0.0",
            "endpoints": {
                "/generate": "POST - Generate multi-speaker audio",
                "/voices": "GET - List available voices",
                "/health": "GET - Check API health"
            },
            "features": [
                "Multi-speaker TTS (unlimited speakers)",
                "Parallel audio generation",
                "Intelligent rate limiting",
                "Compatible with old HTTP clients",
                "WAV audio output"
            ],
            "supported_voices": len(VOICES),
            "max_speakers_per_request": "Unlimited (grouped in pairs)"
        },
        status_code=200
    )

@app.get("/voices")
async def get_voices():
    return JSONResponse(
        content={
            "status_code": 200,
            "total_voices": len(VOICES),
            "voices": VOICES,
            "usage": "Use {{@VoiceName}} in your text to specify speaker"
        },
        status_code=200
    )

@app.post("/generate")
async def generate_audio(
    text: str = Query(..., description="Text with voice tags {{@VoiceName}}"),
    api_key: str = Query(..., description="Your Gemini API key"),
    format: str = Query(default="wav", description="Output format: wav or base64")
):
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Parameter 'text' is required")
    
    if not api_key or not api_key.strip():
        raise HTTPException(status_code=400, detail="Parameter 'api_key' is required")
    
    try:
        segments = parse_text_to_segments(text)
        
        if not segments:
            raise HTTPException(
                status_code=400,
                detail="No valid voice tags found. Use {{@VoiceName}} format"
            )
        
        groups = group_segments_by_voice_pairs(segments)
        total_groups = len(groups)
        
        tasks = [
            generate_audio_for_group(api_key, group, i)
            for i, group in enumerate(groups)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        pcm_arrays = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                raise HTTPException(
                    status_code=500,
                    detail=f"Error generating audio for group {i + 1}: {str(result)}"
                )
            
            pcm_data = extract_pcm_data(result['audio_data'])
            pcm_arrays.append(pcm_data)
        
        concatenated_pcm = concatenate_pcm_data(pcm_arrays)
        wav_data = add_wav_header(concatenated_pcm)
        
        if format.lower() == "base64":
            audio_base64 = base64.b64encode(wav_data).decode('utf-8')
            return JSONResponse(
                content={
                    "status_code": 200,
                    "success": True,
                    "audio_base64": audio_base64,
                    "format": "wav",
                    "total_groups": total_groups,
                    "total_voices": len(set(seg['voice'] for seg in segments)),
                    "duration_estimate": round(len(wav_data) / (24000 * 2), 2)
                },
                status_code=200
            )
        else:
            return Response(
                content=wav_data,
                media_type="audio/wav",
                headers={
                    "Content-Disposition": f'attachment; filename="audio_{int(time.time())}.wav"',
                    "Content-Length": str(len(wav_data))
                }
            )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )

@app.get("/health")
async def health_check():
    return JSONResponse(
        content={
            "status": "healthy",
            "service": "Gemini TTS API - Multi-Speaker",
            "timestamp": datetime.utcnow().isoformat(),
            "rate_limiter": {
                "rpm": rate_limiter.rpm,
                "max_concurrent": rate_limiter.max_concurrent,
                "current_requests": len(rate_limiter.request_times)
            }
        },
        status_code=200
    )

app = app
