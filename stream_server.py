"""
stream_server.py
================
Video to ASCII çekirdek motorunu HTTP/WebSocket üzerinden web'e yayınlar.
Bağımlılıklar: pip install fastapi uvicorn websockets
"""

import asyncio
import numpy as np
import cv2
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import os
from websockets.exceptions import ConnectionClosed

# Mevcut motoru import ediyoruz (ascii_video_player2.py)
from ascii_video_player2 import VideoDecoder, AsciiMapper

app = FastAPI()

# Serve static files (style.css, app.js) from the project directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=BASE_DIR), name="static")

def get_html_content():
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/")
async def root():
    """İstemciye Frontend (HTML/JS/CSS) dosyasını sunar."""
    return HTMLResponse(get_html_content())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    İstemci bağlandığında videoyu decode etmeye başlar, 
    AsciiMapper ile saf ASCII'ye çevirir ve WebSockets üzerinden gönderir.
    """
    await websocket.accept()
    
    video_path = getattr(app.state, "video_path", "video.mp4")
    render_mode = getattr(app.state, "render_mode", 1)
    cols = getattr(app.state, "cols", 200)
    rows = getattr(app.state, "rows", 80)
    
    try:
        decoder = VideoDecoder(video_path, cols, rows)
    except FileNotFoundError:
        await websocket.send_text("Hata: Video dosyası bulunamadı!")
        await websocket.close()
        return

    mapper = AsciiMapper()
    fps = decoder.fps
    frame_t = 1.0 / fps
    
    # Karakter → byte kodu lookup tablosu (binary format için)
    char_byte_lut = np.array([ord(c) for c in mapper._lut], dtype=np.uint8)
    
    # Kuantizasyon seviyesini bir kere belirle (render_mode sabit)
    qb = {5: 0, 4: 2, 3: 3, 2: 5}.get(render_mode, 0)
    
    # İstemciye meta bilgilerini yolla (cols/rows grid oluşturmak için)
    await websocket.send_text(f"INIT:{fps}:{render_mode}:{cols}:{rows}")

    try:
        # Decoder iteratörü her kare için (gray, bgr) döndürüyor
        # Binary frame buffer'ı önceden ayır (GC baskısını azalt)
        frame_buf = np.empty((rows, cols, 4), dtype=np.uint8) if render_mode > 1 else None
        
        for gray_frame, bgr_frame in decoder:
            t0 = asyncio.get_event_loop().time()
            
            # Ortak: yoğunluk → karakter indeksi
            indices = np.floor_divide(gray_frame, max(1, 256 // mapper._n))
            np.clip(indices, 0, mapper._n - 1, out=indices)
            
            if render_mode == 1:
                # --- SAF ASCII DÖNÜŞÜMÜ (text) ---
                char_matrix = mapper._lut[indices]
                lines = [''.join(row) for row in char_matrix]
                await websocket.send_text('\n'.join(lines))
            else:
                # --- RENKLİ BINARY DÖNÜŞÜMÜ (numpy, sıfır Python döngüsü) ---
                H, W = gray_frame.shape
                char_codes = char_byte_lut[indices]   # (H,W) uint8
                
                rgb = bgr_frame[:, :, ::-1]           # BGR → RGB
                if qb > 0:
                    rgb = (rgb >> qb) << qb
                
                # [char, R, G, B] interleaved binary frame
                frame_buf[:, :, 0] = char_codes
                frame_buf[:, :, 1:] = rgb
                
                await websocket.send_bytes(frame_buf.tobytes())
                
            elapsed = asyncio.get_event_loop().time() - t0
            wait = frame_t - elapsed
            if wait > 0:
                await asyncio.sleep(wait)
                
    except (WebSocketDisconnect, ConnectionClosed):
        print("İstemci yayından ayrıldı.")
    finally:
        decoder.release()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Gerçek Zamanlı ASCII Web Sunucusu")
    parser.add_argument("video", help="Yayınlanacak video dosyası", default="video.mp4", nargs='?')
    parser.add_argument("--port", type=int, default=8000, help="Sunucu portu")
    parser.add_argument("--mode", type=int, choices=[1, 2, 3, 4, 5], default=1, help="Render Modu: 1=B&W, 2=512renk, 3=32K, 4=262K, 5=16M Ultra")
    parser.add_argument("--cols", type=int, default=200, help="Terminal kolon genişliği")
    parser.add_argument("--rows", type=int, default=80, help="Terminal satır yüksekliği")
    args = parser.parse_args()
    
    # Argümanları global olarak state içine kaydet
    app.state.video_path = args.video
    app.state.render_mode = args.mode
    app.state.cols = args.cols
    app.state.rows = args.rows
    
    print(f"[{args.video}] yayınlanmaya hazır. Mod: {args.mode}, Çöz: {args.cols}x{args.rows}")
    print(f"Sunucu başlatılıyor... Lütfen tarayıcınızdan http://localhost:{args.port} adresine gidin.")
    
    uvicorn.run(app, host="0.0.0.0", port=args.port, ws_ping_interval=None, ws_ping_timeout=None)
