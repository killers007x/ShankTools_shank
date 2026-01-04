# احفظ هذا كملف analyze_ktex.py وشغله
import struct

def analyze_file(filepath):
    with open(filepath, 'rb') as f:
        data = f.read()
    
    print(f"حجم الملف: {len(data):,} bytes")
    print(f"\n=== أول 128 بايت (Hex) ===")
    
    for i in range(0, min(128, len(data)), 16):
        hex_part = ' '.join(f'{b:02X}' for b in data[i:i+16])
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[i:i+16])
        print(f"{i:04X}: {hex_part:<48} | {ascii_part}")
    
    print(f"\n=== البحث عن توقيعات معروفة ===")
    
    signatures = {
        b'KTEX': 'KTEX Texture',
        b'DDS ': 'DDS Texture',
        b'\x89PNG': 'PNG Image',
        b'RIFF': 'RIFF/WAV',
        b'FSB4': 'FMOD Sound Bank 4',
        b'FSB5': 'FMOD Sound Bank 5',
        b'\x1bLua': 'Compiled Lua',
    }
    
    for sig, name in signatures.items():
        pos = data.find(sig)
        if pos != -1:
            print(f"  {name}: وُجد في الموقع {pos} (0x{pos:X})")
    
    print(f"\n=== قراءة كـ أرقام (Little Endian) ===")
    for i in range(0, min(64, len(data)), 4):
        val = struct.unpack('<I', data[i:i+4])[0]
        print(f"  Offset {i:2}: {val:>12} (0x{val:08X})")

# شغل التحليل
analyze_file('skin_classicshank.tex')