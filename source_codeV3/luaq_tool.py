import struct
import sys
import os


class LuaParser:
    """Custom Lua table parser"""
    
    def __init__(self, code):
        self.code = code
        self.pos = 0
        self.length = len(code)
    
    def skip_whitespace(self):
        while self.pos < self.length:
            if self.code[self.pos] in ' \t\n\r':
                self.pos += 1
            elif self.code[self.pos:self.pos+2] == '--':
                while self.pos < self.length and self.code[self.pos] != '\n':
                    self.pos += 1
            else:
                break
    
    def peek(self):
        self.skip_whitespace()
        if self.pos < self.length:
            return self.code[self.pos]
        return None
    
    def consume(self, expected=None):
        self.skip_whitespace()
        if expected:
            if self.code[self.pos:self.pos+len(expected)] == expected:
                self.pos += len(expected)
                return expected
            raise ValueError(f"Expected '{expected}' at position {self.pos}")
        char = self.code[self.pos]
        self.pos += 1
        return char
    
    def parse_string(self):
        self.skip_whitespace()
        quote = self.code[self.pos]
        if quote not in '"\'':
            raise ValueError(f"Expected string at position {self.pos}")
        
        self.pos += 1
        result = []
        
        while self.pos < self.length:
            char = self.code[self.pos]
            
            if char == quote:
                self.pos += 1
                return ''.join(result)
            elif char == '\\':
                self.pos += 1
                if self.pos < self.length:
                    next_char = self.code[self.pos]
                    escape_map = {'n': '\n', 't': '\t', 'r': '\r', '\\': '\\', '"': '"', "'": "'"}
                    result.append(escape_map.get(next_char, next_char))
                    self.pos += 1
            else:
                result.append(char)
                self.pos += 1
        
        raise ValueError("Unterminated string")
    
    def parse_number(self):
        self.skip_whitespace()
        start = self.pos
        
        if self.pos < self.length and self.code[self.pos] == '-':
            self.pos += 1
        
        while self.pos < self.length and (self.code[self.pos].isdigit() or self.code[self.pos] == '.'):
            self.pos += 1
        
        if self.pos < self.length and self.code[self.pos] in 'eE':
            self.pos += 1
            if self.pos < self.length and self.code[self.pos] in '+-':
                self.pos += 1
            while self.pos < self.length and self.code[self.pos].isdigit():
                self.pos += 1
        
        num_str = self.code[start:self.pos]
        
        if '.' in num_str or 'e' in num_str.lower():
            return float(num_str)
        return int(num_str)
    
    def parse_identifier(self):
        self.skip_whitespace()
        start = self.pos
        
        while self.pos < self.length:
            char = self.code[self.pos]
            if char.isalnum() or char == '_':
                self.pos += 1
            else:
                break
        
        return self.code[start:self.pos]
    
    def parse_value(self):
        self.skip_whitespace()
        
        if self.pos >= self.length:
            return None
        
        char = self.peek()
        
        if char in '"\'':
            return self.parse_string()
        
        if char == '{':
            return self.parse_table()
        
        if char == '-' or char.isdigit():
            if char == '-':
                if self.pos + 1 < self.length and self.code[self.pos + 1].isdigit():
                    return self.parse_number()
            else:
                return self.parse_number()
        
        if char.isalpha() or char == '_':
            ident = self.parse_identifier()
            if ident == 'true':
                return True
            elif ident == 'false':
                return False
            elif ident == 'nil':
                return None
            return ident
        
        raise ValueError(f"Unexpected character '{char}' at position {self.pos}")
    
    def parse_table(self):
        self.consume('{')
        result = {}
        array_index = 1
        
        while True:
            self.skip_whitespace()
            
            if self.peek() == '}':
                self.consume('}')
                break
            
            if self.peek() == '[':
                self.consume('[')
                key = self.parse_value()
                self.consume(']')
                self.skip_whitespace()
                self.consume('=')
                value = self.parse_value()
                result[key] = value
            else:
                saved_pos = self.pos
                
                if self.peek() and (self.peek().isalpha() or self.peek() == '_'):
                    ident = self.parse_identifier()
                    self.skip_whitespace()
                    
                    if self.peek() == '=':
                        self.consume('=')
                        value = self.parse_value()
                        result[ident] = value
                    else:
                        self.pos = saved_pos
                        value = self.parse_value()
                        result[array_index] = value
                        array_index += 1
                else:
                    value = self.parse_value()
                    result[array_index] = value
                    array_index += 1
            
            self.skip_whitespace()
            if self.peek() == ',':
                self.consume(',')
        
        if result and all(isinstance(k, int) for k in result.keys()):
            max_idx = max(result.keys())
            if set(result.keys()) == set(range(1, max_idx + 1)):
                return [result[i] for i in range(1, max_idx + 1)]
        
        return result
    
    def parse_assignment(self):
        self.skip_whitespace()
        name = self.parse_identifier()
        self.skip_whitespace()
        self.consume('=')
        value = self.parse_value()
        return name, value


def parse_lua_file(filepath):
    """Read and parse Lua file"""
    with open(filepath, 'r', encoding='utf-8') as f:
        code = f.read()
    
    lines = []
    for line in code.split('\n'):
        stripped = line.strip()
        if stripped.startswith('--'):
            continue
        lines.append(line)
    
    clean_code = '\n'.join(lines).strip()
    
    parser = LuaParser(clean_code)
    return parser.parse_assignment()


class LuaCompiler:
    """Compile Lua table to Bytecode 5.1"""
    
    OP_LOADK = 1
    OP_LOADBOOL = 2
    OP_LOADNIL = 3
    OP_SETGLOBAL = 7
    OP_SETTABLE = 9
    OP_NEWTABLE = 10
    OP_SETLIST = 34
    OP_RETURN = 30
    
    def __init__(self):
        self.output = bytearray()
        self.constants = []
        self.const_map = {}
        self.instructions = []
        self.max_stack = 2
    
    def write_byte(self, b):
        self.output.append(b & 0xFF)
    
    def write_int(self, val):
        self.output.extend(struct.pack('<i', val))
    
    def write_size_t(self, val):
        self.output.extend(struct.pack('<I', val))
    
    def write_number(self, val):
        self.output.extend(struct.pack('<d', float(val)))
    
    def write_string(self, s):
        if s is None:
            self.write_size_t(0)
        else:
            encoded = s.encode('latin-1', errors='replace') + b'\x00'
            self.write_size_t(len(encoded))
            self.output.extend(encoded)
    
    def write_instruction(self, opcode, a=0, b=0, c=0, bx=None):
        if bx is not None:
            inst = (opcode & 0x3F) | ((a & 0xFF) << 6) | ((bx & 0x3FFFF) << 14)
        else:
            inst = (opcode & 0x3F) | ((a & 0xFF) << 6) | ((c & 0x1FF) << 14) | ((b & 0x1FF) << 23)
        self.output.extend(struct.pack('<I', inst))
    
    def write_header(self):
        self.output.extend(b'\x1bLua')
        self.write_byte(0x51)
        self.write_byte(0x00)
        self.write_byte(0x01)
        self.write_byte(0x04)
        self.write_byte(0x04)
        self.write_byte(0x04)
        self.write_byte(0x08)
        self.write_byte(0x00)
    
    def add_constant(self, val):
        if isinstance(val, int) and not isinstance(val, bool):
            val = float(val)
        
        key = (type(val).__name__, str(val))
        if key in self.const_map:
            return self.const_map[key]
        
        idx = len(self.constants)
        self.constants.append(val)
        self.const_map[key] = idx
        return idx
    
    def rk(self, idx):
        return idx + 256 if idx < 256 else idx
    
    def emit(self, opcode, a=0, b=0, c=0, bx=None):
        self.instructions.append((opcode, a, b, c, bx))
        if a + 1 > self.max_stack:
            self.max_stack = a + 1
    
    def compile_value(self, val, reg):
        if val is None:
            self.emit(self.OP_LOADNIL, reg, reg)
        elif isinstance(val, bool):
            self.emit(self.OP_LOADBOOL, reg, 1 if val else 0, 0)
        elif isinstance(val, (int, float)):
            idx = self.add_constant(val)
            self.emit(self.OP_LOADK, reg, bx=idx)
        elif isinstance(val, str):
            idx = self.add_constant(val)
            self.emit(self.OP_LOADK, reg, bx=idx)
        elif isinstance(val, list):
            self.compile_list(val, reg)
        elif isinstance(val, dict):
            self.compile_dict(val, reg)
        
        return reg
    
    def compile_list(self, lst, reg):
        self.emit(self.OP_NEWTABLE, reg, len(lst), 0)
        
        if not lst:
            return reg
        
        for i, item in enumerate(lst):
            item_reg = reg + 1 + i
            self.compile_value(item, item_reg)
            if item_reg + 1 > self.max_stack:
                self.max_stack = item_reg + 2
        
        self.emit(self.OP_SETLIST, reg, len(lst), 1)
        return reg
    
    def compile_dict(self, dct, reg):
        hash_size = len(dct)
        hash_log = 0
        while (1 << hash_log) < hash_size:
            hash_log += 1
        
        self.emit(self.OP_NEWTABLE, reg, 0, hash_log)
        
        for key, val in dct.items():
            key_idx = self.rk(self.add_constant(key))
            
            if isinstance(val, (list, dict)):
                val_reg = reg + 1
                self.compile_value(val, val_reg)
                if val_reg + 1 > self.max_stack:
                    self.max_stack = val_reg + 2
                self.emit(self.OP_SETTABLE, reg, key_idx, val_reg)
            elif val is None:
                val_reg = reg + 1
                self.emit(self.OP_LOADNIL, val_reg, val_reg)
                self.emit(self.OP_SETTABLE, reg, key_idx, val_reg)
            elif isinstance(val, bool):
                val_idx = self.rk(self.add_constant(val))
                self.emit(self.OP_SETTABLE, reg, key_idx, val_idx)
            else:
                val_idx = self.rk(self.add_constant(val))
                self.emit(self.OP_SETTABLE, reg, key_idx, val_idx)
        
        return reg
    
    def compile_table(self, global_name, table):
        self.compile_value(table, 0)
        name_idx = self.add_constant(global_name)
        self.emit(self.OP_SETGLOBAL, 0, bx=name_idx)
        self.emit(self.OP_RETURN, 0, 1)
    
    def build_bytecode(self):
        self.output = bytearray()
        self.write_header()
        
        self.write_string(None)
        self.write_int(0)
        self.write_int(0)
        self.write_byte(0)
        self.write_byte(0)
        self.write_byte(2)
        self.write_byte(self.max_stack + 10)
        
        self.write_int(len(self.instructions))
        for opcode, a, b, c, bx in self.instructions:
            self.write_instruction(opcode, a, b, c, bx=bx)
        
        self.write_int(len(self.constants))
        for const in self.constants:
            if const is None:
                self.write_byte(0)
            elif isinstance(const, bool):
                self.write_byte(1)
                self.write_byte(1 if const else 0)
            elif isinstance(const, float):
                self.write_byte(3)
                self.write_number(const)
            elif isinstance(const, str):
                self.write_byte(4)
                self.write_string(const)
        
        self.write_int(0)
        self.write_int(0)
        self.write_int(0)
        self.write_int(0)
        
        return bytes(self.output)


class LuaDecompiler:
    """Decompile Lua 5.1 Bytecode"""
    
    def __init__(self, data):
        self.data = data
        self.pos = 0
    
    def read_byte(self):
        b = self.data[self.pos]
        self.pos += 1
        return b
    
    def read_int(self):
        val = struct.unpack('<i', self.data[self.pos:self.pos+4])[0]
        self.pos += 4
        return val
    
    def read_size_t(self):
        val = struct.unpack('<I', self.data[self.pos:self.pos+4])[0]
        self.pos += 4
        return val
    
    def read_number(self):
        val = struct.unpack('<d', self.data[self.pos:self.pos+8])[0]
        self.pos += 8
        return val
    
    def read_string(self):
        size = self.read_size_t()
        if size == 0:
            return None
        s = self.data[self.pos:self.pos+size-1].decode('latin-1', errors='replace')
        self.pos += size
        return s
    
    def parse_header(self):
        self.pos = 12
    
    def parse_function(self):
        self.read_string()
        self.read_int()
        self.read_int()
        self.read_byte()
        self.read_byte()
        self.read_byte()
        self.read_byte()
        
        num_inst = self.read_int()
        instructions = []
        for _ in range(num_inst):
            instructions.append(struct.unpack('<I', self.data[self.pos:self.pos+4])[0])
            self.pos += 4
        
        num_const = self.read_int()
        constants = []
        for _ in range(num_const):
            t = self.read_byte()
            if t == 0:
                constants.append(None)
            elif t == 1:
                constants.append(self.read_byte() != 0)
            elif t == 3:
                constants.append(self.read_number())
            elif t == 4:
                constants.append(self.read_string())
        
        num_proto = self.read_int()
        for _ in range(num_proto):
            self.parse_function()
        
        num_lines = self.read_int()
        self.pos += num_lines * 4
        
        num_locals = self.read_int()
        for _ in range(num_locals):
            self.read_string()
            self.read_int()
            self.read_int()
        
        num_upval = self.read_int()
        for _ in range(num_upval):
            self.read_string()
        
        return instructions, constants
    
    def format_value(self, val, indent=0):
        prefix = "    " * indent
        
        if val is None:
            return "nil"
        elif isinstance(val, bool):
            return "true" if val else "false"
        elif isinstance(val, float):
            if val == int(val):
                return str(int(val))
            return str(val)
        elif isinstance(val, str):
            escaped = val.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            return f'"{escaped}"'
        elif isinstance(val, dict):
            if not val:
                return "{}"
            lines = ["{"]
            for k, v in val.items():
                fv = self.format_value(v, indent + 1)
                if isinstance(k, str) and k.isidentifier() and not k[0].isdigit():
                    lines.append(f"{prefix}    {k} = {fv},")
                else:
                    lines.append(f"{prefix}    [{self.format_value(k)}] = {fv},")
            lines.append(f"{prefix}}}")
            return "\n".join(lines)
        elif isinstance(val, list):
            if not val:
                return "{}"
            if all(isinstance(x, (int, float, str, bool, type(None))) for x in val):
                return "{ " + ", ".join(self.format_value(x) for x in val) + " }"
            lines = ["{"]
            for item in val:
                lines.append(f"{prefix}    {self.format_value(item, indent + 1)},")
            lines.append(f"{prefix}}}")
            return "\n".join(lines)
        return str(val)
    
    def reconstruct_table(self, instructions, constants):
        registers = {}
        global_name = None
        
        def get_const(idx):
            idx = idx - 256 if idx >= 256 else idx
            return constants[idx] if 0 <= idx < len(constants) else None
        
        for inst in instructions:
            opcode = inst & 0x3F
            a = (inst >> 6) & 0xFF
            b = (inst >> 23) & 0x1FF
            c = (inst >> 14) & 0x1FF
            bx = (inst >> 14) & 0x3FFFF
            
            if opcode == 10:
                registers[a] = {}
            elif opcode == 9:
                if a in registers and isinstance(registers[a], dict):
                    key = get_const(b) if b >= 256 else registers.get(b)
                    val = get_const(c) if c >= 256 else registers.get(c)
                    if key is not None:
                        registers[a][key] = val
            elif opcode == 1:
                registers[a] = get_const(bx)
            elif opcode == 34:
                if a in registers:
                    items = [registers.get(a + i + 1) for i in range(b)]
                    registers[a] = [x for x in items if x is not None] or registers[a]
            elif opcode == 7:
                global_name = get_const(bx)
        
        return global_name, registers.get(0, {})
    
    def decompile(self):
        self.parse_header()
        instructions, constants = self.parse_function()
        global_name, table = self.reconstruct_table(instructions, constants)
        
        if global_name:
            return f"{global_name} = {self.format_value(table)}\n"
        return f"return {self.format_value(table)}\n"


def compile_lua_file(input_path, output_path=None):
    """Compile Lua file to bytecode"""
    print(f"Compiling: {input_path}")
    
    global_name, table = parse_lua_file(input_path)
    
    print(f"  Global name: {global_name}")
    print(f"  Table type: {type(table).__name__}")
    
    compiler = LuaCompiler()
    compiler.compile_table(global_name, table)
    bytecode = compiler.build_bytecode()
    
    if output_path is None:
        output_path = input_path.rsplit('.', 1)[0] + '_compiled.lua'
    
    with open(output_path, 'wb') as f:
        f.write(bytecode)
    
    print(f"Done!")
    print(f"  Output: {output_path}")
    print(f"  Size: {len(bytecode)} bytes")
    print(f"  Constants: {len(compiler.constants)}")
    print(f"  Instructions: {len(compiler.instructions)}")
    
    return True


def decompile_file(input_path, output_path=None):
    """Decompile bytecode to Lua"""
    with open(input_path, 'rb') as f:
        data = f.read()
    
    if data[:4] != b'\x1bLua':
        print(f"Error: Not a Lua bytecode file")
        return False
    
    decompiler = LuaDecompiler(data)
    lua_code = decompiler.decompile()
    
    if output_path is None:
        output_path = input_path.rsplit('.', 1)[0] + '_decompiled.lua'
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("-- Decompiled from Shank 2 Lua bytecode\n")
        f.write(f"-- Original file: {os.path.basename(input_path)}\n\n")
        f.write(lua_code)
    
    print(f"Decompiled: {input_path}")
    print(f"  Output: {output_path}")
    return True


def batch_decompile(folder_path, output_folder=None):
    """Decompile all bytecode files in folder"""
    if output_folder is None:
        output_folder = os.path.join(folder_path, "decompiled")
    
    os.makedirs(output_folder, exist_ok=True)
    
    success = 0
    failed = 0
    skipped = 0
    
    files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
    
    print(f"Scanning {len(files)} files...")
    print("=" * 50)
    
    for filename in files:
        filepath = os.path.join(folder_path, filename)
        
        try:
            with open(filepath, 'rb') as f:
                header = f.read(4)
            
            if header == b'\x1bLua':
                out_name = os.path.splitext(filename)[0] + '_decompiled.lua'
                out_path = os.path.join(output_folder, out_name)
                
                with open(filepath, 'rb') as f:
                    data = f.read()
                
                decompiler = LuaDecompiler(data)
                lua_code = decompiler.decompile()
                
                with open(out_path, 'w', encoding='utf-8') as f:
                    f.write(f"-- Decompiled from: {filename}\n\n")
                    f.write(lua_code)
                
                print(f"[OK] {filename}")
                success += 1
            else:
                skipped += 1
        
        except Exception as e:
            print(f"[FAIL] {filename}: {e}")
            failed += 1
    
    print("=" * 50)
    print(f"Done! Success: {success}, Failed: {failed}, Skipped: {skipped}")
    print(f"Output: {output_folder}")


def batch_compile(folder_path, output_folder=None):
    """Compile all Lua files in folder"""
    if output_folder is None:
        output_folder = os.path.join(folder_path, "compiled")
    
    os.makedirs(output_folder, exist_ok=True)
    
    success = 0
    failed = 0
    
    files = [f for f in os.listdir(folder_path) if f.endswith('.lua')]
    
    print(f"Compiling {len(files)} files...")
    print("=" * 50)
    
    for filename in files:
        filepath = os.path.join(folder_path, filename)
        
        try:
            with open(filepath, 'rb') as f:
                header = f.read(4)
            
            if header == b'\x1bLua':
                continue
            
            global_name, table = parse_lua_file(filepath)
            
            compiler = LuaCompiler()
            compiler.compile_table(global_name, table)
            bytecode = compiler.build_bytecode()
            
            out_name = filename.replace('_decompiled', '')
            out_path = os.path.join(output_folder, out_name)
            
            with open(out_path, 'wb') as f:
                f.write(bytecode)
            
            print(f"[OK] {filename} -> {out_name}")
            success += 1
        
        except Exception as e:
            print(f"[FAIL] {filename}: {e}")
            failed += 1
    
    print("=" * 50)
    print(f"Done! Success: {success}, Failed: {failed}")
    print(f"Output: {output_folder}")


def main():
    if len(sys.argv) < 2:
        print("=" * 50)
        print("  Shank 2 Lua Tool - Decompile & Compile")
        print("=" * 50)
        print("\nSingle file:")
        print("  python luaq_tool.py -d <file>           Decompile")
        print("  python luaq_tool.py -c <file>           Compile")
        print("  python luaq_tool.py -d <file> -o <out>  Custom output")
        print("  python luaq_tool.py -c <file> -o <out>  Custom output")
        print("\nBatch processing:")
        print("  python luaq_tool.py -db <folder>        Decompile all")
        print("  python luaq_tool.py -cb <folder>        Compile all")
        print("\nExamples:")
        print("  python luaq_tool.py -d boss_magnus.lua")
        print("  python luaq_tool.py -db C:\\game\\lua")
        print("  python luaq_tool.py -cb C:\\game\\lua\\decompiled")
        return
    
    mode = sys.argv[1]
    # the modes that you should type it in CMD
    if mode == '-d': # single file
        if len(sys.argv) >= 5 and sys.argv[3] == '-o': # -o give your file name before decode
            decompile_file(sys.argv[2], sys.argv[4])
        elif len(sys.argv) >= 3:
            decompile_file(sys.argv[2])
    
    elif mode == '-c': # for rebuild
        if len(sys.argv) >= 5 and sys.argv[3] == '-o': # -o give your file name before decode
            compile_lua_file(sys.argv[2], sys.argv[4])
        elif len(sys.argv) >= 3:
            compile_lua_file(sys.argv[2])
    
    elif mode == '-db': # decode all
        if len(sys.argv) >= 3:
            batch_decompile(sys.argv[2])
    
    elif mode == '-cb': # rebuild all
        if len(sys.argv) >= 3:
            batch_compile(sys.argv[2])
    
    else:
        print(f"Unknown mode: {mode}") # if you didn't type -d or -c or -db or -cd


if __name__ == "__main__":
    main()