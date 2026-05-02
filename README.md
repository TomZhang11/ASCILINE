# 🌌 ASCILINE Engine

**ASCILINE** is a high-performance, real-time ASCII video rendering engine for the web. It streams video frames from a Python backend directly into a web browser at **60 FPS** using binary WebSockets and HTML5 Canvas.

![ASCILINE Showcase](https://via.placeholder.com/800x450.png?text=Add+Your+Amazing+ASCII+GIF+Here) <!-- Replace with your actual GIF -->

## 🚀 Key Features

-   **Real-Time Streaming**: Low-latency video-to-ASCII conversion.
-   **High Performance**: Uses **HTML5 Canvas** for rendering instead of heavy DOM elements, enabling 60 FPS playback.
-   **Binary Protocol**: Frames are encoded into `Uint8Array` (binary) for efficient bandwidth usage.
-   **Multiple Color Modes**: Supports everything from classic B&W to 16M color ultra-fidelity.
-   **Modern Aesthetic**: Premium dark-mode UI with interactive ripple dissolve effects.

## 🛠️ Architecture

1.  **Backend (Python/FastAPI)**: Decodes video using OpenCV, maps pixels to ASCII characters via NumPy, and streams binary data.
2.  **Frontend (Vanilla JS)**: Receives binary frames via WebSockets, manages a jitter buffer, and renders to a Canvas grid.
3.  **Communication**: Optimized WebSocket protocol with a custom `INIT` handshake for dynamic resolution/FPS adjustment.

## 📦 Installation

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/ASCILINE.git
cd ASCILINE
```

### 2. Install dependencies
```bash
pip install fastapi uvicorn opencv-python numpy websockets
```

### 3. Run the engine
Place a `video.mp4` in the root directory and start the server:
```bash
python stream_server.py
```
Open `http://localhost:8000` in your browser.

## 🎨 Customization

You can easily customize the look and feel of the engine:

### Styling
Edit `style.css` to change the accent colors and typography using CSS variables:
```css
:root {
    --accent-color: #00ff41; /* Classic Matrix Green */
    --bg-color: #050505;
}
```

### Rendering Modes
The engine supports different fidelity levels via the `--mode` flag:
- `1`: Black & White (DOM mode)
- `2`: 512 Colors
- `3`: 32K Colors
- `4`: 262K Colors
- `5`: 16M Colors (Ultra)

```bash
python stream_server.py --mode 5 --cols 240 --rows 100
```

## 📜 License
MIT License. Feel free to use and abuse for your own ASCII adventures!
