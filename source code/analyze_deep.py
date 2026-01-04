# analyze_deep.py - تحليل أعمق
import struct

def deep_analyze(filepath):
    with open(filepath, 'rb') as f:
        data = f.read()
    
    print(f"حجم الملف: {len(data):,} bytes")
    
    # الترويسة
    print("\n=== تحليل الترويسة ===")
    print(f"Magic: {data[0:4]}")
    print(f"Bytes 4-5: {data[4:6].hex()} (flags?)")
    print(f"Byte 6: {data[6]} (version?)")
    print(f"Byte 7: {data[7]} (format?)")
    
    # الأبعاد
    w = struct.unpack('<H', data[8:10])[0]
    h = struct.unpack('<H', data[10:12])[0]
    print(f"Width: {w}")
    print(f"Height: {h}")
    
    # البحث عن نهاية النمط المتكرر
    print("\n=== البحث عن نهاية الترويسة/Palette ===")
    
    # النمط المتكرر: 00 00 00 05 00 00 00 00 00 00 FF FF 00 00 00 00
    pattern = bytes([0x00, 0x00, 0x00, 0x05])
    
    last_pattern_pos = 0
    pos = 0
    count = 0
    while True:
        pos = data.find(pattern, pos)
        if pos == -1 or pos > 2000:
            break
        last_pattern_pos = pos
        count += 1
        pos += 1
    
    print(f"النمط المتكرر وُجد {count} مرات")
    print(f"آخر موقع للنمط: {last_pattern_pos}")
    
    # البحث عن بداية البيانات الحقيقية
    print("\n=== فحص مواقع محتملة لبداية البيانات ===")
    
    # حجم DXT5 المتوقع لـ 148x148
    blocks = ((w + 3) // 4) * ((h + 3) // 4)
    dxt5_size = blocks * 16
    dxt1_size = blocks * 8
    indexed_size = w * h  # 8-bit indexed
    
    print(f"حجم DXT5 المتوقع: {dxt5_size:,} bytes")
    print(f"حجم DXT1 المتوقع: {dxt1_size:,} bytes")
    print(f"حجم Indexed 8-bit: {indexed_size:,} bytes")
    
    # فحص المواقع المحتملة
    for offset in [16, 32, 64, 128, 256, 512, 1024, 1040, 2048]:
        remaining = len(data) - offset
        print(f"\nOffset {offset}: {remaining:,} bytes متبقية")
        
        if remaining == dxt5_size:
            print(f"  ✓ يطابق DXT5!")
        if remaining == dxt1_size:
            print(f"  ✓ يطابق DXT1!")
        if remaining == indexed_size:
            print(f"  ✓ يطابق Indexed 8-bit!")
        if remaining == indexed_size + 256*4:
            print(f"  ✓ يطابق Indexed + Palette (256 colors RGBA)!")
        if remaining == indexed_size + 256*3:
            print(f"  ✓ يطابق Indexed + Palette (256 colors RGB)!")
    
    # حساب عكسي
    print("\n=== حساب عكسي ===")
    remaining_from_16 = len(data) - 16
    
    if remaining_from_16 > indexed_size:
        palette_size = remaining_from_16 - indexed_size
        colors = palette_size // 4
        print(f"إذا كان Indexed من offset 16:")
        print(f"  حجم Palette: {palette_size} bytes = {colors} colors (RGBA)")
    
    # طباعة بيانات بعد الترويسة المحتملة
    print("\n=== بيانات عند مواقع مختلفة ===")
    for offset in [16, 256, 512, 1024]:
        if offset < len(data):
            sample = data[offset:offset+32]
            print(f"Offset {offset}: {sample.hex()}")

deep_analyze('skin_classicshank.tex')