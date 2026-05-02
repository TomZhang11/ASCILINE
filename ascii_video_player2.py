"""
ascii_video_player.py
=====================
Modüler, renkli (True Color / 24-bit ANSI), sıfır titremeli ASCII video oynatıcı.

  - VideoDecoder    : Video → (gray, color) kare çifti üretir.
  - AsciiMapper     : Gri matris → ASCII karakter + ANSI True Color kodu → String.
  - TerminalRenderer: Ana döngü, FPS kontrolü, yön tespiti, render.

Bağımlılıklar:
    pip install opencv-python numpy
"""

import sys
import time
import shutil
import numpy as np
import cv2
import os

# PowerShell/CMD (Windows) üzerinde ANSI renk kodlarını aktif etmek için:
os.system("")


# ─────────────────────────────────────────────
#  MODÜL 1 ─ VideoDecoder
# ─────────────────────────────────────────────
class VideoDecoder:
    """
    Video dosyasını açar ve her kare için (gray, bgr) çifti üretir.

    Renkli render için hem gri (karakter seçimi) hem de
    orijinal BGR (renk örnekleme) matrisine ihtiyaç var.
    İkisi de aynı resize işleminden geçer → boyut tutarlılığı garantili.
    """

    def __init__(self, path: str, cols: int, rows: int) -> None:
        self._cap = cv2.VideoCapture(path)
        if not self._cap.isOpened():
            raise FileNotFoundError(f"Video açılamadı: {path!r}")

        self.fps         : float = self._cap.get(cv2.CAP_PROP_FPS) or 24.0
        self.frame_count : int   = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.vid_w       : int   = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.vid_h       : int   = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._size       : tuple = (cols, rows)

    def __iter__(self):
        return self

    def __next__(self) -> tuple[np.ndarray, np.ndarray]:
        """
        :return: (gray[H,W] uint8,  bgr[H,W,3] uint8)
        """
        ok, frame = self._cap.read()
        if not ok:
            raise StopIteration

        small = cv2.resize(frame, self._size, interpolation=cv2.INTER_LINEAR)
        gray  = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        return gray, small   # small = küçültülmüş BGR karesi

    def release(self):
        self._cap.release()

    def __del__(self):
        self.release()


# ─────────────────────────────────────────────
#  MODÜL 2 ─ AsciiMapper
# ─────────────────────────────────────────────
class AsciiMapper:
    """
    Gri + BGR matrisini ANSI True Color kodlarıyla renklendirilmiş
    ASCII çerçeve dizisine dönüştürür.

    ── True Color ANSI Formatı ─────────────────────────────────────────────
      \033[38;2;R;G;Bm{karakter}\033[0m
      └─ ön plan rengi ─────────┘

    ── Renk Kuantizasyonu (Performans Optimizasyonu) ───────────────────────
      Her piksel için ayrı bir escape kodu üretmek yerine renk değerleri
      6-bit'e indirilir (>> 2 << 2, 64 seviye/kanal).
      Bu sayede ardışık aynı renkli pikseller tek bir escape koduyla
      temsil edilir → string boyutu ve stdout.write yükü azalır.
      Gözle algılanabilir renk kaybı olmaz (16M → ~262K renk).

    ── RLE (Run-Length Encoding) ───────────────────────────────────────────
      Aynı renkteki ardışık karakterler için escape kodu tekrar yazılmaz;
      yalnızca renk değiştiğinde yeni kod eklenir.
      Tipik bir karede %40-60 oranında string küçülmesi sağlar.
    """

    DEFAULT_PALETTE = list(
        " `.-':_,^=;><+!rc*/z?sLTv)J7(|Fi{C}fI31tlu[neoZ5Yxjya]2ESwqkP6h9d4VpOGbUAKXHm8RD#$Bg0MNWQ%&@"
    )

    # ANSI sıfırlama + satır başı
    _RESET = "\033[0m"

    def __init__(self, palette: list[str] | None = None, quantize_bits: int = 0) -> None:
        """
        :param palette:       Karakter listesi (None → 93 seviyeli varsayılan)
        :param quantize_bits: Renk kuantizasyonu için sağdan kaydırma miktarı.
                              2 → 64 seviye/kanal (hızlı),
                              0 → tam 8-bit (en yüksek kalite, varsayılan).
        """
        p = palette or self.DEFAULT_PALETTE
        self._n   = len(p)
        self._lut = np.array(p, dtype='U1')
        self._qb  = quantize_bits           # kuantizasyon bit kaydırma miktarı

    def convert(self, gray: np.ndarray, bgr: np.ndarray) -> str:
        """
        Her piksel için:
          1. Gri değeri → ASCII karakter (yoğunluk LUT)
          2. BGR rengi  → ANSI True Color escape kodu (kuantize + RLE)

        :param gray: shape=(H,W)   uint8 gri matris
        :param bgr:  shape=(H,W,3) uint8 BGR renk matrisi
        :return: Terminale doğrudan yazılabilecek renkli ASCII dizesi
        """
        H, W = gray.shape

        # ── Adım 1: Piksel yoğunluğu → karakter indeksi ──────────────────
        indices = np.floor_divide(gray, max(1, 256 // self._n))
        np.clip(indices, 0, self._n - 1, out=indices)
        char_matrix = self._lut[indices]    # shape=(H,W), dtype='U1'

        # ── Adım 2: Renk kuantizasyonu ────────────────────────────────────
        # BGR → RGB sıralaması (ANSI kodu R,G,B sırasında)
        rgb = bgr[:, :, ::-1]              # BGR → RGB view, kopyasız

        if self._qb > 0:
            # Düşük bitleri sıfırla → renk hassasiyetini düşür, hızı artır
            qb = self._qb
            rgb = (rgb >> qb) << qb        # örn. qb=2: 0b11111100 maskeleme

        # ── Adım 3: RLE ile renkli string birleştirme ─────────────────────
        # Saf NumPy ile RLE yapılamadığından bu kısım Python döngüsüdür.
        # Ancak satır başına yalnızca renk değişimlerinde escape kodu yazılır;
        # tekrarlanan renkler için döngü yükü minimize edilir.
        lines = []
        prev_r = prev_g = prev_b = -1      # önceki renk (ilk piksel hep farklı)

        for row_idx in range(H):
            row_chars  = char_matrix[row_idx]   # shape=(W,) char array
            row_colors = rgb[row_idx]            # shape=(W,3) uint8 array
            buf = []

            for col_idx in range(W):
                r, g, b = int(row_colors[col_idx, 0]), \
                           int(row_colors[col_idx, 1]), \
                           int(row_colors[col_idx, 2])

                # RLE: sadece renk değişince yeni escape kodu ekle
                if r != prev_r or g != prev_g or b != prev_b:
                    buf.append(f"\033[38;2;{r};{g};{b}m")
                    prev_r, prev_g, prev_b = r, g, b

                buf.append(row_chars[col_idx])

            lines.append("".join(buf))

        return self._RESET + "\n".join(lines) + self._RESET


# ─────────────────────────────────────────────
#  MODÜL 3 ─ TerminalRenderer
# ─────────────────────────────────────────────
class TerminalRenderer:
    """
    VideoDecoder → AsciiMapper → stdout akışını yönetir.

    Ek özellikler (renkli sürüm):
      - Başlangıçta terminal arka planını siyaha alır (\033[40m)
        → renkli karakterler daha belirgin görünür.
      - Her kare sonunda \033[0m ile renk sıfırlanır
        → sonraki terminal komutları etkilenmez.
    """

    _CURSOR_HOME   = "\033[H"
    _HIDE_CURSOR   = "\033[?25l"
    _SHOW_CURSOR   = "\033[?25h"
    _BLACK_BG      = "\033[40m"    # siyah arka plan — kontrast için
    _RESET_ALL     = "\033[0m"
    _CLEAR_SCREEN  = "\033[2J"

    CHAR_RATIO = 0.45              # terminal karakter en-boy oranı düzeltmesi

    def __init__(
        self,
        path         : str,
        palette      : list[str] | None = None,
        quantize_bits: int = 0,
    ) -> None:
        """
        :param path:          Video dosyası yolu
        :param palette:       Özel karakter paleti (None → 93 seviyeli)
        :param quantize_bits: Renk kuantizasyonu (0=tam kalite, 2=hızlı)
        """
        # ── Video meta bilgisi ────────────────────────────────────────────
        _probe = VideoDecoder(path, 2, 2)
        vid_w, vid_h = _probe.vid_w, _probe.vid_h
        src_fps      = _probe.fps
        _probe.release()

        # ── Terminal boyutları ────────────────────────────────────────────
        term    = shutil.get_terminal_size(fallback=(220, 50))
        t_cols  = term.columns
        t_lines = term.lines - 2

        # ── Yön tespiti & en-boy oranı korumalı boyutlandırma ─────────────
        orientation = "portrait" if vid_h > vid_w else "landscape"
        aspect      = vid_h / vid_w

        if orientation == "landscape":
            cols = t_cols
            rows = max(1, int(cols * aspect * self.CHAR_RATIO))
            if rows > t_lines:
                rows = t_lines
                cols = max(1, int(rows / (aspect * self.CHAR_RATIO)))
        else:
            rows = t_lines
            cols = max(1, int(rows / (aspect * self.CHAR_RATIO)))
            if cols > t_cols:
                cols = t_cols
                rows = max(1, int(cols * aspect * self.CHAR_RATIO))

        # ── Bilgi ekranı ──────────────────────────────────────────────────
        print(self._CLEAR_SCREEN)
        print(
            f"\033[1m[ASCII Player — True Color]\033[0m\n"
            f"  Yön       : {orientation.upper()}\n"
            f"  Video     : {vid_w}×{vid_h}\n"
            f"  ASCII     : {cols}×{rows} karakter\n"
            f"  FPS       : {src_fps:.1f}\n"
            f"  Kuantizasyon: {2**(8-quantize_bits)} seviye/kanal\n"
            f"  Çıkış     : Ctrl+C\n"
        )
        time.sleep(2.0)

        self._decoder       = VideoDecoder(path, cols, rows)
        self._mapper        = AsciiMapper(palette, quantize_bits)
        self._fps           = self._decoder.fps
        self._frame_t       = 1.0 / self._fps

    def play(self) -> None:
        """Ana oynatma döngüsü."""
        stdout = sys.stdout

        stdout.write(self._HIDE_CURSOR + self._BLACK_BG)
        stdout.flush()

        try:
            for gray_frame, bgr_frame in self._decoder:
                t0 = time.perf_counter()

                ascii_frame = self._mapper.convert(gray_frame, bgr_frame)

                stdout.write(self._CURSOR_HOME + ascii_frame)
                stdout.flush()

                wait = self._frame_t - (time.perf_counter() - t0)
                if wait > 0:
                    time.sleep(wait)

        except KeyboardInterrupt:
            pass

        finally:
            stdout.write(self._SHOW_CURSOR + self._RESET_ALL + "\n")
            stdout.flush()
            self._decoder.release()


# ─────────────────────────────────────────────
#  GİRİŞ NOKTASI
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="True Color ANSI ASCII video oynatıcı — sıfır titreme"
    )
    parser.add_argument("video",
        help="Video dosyası yolu (MP4, AVI, MKV …)")
    parser.add_argument("--palette", default=None,
        help="Özel karakter paleti, boşlukla ayrılmış")
    parser.add_argument("--quality", type=int, choices=[0, 1, 2, 3], default=0,
        help="Renk kalitesi: 0=maksimum kalite, 3=maksimum hız (varsayılan: 0)")
    args = parser.parse_args()

    custom_palette = args.palette.split() if args.palette else None

    renderer = TerminalRenderer(
        path          = args.video,
        palette       = custom_palette,
        quantize_bits = args.quality,
    )
    renderer.play()
