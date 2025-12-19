use anyhow::{Context, Result};
use serde::Deserialize;
use std::process::{Command, Stdio};
use std::io::Read;

#[derive(Debug, Clone)]
pub struct VideoInfo {
    pub width: u32,
    pub height: u32,
    pub frame_count: u32,
    pub fps: f32,
    pub duration: f32,
}

fn parse_fraction(fraction: &str) -> Option<(u32, u32)> {
    let parts: Vec<&str> = fraction.split('/').collect();
    if parts.len() == 2 {
        let num = parts[0].parse().ok()?;
        let den = parts[1].parse().ok()?;
        Some((num, den))
    } else {
        None
    }
}

impl VideoInfo {
    pub fn from_path(path: &str) -> Result<Self> {
        let output = Command::new("ffprobe")
            .args([
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                path,
            ])
            .output()
            .context("Failed to execute ffprobe")?;
        if !output.status.success() {
            anyhow::bail!("ffprobe failed: {}", String::from_utf8_lossy(&output.stderr));
        }
        let probe: FfprobeOutput = serde_json::from_slice(&output.stdout)
            .context("Failed to parse ffprobe JSON")?;

        let video_stream = probe
            .streams
            .into_iter()
            .find(|s| s.codec_type == "video")
            .context("No video stream found")?;

        let width = video_stream.width.unwrap_or(0);
        let height = video_stream.height.unwrap_or(0);
        let nb_frames = video_stream.nb_frames.and_then(|s| s.parse().ok());
        let avg_frame_rate = video_stream.avg_frame_rate.as_deref()
            .and_then(parse_fraction)
            .unwrap_or((0, 1));
        let fps = if avg_frame_rate.1 == 0 { 0.0 } else { avg_frame_rate.0 as f32 / avg_frame_rate.1 as f32 };
        let duration = video_stream.duration
            .as_deref()
            .and_then(|s| s.parse().ok())
            .or_else(|| probe.format.duration.as_deref().and_then(|s| s.parse().ok()))
            .unwrap_or(0.0);
        let frame_count = nb_frames.unwrap_or_else(|| {
            (duration * fps).round() as u32
        });

        Ok(Self {
            width,
            height,
            frame_count,
            fps,
            duration,
        })
    }
}

#[derive(Debug, Deserialize)]
struct FfprobeOutput {
    streams: Vec<Stream>,
    format: Format,
}

#[derive(Debug, Deserialize)]
struct Stream {
    codec_type: String,
    width: Option<u32>,
    height: Option<u32>,
    #[serde(rename = "nb_frames")]
    nb_frames: Option<String>,
    #[serde(rename = "avg_frame_rate")]
    avg_frame_rate: Option<String>,
    duration: Option<String>,
}

#[derive(Debug, Deserialize)]
struct Format {
    duration: Option<String>,
}

pub struct FrameExtractor {
    width: u32,
    height: u32,
    child: std::process::Child,
    stdout: std::process::ChildStdout,
    frame_size: usize,
}

impl FrameExtractor {
    pub fn new(path: &str, width: u32, height: u32) -> Result<Self> {
        let mut child = Command::new("ffmpeg")
            .args([
                "-i", path,
                "-vf", "format=rgb24",
                "-f", "rawvideo",
                "-pix_fmt", "rgb24",
                "-",
            ])
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .context("Failed to start ffmpeg")?;

        let stdout = child.stdout.take().context("Failed to capture stdout")?;
        let frame_size = (width * height * 3) as usize;

        Ok(Self {
            width,
            height,
            child,
            stdout,
            frame_size,
        })
    }

    pub fn read_frame(&mut self, buffer: &mut [u8]) -> Result<bool> {
        buffer.iter_mut().for_each(|b| *b = 0);
        let mut read = 0;
        while read < self.frame_size {
            match self.stdout.read(&mut buffer[read..]) {
                Ok(0) => return Ok(false),
                Ok(n) => read += n,
                Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
                Err(e) => return Err(e.into()),
            }
        }
        Ok(true)
    }

    pub fn width(&self) -> u32 { self.width }
    pub fn height(&self) -> u32 { self.height }
}

impl Drop for FrameExtractor {
    fn drop(&mut self) {
        let _ = self.child.kill();
    }
}