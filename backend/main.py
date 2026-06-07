import asyncio
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from twitchio.ext import commands
from google import genai
import re
import requests 
import os
import json # for twitch chat overlay


# Store active websocket connections
active_connections = []

# Initialize Gemini (Replace with your actual API key)
gemini_client = genai.Client(api_key="YOUR_API_KEY")

# 2. Setup the Twitch Bot
class AikoBot(commands.Bot):
    def __init__(self):
        super().__init__(token='', prefix='!', initial_channels=['ur_aik0'])

    async def event_ready(self):
        print(f'Aiko is online and reading chat as | {self.nick}')

    async def event_message(self, message):
        if message.echo: return # Ignore own messages
        
        print(f"Chat: {message.author.name}: {message.content}")

        # Send to Gemini
        try:
            response = gemini_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=f"You are Aiko, a cute, slightly mischievous AI VTuber. Keep your response under 2 sentences. Respond to {message.author.name} who said: {message.content}"
            )

            reply_text = response.text or "*smiles quietly*"
            print(f"Aiko: {reply_text}")

        # NEW: Clean the tags out before sending to Text-to-Speech
            spoken_text = re.sub(r'\[.*?\]', '', reply_text).strip()
            
            if not spoken_text:
                spoken_text = "Tch."

            # ==========================================
            # FISH AUDIO INTEGRATION
            # ==========================================
            FISH_API_KEY = ""
            VOICE_MODEL_ID = "" 
            
            # Send the text to Fish Audio
            print("Generating emotional voice...")
            fish_url = "https://api.fish.audio/v1/tts"
            headers = {
                "Authorization": f"Bearer {FISH_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "text": spoken_text,
                "reference_id": VOICE_MODEL_ID,
                "format": "mp3"
            }
            
            audio_response = requests.post(fish_url, json=payload, headers=headers)
            
            # Save the MP3 if successful
            if audio_response.status_code == 200:
                with open("aiko_response.mp3", "wb") as f:
                    f.write(audio_response.content)
            else:
                print(f"Fish Audio Error: {audio_response.text}")
            # ==========================================

            # Push audio alert to frontend
            import json # Make sure to add 'import json' at the top of main.py

            for connection in active_connections:
                await connection.send_json({
                    "action": "play_audio",
                    "chatter": message.author.name,
                    "chat_message": message.content,
                    "aiko_reply": reply_text
                })
            
        except Exception as e:
            print(f"Error processing message: {e}")

# Create an empty placeholder for the bot
bot = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot
    # Initialize the bot INSIDE the correct Uvicorn event loop
    bot = AikoBot() 
    asyncio.create_task(bot.start())
    yield
    # Safely shut down the bot when you close the server
    if bot:
        await bot.close()

app = FastAPI(lifespan=lifespan)

# 3. FastAPI Web Routes
@app.get("/")
async def get():
    # Serve the HTML page
    with open("index.html", "r") as f:
        return HTMLResponse(f.read())

@app.get("/audio")
async def get_audio():
    # Serve the generated audio file
    return FileResponse("aiko_response.mp3", media_type="audio/mpeg")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except:
        active_connections.remove(websocket)

# 4. Start the Bot alongside the Web Server
# Modern FastAPI Lifespan setup
