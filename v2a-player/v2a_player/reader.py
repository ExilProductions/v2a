import struct
import gzip
import io
import zlib
from dataclasses import dataclass
from typing import BinaryIO, Iterator, Tuple, Optional

MAGIC = b"V2A\0"
VERSION = 2

@dataclass
class V2AHeader:
    magic: bytes
    version: int
    frame_count: int
    original_width: int
    original_height: int
    fps: float
    audio_size: int
    padding: bytes
    
    @classmethod
    def read(cls, f: BinaryIO) -> "V2AHeader":
        magic = f.read(4)
        if magic != MAGIC:
            raise ValueError(f"Invalid magic: {magic!r}")
        version = struct.unpack("<H", f.read(2))[0]
        if version != VERSION:
            raise ValueError(f"Unsupported version: {version}")
        frame_count = struct.unpack("<I", f.read(4))[0]
        original_width = struct.unpack("<I", f.read(4))[0]
        original_height = struct.unpack("<I", f.read(4))[0]
        fps = struct.unpack("<f", f.read(4))[0]
        audio_size = struct.unpack("<Q", f.read(8))[0]
        padding = f.read(2)
        return cls(
            magic=magic,
            version=version,
            frame_count=frame_count,
            original_width=original_width,
            original_height=original_height,
            fps=fps,
            audio_size=audio_size,
            padding=padding,
        )
    
    def write(self, f: BinaryIO) -> None:
        f.write(self.magic)
        f.write(struct.pack("<H", self.version))
        f.write(struct.pack("<I", self.frame_count))
        f.write(struct.pack("<I", self.original_width))
        f.write(struct.pack("<I", self.original_height))
        f.write(struct.pack("<f", self.fps))
        f.write(struct.pack("<Q", self.audio_size))
        f.write(self.padding)

@dataclass
class V2AFrame:
    width: int
    height: int
    pixel_pairs: list  
    
    @classmethod
    def read_compressed(cls, f: BinaryIO) -> "V2AFrame":
        import zlib
        
        d = zlib.decompressobj(wbits=31)
        decompressed = bytearray()
        chunk_size = 4096
        
        while True:
            
            chunk = f.read(chunk_size)
            if not chunk:
                raise EOFError("End of file while reading gzip stream")
            
            try:
                
                decompressed.extend(d.decompress(chunk))
            except zlib.error as e:
                raise ValueError(f"zlib decompression error: {e}")
            
            if d.eof:
                
                unused_data = d.unused_data
                if unused_data:
                    
                    f.seek(-len(unused_data), 1)
                    
                if len(decompressed) < 4:
                    raise ValueError(f"Decompressed data too short: {len(decompressed)}")
                
                width = struct.unpack("<H", decompressed[0:2])[0]
                height = struct.unpack("<H", decompressed[2:4])[0]
                pixel_count = width * height
                expected_len = 4 + pixel_count * 2
                
                if len(decompressed) < expected_len:
                    raise ValueError(f"Decompressed data too short: expected {expected_len}, got {len(decompressed)}")
                
                
                data = bytes(decompressed[4:expected_len])
                pixel_pairs = [list(data[i:i+2]) for i in range(0, len(data), 2)]
                return cls(width, height, pixel_pairs)
            
            if len(decompressed) > 8192 * 1024:  
                raise ValueError(f"Decompressed data too large ({len(decompressed)} > 8MB), likely corrupted data")
    
    def write_compressed(self, f: BinaryIO) -> None:
        with gzip.GzipFile(fileobj=f, mode='wb') as gz:
            gz.write(struct.pack("<H", self.width))
            gz.write(struct.pack("<H", self.height))
            for pair in self.pixel_pairs:
                gz.write(bytes(pair))

class V2AReader:
    def __init__(self, path: str):
        self.path = path
        self.file = open(path, 'rb')
        self.header = V2AHeader.read(self.file)
        
        self.audio_data = self.file.read(self.header.audio_size)
        if len(self.audio_data) != self.header.audio_size:
            raise ValueError(f"Incomplete audio data: expected {self.header.audio_size}, got {len(self.audio_data)}")
        self.current_frame = 0
    
    def close(self):
        self.file.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()
    
    def read_frame(self) -> Optional[V2AFrame]:
        if self.current_frame >= self.header.frame_count:
            return None
        try:
            frame = V2AFrame.read_compressed(self.file)
            self.current_frame += 1
            return frame
        except EOFError:
            return None
    
    def frames(self) -> Iterator[V2AFrame]:
        while True:
            frame = self.read_frame()
            if frame is None:
                break
            yield frame
    
    def reset(self):
        self.file.seek(32 + self.header.audio_size)  
        self.current_frame = 0
    
    @property
    def frame_rate(self) -> float:
        return self.header.fps
    
    @property
    def original_dimensions(self) -> Tuple[int, int]:
        return (self.header.original_width, self.header.original_height)
    
    @property
    def frame_dimensions(self) -> Tuple[int, int]:
        pos = self.file.tell()
        self.file.seek(32 + self.header.audio_size)
        try:
            frame = V2AFrame.read_compressed(self.file)
            self.file.seek(pos)
            return (frame.width, frame.height)
        except Exception:
            self.file.seek(pos)
            raise
    
    @property
    def audio(self) -> bytes:
        return self.audio_data
