use byteorder::{LittleEndian, ReadBytesExt, WriteBytesExt};
use flate2::{read::GzDecoder, write::GzEncoder, Compression};
use std::io::{Read, Write};

pub mod audio;
pub mod block;
pub mod color;
pub mod converter;
pub mod video;

pub const MAGIC: &[u8; 4] = b"V2A\0";
pub const VERSION: u16 = 2;

#[derive(Debug, Clone, Copy)]
pub struct V2AHeader {
    pub magic: [u8; 4],
    pub version: u16,
    pub frame_count: u32,
    pub original_width: u32,
    pub original_height: u32,
    pub fps: f32,
    pub audio_size: u64,
    pub _padding: [u8; 2],
}

impl V2AHeader {
    pub fn new(
        frame_count: u32,
        original_width: u32,
        original_height: u32,
        fps: f32,
        audio_size: u64,
    ) -> Self {
        Self {
            magic: *MAGIC,
            version: VERSION,
            frame_count,
            original_width,
            original_height,
            fps,
            audio_size,
            _padding: [0; 2],
        }
    }

    pub fn write<W: Write>(&self, mut writer: W) -> std::io::Result<()> {
        writer.write_all(&self.magic)?;
        writer.write_u16::<LittleEndian>(self.version)?;
        writer.write_u32::<LittleEndian>(self.frame_count)?;
        writer.write_u32::<LittleEndian>(self.original_width)?;
        writer.write_u32::<LittleEndian>(self.original_height)?;
        writer.write_f32::<LittleEndian>(self.fps)?;
        writer.write_u64::<LittleEndian>(self.audio_size)?;
        writer.write_all(&self._padding)?;
        Ok(())
    }

    pub fn read<R: Read>(mut reader: R) -> std::io::Result<Self> {
        let mut magic = [0; 4];
        reader.read_exact(&mut magic)?;
        if &magic != MAGIC {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "Invalid magic",
            ));
        }
        let version = reader.read_u16::<LittleEndian>()?;
        if version != VERSION {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "Unsupported version",
            ));
        }
        let frame_count = reader.read_u32::<LittleEndian>()?;
        let original_width = reader.read_u32::<LittleEndian>()?;
        let original_height = reader.read_u32::<LittleEndian>()?;
        let fps = reader.read_f32::<LittleEndian>()?;
        let audio_size = reader.read_u64::<LittleEndian>()?;
        let mut padding = [0; 2];
        reader.read_exact(&mut padding)?;
        Ok(Self {
            magic,
            version,
            frame_count,
            original_width,
            original_height,
            fps,
            audio_size,
            _padding: padding,
        })
    }
}

#[derive(Debug, Clone)]
pub struct V2AFrame {
    pub width: u16,
    pub height: u16,
    pub pixel_pairs: Vec<[u8; 2]>,
}

impl V2AFrame {
    pub fn new(width: u16, height: u16) -> Self {
        Self {
            width,
            height,
            pixel_pairs: vec![[0, 0]; (width as usize) * (height as usize)],
        }
    }

    pub fn write_compressed<W: Write>(&self, writer: W) -> std::io::Result<()> {
        let mut encoder = GzEncoder::new(writer, Compression::best());
        encoder.write_u16::<LittleEndian>(self.width)?;
        encoder.write_u16::<LittleEndian>(self.height)?;
        for pair in &self.pixel_pairs {
            encoder.write_all(pair)?;
        }
        encoder.finish()?;
        Ok(())
    }

    pub fn read_compressed<R: Read>(reader: R) -> std::io::Result<Self> {
        let mut decoder = GzDecoder::new(reader);
        let width = decoder.read_u16::<LittleEndian>()?;
        let height = decoder.read_u16::<LittleEndian>()?;
        let pixel_count = (width as usize) * (height as usize);
        let mut pixel_pairs = Vec::with_capacity(pixel_count);
        for _ in 0..pixel_count {
            let mut pair = [0; 2];
            decoder.read_exact(&mut pair)?;
            pixel_pairs.push(pair);
        }
        Ok(Self {
            width,
            height,
            pixel_pairs,
        })
    }
}

pub use converter::Converter;
pub use block::BlockProcessor;
pub use color::Ansi256Palette;
pub use video::{VideoInfo, FrameExtractor};