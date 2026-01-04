#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║            Shank 2 KTEX Universal Converter V4 - Final Edition               ║
║                                                                              ║
║   Supports ALL KTEX variants:                                                ║
║   • Version 1: No mipmaps (18-byte header)                                   ║
║   • Version 5: Compact mipmaps (10-byte header)                              ║
║   • Version 8: Full mipmaps (88-byte header)                                 ║
║                                                                              ║
║   Auto-detection • Batch processing • High quality encoding                  ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import struct
import sys
import json
import time
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
from enum import IntEnum
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("ERROR: Pillow required. Install with: pip install Pillow")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
#                              CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

KTEX_MAGIC = b'KTEX'

class DXTFormat(IntEnum):
    DXT1 = 0  # 8 bytes per block
    DXT3 = 1  # 16 bytes per block
    DXT5 = 2  # 16 bytes per block
    
    @property
    def block_size(self) -> int:
        return 8 if self == DXTFormat.DXT1 else 16
    
    @property
    def name_str(self) -> str:
        return f"DXT{5 if self == 2 else 3 if self == 1 else 1}"

class KTEXVersion(IntEnum):
    NO_MIPMAPS = 1       # 18-byte header, single level
    COMPACT_MIPMAPS = 5  # 10-byte header, mipmaps embedded
    FULL_MIPMAPS = 8     # 88-byte header, mipmap table

# Lookup tables for fast RGB565 conversion
RGB565_R = tuple((i * 255 + 15) // 31 for i in range(32))
RGB565_G = tuple((i * 255 + 31) // 63 for i in range(64))
RGB565_B = tuple((i * 255 + 15) // 31 for i in range(32))


# ══════════════════════════════════════════════════════════════════════════════
#                              DATA STRUCTURES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class MipmapInfo:
    level: int
    width: int
    height: int
    size: int
    offset: int

@dataclass
class KTEXInfo:
    """Complete KTEX file information"""
    version: int
    format: DXTFormat
    width: int
    height: int
    header_size: int
    has_mipmaps: bool
    mipmap_count: int
    mipmaps: List[MipmapInfo]
    raw_header: bytes
    
    def to_dict(self) -> dict:
        return {
            'version': self.version,
            'format': self.format.name_str,
            'format_id': int(self.format),
            'width': self.width,
            'height': self.height,
            'header_size': self.header_size,
            'has_mipmaps': self.has_mipmaps,
            'mipmap_count': self.mipmap_count
        }

@dataclass
class ConversionResult:
    success: bool
    input_path: Path
    output_path: Optional[Path] = None
    error: Optional[str] = None
    duration: float = 0.0


# ══════════════════════════════════════════════════════════════════════════════
#                              UTILITY FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

@lru_cache(maxsize=65536)
def rgb565_to_rgb(c: int) -> Tuple[int, int, int]:
    """Convert RGB565 to RGB888"""
    return (RGB565_R[(c >> 11) & 0x1F],
            RGB565_G[(c >> 5) & 0x3F],
            RGB565_B[c & 0x1F])

@lru_cache(maxsize=262144)
def rgb_to_rgb565(r: int, g: int, b: int) -> int:
    """Convert RGB888 to RGB565"""
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)

def calculate_mipmap_chain(width: int, height: int, fmt: DXTFormat) -> Tuple[List[MipmapInfo], int]:
    """Calculate all mipmap levels"""
    mipmaps = []
    total = 0
    w, h = width, height
    level = 0
    
    while w >= 1 and h >= 1:
        bw = max(1, (w + 3) // 4)
        bh = max(1, (h + 3) // 4)
        size = bw * bh * fmt.block_size
        
        mipmaps.append(MipmapInfo(level, w, h, size, total))
        total += size
        
        if w <= 4 and h <= 4:
            break
        
        w = max(1, w // 2)
        h = max(1, h // 2)
        level += 1
    
    return mipmaps, total

def build_alpha_table(a0: int, a1: int) -> List[int]:
    """Build DXT5 alpha interpolation table"""
    if a0 > a1:
        return [a0, a1,
                (6*a0 + 1*a1) // 7, (5*a0 + 2*a1) // 7,
                (4*a0 + 3*a1) // 7, (3*a0 + 4*a1) // 7,
                (2*a0 + 5*a1) // 7, (1*a0 + 6*a1) // 7]
    else:
        return [a0, a1,
                (4*a0 + 1*a1) // 5, (3*a0 + 2*a1) // 5,
                (2*a0 + 3*a1) // 5, (1*a0 + 4*a1) // 5,
                0, 255]


# ══════════════════════════════════════════════════════════════════════════════
#                              DXT DECODER
# ══════════════════════════════════════════════════════════════════════════════

class DXTDecoder:
    """Decode DXT compressed textures"""
    
    @staticmethod
    def decode(data: bytes, width: int, height: int, fmt: DXTFormat) -> Image.Image:
        """Decode DXT data to PIL Image"""
        image = Image.new('RGBA', (width, height))
        pixels = image.load()
        
        blocks_w = max(1, (width + 3) // 4)
        blocks_h = max(1, (height + 3) // 4)
        block_size = fmt.block_size
        
        offset = 0
        for by in range(blocks_h):
            for bx in range(blocks_w):
                if offset + block_size > len(data):
                    break
                
                block = data[offset:offset + block_size]
                offset += block_size
                
                if fmt == DXTFormat.DXT5:
                    block_pixels = DXTDecoder._decode_dxt5_block(block)
                elif fmt == DXTFormat.DXT3:
                    block_pixels = DXTDecoder._decode_dxt3_block(block)
                else:
                    block_pixels = DXTDecoder._decode_dxt1_block(block)
                
                for i, pixel in enumerate(block_pixels):
                    px = bx * 4 + (i % 4)
                    py = by * 4 + (i // 4)
                    if px < width and py < height:
                        pixels[px, py] = pixel
        
        return image
    
    @staticmethod
    def _decode_dxt5_block(block: bytes) -> List[Tuple[int, int, int, int]]:
        """Decode single DXT5 block"""
        # Alpha
        a0, a1 = block[0], block[1]
        alpha_table = build_alpha_table(a0, a1)
        alpha_bits = sum(block[2+i] << (i*8) for i in range(6))
        
        # Colors
        c0 = struct.unpack('<H', block[8:10])[0]
        c1 = struct.unpack('<H', block[10:12])[0]
        color_bits = struct.unpack('<I', block[12:16])[0]
        
        rgb0, rgb1 = rgb565_to_rgb(c0), rgb565_to_rgb(c1)
        colors = [
            rgb0, rgb1,
            tuple((2*rgb0[i] + rgb1[i]) // 3 for i in range(3)),
            tuple((rgb0[i] + 2*rgb1[i]) // 3 for i in range(3))
        ]
        
        pixels = []
        for i in range(16):
            a_idx = (alpha_bits >> (i * 3)) & 0x7
            c_idx = (color_bits >> (i * 2)) & 0x3
            r, g, b = colors[c_idx]
            pixels.append((r, g, b, alpha_table[a_idx]))
        
        return pixels
    
    @staticmethod
    def _decode_dxt3_block(block: bytes) -> List[Tuple[int, int, int, int]]:
        """Decode single DXT3 block"""
        alpha_bits = struct.unpack('<Q', block[0:8])[0]
        
        c0 = struct.unpack('<H', block[8:10])[0]
        c1 = struct.unpack('<H', block[10:12])[0]
        color_bits = struct.unpack('<I', block[12:16])[0]
        
        rgb0, rgb1 = rgb565_to_rgb(c0), rgb565_to_rgb(c1)
        colors = [
            rgb0, rgb1,
            tuple((2*rgb0[i] + rgb1[i]) // 3 for i in range(3)),
            tuple((rgb0[i] + 2*rgb1[i]) // 3 for i in range(3))
        ]
        
        pixels = []
        for i in range(16):
            a = ((alpha_bits >> (i * 4)) & 0xF) * 17
            c_idx = (color_bits >> (i * 2)) & 0x3
            r, g, b = colors[c_idx]
            pixels.append((r, g, b, a))
        
        return pixels
    
    @staticmethod
    def _decode_dxt1_block(block: bytes) -> List[Tuple[int, int, int, int]]:
        """Decode single DXT1 block"""
        c0 = struct.unpack('<H', block[0:2])[0]
        c1 = struct.unpack('<H', block[2:4])[0]
        bits = struct.unpack('<I', block[4:8])[0]
        
        rgb0, rgb1 = rgb565_to_rgb(c0), rgb565_to_rgb(c1)
        
        if c0 > c1:
            colors = [
                rgb0 + (255,), rgb1 + (255,),
                tuple((2*rgb0[i] + rgb1[i]) // 3 for i in range(3)) + (255,),
                tuple((rgb0[i] + 2*rgb1[i]) // 3 for i in range(3)) + (255,)
            ]
        else:
            colors = [
                rgb0 + (255,), rgb1 + (255,),
                tuple((rgb0[i] + rgb1[i]) // 2 for i in range(3)) + (255,),
                (0, 0, 0, 0)
            ]
        
        return [colors[(bits >> (i * 2)) & 0x3] for i in range(16)]


# ══════════════════════════════════════════════════════════════════════════════
#                              DXT ENCODER
# ══════════════════════════════════════════════════════════════════════════════

class DXTEncoder:
    """High-quality DXT encoder"""
    
    def __init__(self, use_perceptual: bool = True):
        self.use_perceptual = use_perceptual
        # Perceptual weights (ITU-R BT.601)
        self.weights = (0.299, 0.587, 0.114) if use_perceptual else (1, 1, 1)
    
    def encode(self, image: Image.Image, fmt: DXTFormat) -> bytes:
        """Encode PIL Image to DXT format"""
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        width, height = image.size
        pixels = image.load()
        
        blocks_w = max(1, (width + 3) // 4)
        blocks_h = max(1, (height + 3) // 4)
        
        result = bytearray()
        
        for by in range(blocks_h):
            for bx in range(blocks_w):
                # Extract 4x4 block
                block_pixels = []
                for py in range(4):
                    for px in range(4):
                        x = min(bx * 4 + px, width - 1)
                        y = min(by * 4 + py, height - 1)
                        block_pixels.append(pixels[x, y])
                
                if fmt == DXTFormat.DXT5:
                    result.extend(self._encode_dxt5_block(block_pixels))
                elif fmt == DXTFormat.DXT3:
                    result.extend(self._encode_dxt3_block(block_pixels))
                else:
                    result.extend(self._encode_dxt1_block(block_pixels))
        
        return bytes(result)
    
    def _color_distance(self, c1: tuple, c2: tuple) -> float:
        """Weighted color distance"""
        return sum(self.weights[i] * (c1[i] - c2[i]) ** 2 for i in range(3))
    
    def _find_endpoints(self, colors: List[tuple]) -> Tuple[tuple, tuple]:
        """Find best color endpoints"""
        if not colors:
            return (0, 0, 0), (255, 255, 255)
        
        # Bounding box
        min_c = [min(c[i] for c in colors) for i in range(3)]
        max_c = [max(c[i] for c in colors) for i in range(3)]
        
        c0 = tuple(max_c)
        c1 = tuple(min_c)
        
        if c0 == c1:
            c1 = tuple(min(255, c + 1) for c in c0)
        
        return c0, c1
    
    def _encode_dxt5_block(self, pixels: List[tuple]) -> bytes:
        """Encode 16 pixels to DXT5"""
        block = bytearray(16)
        
        # === Alpha ===
        alphas = [p[3] for p in pixels]
        a0, a1 = max(alphas), min(alphas)
        if a0 == a1:
            a0 = min(255, a1 + 1)
        
        block[0], block[1] = a0, a1
        alpha_table = build_alpha_table(a0, a1)
        
        # Find best alpha indices
        alpha_bits = 0
        for i, a in enumerate(alphas):
            best_idx = min(range(8), key=lambda idx: abs(a - alpha_table[idx]))
            alpha_bits |= best_idx << (i * 3)
        
        for i in range(6):
            block[2 + i] = (alpha_bits >> (i * 8)) & 0xFF
        
        # === Colors ===
        colors = [(p[0], p[1], p[2]) for p in pixels]
        c0, c1 = self._find_endpoints(colors)
        
        c0_565 = rgb_to_rgb565(*c0)
        c1_565 = rgb_to_rgb565(*c1)
        
        if c0_565 < c1_565:
            c0_565, c1_565 = c1_565, c0_565
            c0, c1 = c1, c0
        
        block[8:10] = struct.pack('<H', c0_565)
        block[10:12] = struct.pack('<H', c1_565)
        
        # Color table
        color_table = [
            c0, c1,
            tuple((2*c0[i] + c1[i]) // 3 for i in range(3)),
            tuple((c0[i] + 2*c1[i]) // 3 for i in range(3))
        ]
        
        # Find best color indices
        color_bits = 0
        for i, color in enumerate(colors):
            best_idx = min(range(4), key=lambda idx: self._color_distance(color, color_table[idx]))
            color_bits |= best_idx << (i * 2)
        
        block[12:16] = struct.pack('<I', color_bits)
        
        return bytes(block)
    
    def _encode_dxt3_block(self, pixels: List[tuple]) -> bytes:
        """Encode 16 pixels to DXT3"""
        block = bytearray(16)
        
        # Explicit alpha (4-bit)
        alpha_bits = 0
        for i, p in enumerate(pixels):
            alpha_bits |= (p[3] // 17) << (i * 4)
        block[0:8] = struct.pack('<Q', alpha_bits)
        
        # Colors (same as DXT5)
        colors = [(p[0], p[1], p[2]) for p in pixels]
        c0, c1 = self._find_endpoints(colors)
        
        c0_565 = rgb_to_rgb565(*c0)
        c1_565 = rgb_to_rgb565(*c1)
        
        if c0_565 < c1_565:
            c0_565, c1_565 = c1_565, c0_565
            c0, c1 = c1, c0
        
        block[8:10] = struct.pack('<H', c0_565)
        block[10:12] = struct.pack('<H', c1_565)
        
        color_table = [
            c0, c1,
            tuple((2*c0[i] + c1[i]) // 3 for i in range(3)),
            tuple((c0[i] + 2*c1[i]) // 3 for i in range(3))
        ]
        
        color_bits = 0
        for i, color in enumerate(colors):
            best_idx = min(range(4), key=lambda idx: self._color_distance(color, color_table[idx]))
            color_bits |= best_idx << (i * 2)
        
        block[12:16] = struct.pack('<I', color_bits)
        
        return bytes(block)
    
    def _encode_dxt1_block(self, pixels: List[tuple]) -> bytes:
        """Encode 16 pixels to DXT1"""
        block = bytearray(8)
        
        colors = [(p[0], p[1], p[2]) for p in pixels]
        c0, c1 = self._find_endpoints(colors)
        
        c0_565 = rgb_to_rgb565(*c0)
        c1_565 = rgb_to_rgb565(*c1)
        
        if c0_565 < c1_565:
            c0_565, c1_565 = c1_565, c0_565
            c0, c1 = c1, c0
        elif c0_565 == c1_565:
            c0_565 = min(65535, c0_565 + 1)
        
        block[0:2] = struct.pack('<H', c0_565)
        block[2:4] = struct.pack('<H', c1_565)
        
        color_table = [
            c0, c1,
            tuple((2*c0[i] + c1[i]) // 3 for i in range(3)),
            tuple((c0[i] + 2*c1[i]) // 3 for i in range(3))
        ]
        
        color_bits = 0
        for i, color in enumerate(colors):
            best_idx = min(range(4), key=lambda idx: self._color_distance(color, color_table[idx]))
            color_bits |= best_idx << (i * 2)
        
        block[4:8] = struct.pack('<I', color_bits)
        
        return bytes(block)


# ══════════════════════════════════════════════════════════════════════════════
#                              KTEX CONVERTER (MAIN CLASS)
# ══════════════════════════════════════════════════════════════════════════════

class KTEXConverter:
    """
    Universal KTEX Converter
    
    Automatically detects and handles all KTEX variants:
    - Version 1: No mipmaps (18-byte header)
    - Version 5: Compact mipmaps (10-byte header)
    - Version 8: Full mipmaps (88-byte header)
    """
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.encoder = DXTEncoder()
    
    def log(self, msg: str):
        """Print message if verbose"""
        if self.verbose:
            print(f"  {msg}")
    
    # ──────────────────────────────────────────────────────────────────────────
    #                           HEADER PARSING
    # ──────────────────────────────────────────────────────────────────────────
    
    def _detect_structure(self, data: bytes) -> KTEXInfo:
        """Auto-detect KTEX structure and parse header"""
        if len(data) < 12 or data[0:4] != KTEX_MAGIC:
            raise ValueError("Invalid KTEX file")
        
        version = data[6]
        fmt = DXTFormat(data[7])
        width = struct.unpack('<H', data[8:10])[0]
        height = struct.unpack('<H', data[10:12])[0]
        
        # Calculate possible structures
        blocks_w = max(1, (width + 3) // 4)
        blocks_h = max(1, (height + 3) // 4)
        single_size = blocks_w * blocks_h * fmt.block_size
        
        mipmaps, mip_total = calculate_mipmap_chain(width, height, fmt)
        
        no_mip_header = len(data) - single_size
        mip_header = len(data) - mip_total
        
        # Detect based on header size validity
        if 12 <= no_mip_header <= 64:
            # No mipmaps
            return KTEXInfo(
                version=version,
                format=fmt,
                width=width,
                height=height,
                header_size=no_mip_header,
                has_mipmaps=False,
                mipmap_count=1,
                mipmaps=[MipmapInfo(0, width, height, single_size, 0)],
                raw_header=data[:no_mip_header]
            )
        elif 8 <= mip_header <= 256:
            # Has mipmaps
            return KTEXInfo(
                version=version,
                format=fmt,
                width=width,
                height=height,
                header_size=mip_header,
                has_mipmaps=True,
                mipmap_count=len(mipmaps),
                mipmaps=mipmaps,
                raw_header=data[:mip_header]
            )
        else:
            # Fallback: try version-based detection
            if version == 1:
                return KTEXInfo(
                    version=version,
                    format=fmt,
                    width=width,
                    height=height,
                    header_size=18,
                    has_mipmaps=False,
                    mipmap_count=1,
                    mipmaps=[MipmapInfo(0, width, height, single_size, 0)],
                    raw_header=data[:18]
                )
            elif version == 5:
                return KTEXInfo(
                    version=version,
                    format=fmt,
                    width=width,
                    height=height,
                    header_size=10,
                    has_mipmaps=True,
                    mipmap_count=len(mipmaps),
                    mipmaps=mipmaps,
                    raw_header=data[:10]
                )
            elif version == 8:
                return KTEXInfo(
                    version=version,
                    format=fmt,
                    width=width,
                    height=height,
                    header_size=88,
                    has_mipmaps=True,
                    mipmap_count=len(mipmaps),
                    mipmaps=mipmaps,
                    raw_header=data[:88]
                )
            else:
                raise ValueError(f"Unknown KTEX version: {version}")
    
    # ──────────────────────────────────────────────────────────────────────────
    #                           EXTRACTION (KTEX → PNG)
    # ──────────────────────────────────────────────────────────────────────────
    
    def extract(self, input_path: Path, output_path: Optional[Path] = None,
                extract_all_mipmaps: bool = False) -> ConversionResult:
        """Extract KTEX to PNG"""
        start = time.time()
        input_path = Path(input_path)
        
        try:
            # Read file
            with open(input_path, 'rb') as f:
                data = f.read()
            
            # Parse structure
            info = self._detect_structure(data)
            
            print(f"📄 {input_path.name}")
            print(f"   Dimensions: {info.width}x{info.height}")
            print(f"   Format: {info.format.name_str}")
            print(f"   Version: {info.version} ({'mipmaps' if info.has_mipmaps else 'no mipmaps'})")
            print(f"   Header: {info.header_size} bytes")
            
            # Set output path
            if output_path is None:
                output_path = input_path.with_suffix('.png')
            output_path = Path(output_path)
            
            # Decode main image
            mip0 = info.mipmaps[0]
            image_data = data[info.header_size:info.header_size + mip0.size]
            
            image = DXTDecoder.decode(image_data, mip0.width, mip0.height, info.format)
            
            # Save PNG
            image.save(output_path, 'PNG', optimize=True)
            print(f"   ✓ Saved: {output_path.name}")
            
            # Save metadata
            self._save_metadata(output_path, info)
            
            # Extract mipmaps if requested
            if extract_all_mipmaps and info.has_mipmaps:
                self._extract_mipmaps(data, info, input_path)
            
            return ConversionResult(
                success=True,
                input_path=input_path,
                output_path=output_path,
                duration=time.time() - start
            )
            
        except Exception as e:
            print(f"   ✗ Error: {e}")
            return ConversionResult(
                success=False,
                input_path=input_path,
                error=str(e),
                duration=time.time() - start
            )
    
    def _save_metadata(self, png_path: Path, info: KTEXInfo):
        """Save header and metadata for rebuilding"""
        # Raw header
        header_path = png_path.with_suffix('.ktex_header')
        with open(header_path, 'wb') as f:
            f.write(info.raw_header)
        
        # JSON metadata
        json_path = png_path.with_suffix('.ktex_meta.json')
        with open(json_path, 'w') as f:
            json.dump(info.to_dict(), f, indent=2)
        
        self.log(f"Metadata: {json_path.name}")
    
    def _extract_mipmaps(self, data: bytes, info: KTEXInfo, input_path: Path):
        """Extract all mipmap levels"""
        offset = info.header_size
        
        for mip in info.mipmaps:
            mip_data = data[offset:offset + mip.size]
            mip_image = DXTDecoder.decode(mip_data, mip.width, mip.height, info.format)
            
            mip_path = input_path.with_name(f"{input_path.stem}_mip{mip.level}.png")
            mip_image.save(mip_path, 'PNG')
            print(f"   Mip {mip.level}: {mip.width}x{mip.height}")
            
            offset += mip.size
    
    # ──────────────────────────────────────────────────────────────────────────
    #                           REBUILDING (PNG → KTEX)
    # ──────────────────────────────────────────────────────────────────────────
    
    def rebuild(self, input_path: Path, output_path: Optional[Path] = None,
                original_ktex: Optional[Path] = None,
                force_mipmaps: Optional[bool] = None) -> ConversionResult:
        """Rebuild PNG to KTEX"""
        start = time.time()
        input_path = Path(input_path)
        
        try:
            # Load image
            image = Image.open(input_path).convert('RGBA')
            width, height = image.size
            
            print(f"📄 {input_path.name}")
            print(f"   Dimensions: {width}x{height}")
            
            # Set output path
            if output_path is None:
                output_path = input_path.with_suffix('.tex')
            output_path = Path(output_path)
            
            # Load metadata
            header_data, meta = self._load_metadata(input_path, original_ktex)
            
            # Determine format and mipmaps
            fmt = DXTFormat(meta.get('format_id', 2))
            has_mipmaps = meta.get('has_mipmaps', True) if force_mipmaps is None else force_mipmaps
            version = meta.get('version', 8 if has_mipmaps else 1)
            
            print(f"   Format: {fmt.name_str}")
            print(f"   Mipmaps: {'Yes' if has_mipmaps else 'No'}")
            
            # Generate texture data
            if has_mipmaps:
                mipmaps, _ = calculate_mipmap_chain(width, height, fmt)
                texture_data = self._encode_with_mipmaps(image, mipmaps, fmt)
            else:
                texture_data = self.encoder.encode(image, fmt)
            
            # Build file
            if header_data and len(header_data) >= 12:
                # Update existing header
                header = bytearray(header_data)
                header[8:10] = struct.pack('<H', width)
                header[10:12] = struct.pack('<H', height)
                final_data = bytes(header) + texture_data
            else:
                # Create new header
                header = self._create_header(width, height, fmt, version, has_mipmaps)
                final_data = header + texture_data
            
            # Save
            with open(output_path, 'wb') as f:
                f.write(final_data)
            
            print(f"   ✓ Saved: {output_path.name} ({len(final_data):,} bytes)")
            
            return ConversionResult(
                success=True,
                input_path=input_path,
                output_path=output_path,
                duration=time.time() - start
            )
            
        except Exception as e:
            print(f"   ✗ Error: {e}")
            return ConversionResult(
                success=False,
                input_path=input_path,
                error=str(e),
                duration=time.time() - start
            )
    
    def _load_metadata(self, png_path: Path, original_ktex: Optional[Path]) -> Tuple[Optional[bytes], dict]:
        """Load header and metadata"""
        header_data = None
        meta = {}
        
        # Try saved header
        header_file = png_path.with_suffix('.ktex_header')
        if header_file.exists():
            with open(header_file, 'rb') as f:
                header_data = f.read()
            self.log(f"Using header: {header_file.name}")
        
        # Try JSON metadata
        json_file = png_path.with_suffix('.ktex_meta.json')
        if json_file.exists():
            with open(json_file, 'r') as f:
                meta = json.load(f)
            self.log(f"Using metadata: {json_file.name}")
        
        # Try original KTEX
        elif original_ktex:
            original_ktex = Path(original_ktex)
            with open(original_ktex, 'rb') as f:
                orig_data = f.read()
            
            info = self._detect_structure(orig_data)
            header_data = info.raw_header
            meta = info.to_dict()
            self.log(f"Using original: {original_ktex.name}")
        
        return header_data, meta
    
    def _encode_with_mipmaps(self, image: Image.Image, mipmaps: List[MipmapInfo], 
                             fmt: DXTFormat) -> bytes:
        """Encode image with all mipmap levels"""
        result = bytearray()
        
        for mip in mipmaps:
            if mip.level > 0:
                mip_image = image.resize((mip.width, mip.height), Image.Resampling.LANCZOS)
            else:
                mip_image = image
            
            mip_data = self.encoder.encode(mip_image, fmt)
            result.extend(mip_data)
            self.log(f"Mip {mip.level}: {mip.width}x{mip.height}")
        
        return bytes(result)
    
    def _create_header(self, width: int, height: int, fmt: DXTFormat, 
                       version: int, has_mipmaps: bool) -> bytes:
        """Create KTEX header"""
        if has_mipmaps and version == 8:
            # Full mipmap header (88 bytes)
            mipmaps, _ = calculate_mipmap_chain(width, height, fmt)
            header = bytearray(88)
            header[0:4] = KTEX_MAGIC
            header[6] = version
            header[7] = int(fmt)
            header[8:10] = struct.pack('<H', width)
            header[10:12] = struct.pack('<H', height)
            # Mipmap table would go here (simplified)
            return bytes(header)
        
        elif has_mipmaps and version == 5:
            # Compact mipmap header (10 bytes)
            header = bytearray(10)
            header[0:4] = KTEX_MAGIC
            header[6] = version
            header[7] = int(fmt)
            header[8:10] = struct.pack('<H', width)
            # Height encoded differently?
            return bytes(header)
        
        else:
            # No mipmap header (18 bytes)
            header = bytearray(18)
            header[0:4] = KTEX_MAGIC
            header[6] = 1
            header[7] = int(fmt)
            header[8:10] = struct.pack('<H', width)
            header[10:12] = struct.pack('<H', height)
            return bytes(header)
    
    # ──────────────────────────────────────────────────────────────────────────
    #                           BATCH PROCESSING
    # ──────────────────────────────────────────────────────────────────────────
    
    def batch_extract(self, files: List[Path], output_dir: Optional[Path] = None,
                      workers: int = 4) -> List[ConversionResult]:
        """Extract multiple files"""
        results = []
        
        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
        
        for f in files:
            f = Path(f)
            out = output_dir / f.with_suffix('.png').name if output_dir else None
            results.append(self.extract(f, out))
        
        return results
    
    def batch_rebuild(self, files: List[Path], output_dir: Optional[Path] = None,
                      workers: int = 4) -> List[ConversionResult]:
        """Rebuild multiple files"""
        results = []
        
        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
        
        for f in files:
            f = Path(f)
            out = output_dir / f.with_suffix('.tex').name if output_dir else None
            results.append(self.rebuild(f, out))
        
        return results
    
    # ──────────────────────────────────────────────────────────────────────────
    #                           FILE INFO
    # ──────────────────────────────────────────────────────────────────────────
    
    def info(self, input_path: Path) -> Optional[KTEXInfo]:
        """Get KTEX file information"""
        input_path = Path(input_path)
        
        try:
            with open(input_path, 'rb') as f:
                data = f.read()
            
            info = self._detect_structure(data)
            
            print(f"\n{'='*50}")
            print(f" {input_path.name}")
            print(f"{'='*50}")
            print(f" Size:       {len(data):,} bytes")
            print(f" Dimensions: {info.width} x {info.height}")
            print(f" Format:     {info.format.name_str}")
            print(f" Version:    {info.version}")
            print(f" Header:     {info.header_size} bytes")
            print(f" Mipmaps:    {info.mipmap_count} levels")
            
            if info.has_mipmaps:
                print(f"\n Mipmap chain:")
                for mip in info.mipmaps:
                    print(f"   Level {mip.level}: {mip.width:4d}x{mip.height:<4d} "
                          f"({mip.size:,} bytes)")
            
            return info
            
        except Exception as e:
            print(f" Error: {e}")
            return None


# ══════════════════════════════════════════════════════════════════════════════
#                              CLI INTERFACE
# ══════════════════════════════════════════════════════════════════════════════

def expand_wildcards(patterns: List[str]) -> List[Path]:
    """Expand wildcard patterns to file list"""
    import glob
    files = []
    for pattern in patterns:
        expanded = glob.glob(pattern)
        if expanded:
            files.extend(Path(p) for p in expanded)
        else:
            files.append(Path(pattern))
    return files

def main():
    parser = argparse.ArgumentParser(
        description='Shank 2 KTEX Universal Converter V4',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s extract texture.tex              Extract single file
  %(prog)s extract *.tex -o output/         Batch extract (use quotes on Windows)
  %(prog)s extract texture.tex --mipmaps    Extract all mipmap levels
  
  %(prog)s rebuild texture.png              Rebuild from PNG
  %(prog)s rebuild *.png -o textures/       Batch rebuild
  %(prog)s rebuild new.png --original old.tex   Use header from original
  %(prog)s rebuild texture.png --no-mipmaps Force no mipmaps
  
  %(prog)s info texture.tex                 Show file information
  %(prog)s info *.tex                       Show info for multiple files

Windows wildcard workaround:
  for %%f in (*.tex) do python %(prog)s extract "%%f" -o output/
        ''')
    
    parser.add_argument('command', choices=['extract', 'rebuild', 'info'],
                        help='Command to run')
    parser.add_argument('input', nargs='+', help='Input file(s)')
    parser.add_argument('-o', '--output', help='Output path or directory')
    parser.add_argument('--original', help='Original KTEX for header (rebuild only)')
    parser.add_argument('--mipmaps', action='store_true', 
                        help='Extract all mipmaps / Force mipmaps on rebuild')
    parser.add_argument('--no-mipmaps', action='store_true',
                        help='Force no mipmaps on rebuild')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--json', action='store_true', help='Output info as JSON')
    
    args = parser.parse_args()
    
    # Banner
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║            Shank 2 KTEX Universal Converter V4 - Final Edition               ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """)
    
    converter = KTEXConverter(verbose=args.verbose)
    
    # Expand input files
    input_files = expand_wildcards(args.input)
    
    if args.command == 'extract':
        if len(input_files) == 1 and args.output and not Path(args.output).suffix:
            # Single file to directory
            output_dir = Path(args.output)
            output_dir.mkdir(parents=True, exist_ok=True)
            out_path = output_dir / input_files[0].with_suffix('.png').name
            converter.extract(input_files[0], out_path, args.mipmaps)
        elif len(input_files) == 1:
            # Single file
            out_path = Path(args.output) if args.output else None
            converter.extract(input_files[0], out_path, args.mipmaps)
        else:
            # Batch
            output_dir = Path(args.output) if args.output else None
            results = converter.batch_extract(input_files, output_dir)
            
            success = sum(1 for r in results if r.success)
            print(f"\n✓ Completed: {success}/{len(results)} succeeded")
    
    elif args.command == 'rebuild':
        force_mipmaps = None
        if args.mipmaps:
            force_mipmaps = True
        elif args.no_mipmaps:
            force_mipmaps = False
        
        original = Path(args.original) if args.original else None
        
        if len(input_files) == 1:
            out_path = Path(args.output) if args.output else None
            converter.rebuild(input_files[0], out_path, original, force_mipmaps)
        else:
            output_dir = Path(args.output) if args.output else None
            results = converter.batch_rebuild(input_files, output_dir)
            
            success = sum(1 for r in results if r.success)
            print(f"\n✓ Completed: {success}/{len(results)} succeeded")
    
    elif args.command == 'info':
        all_info = []
        for f in input_files:
            info = converter.info(f)
            if info and args.json:
                all_info.append(info.to_dict())
        
        if args.json:
            print(json.dumps(all_info, indent=2))


if __name__ == '__main__':
    main()