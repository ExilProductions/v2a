use anyhow::{Context, Result};
use std::io::Write;
use std::process::{Command, Stdio};
use tempfile::NamedTempFile;

pub fn extract_audio(video_path: &str) -> Result<Vec<u8>> {
    let output = Command::new("ffmpeg")
        .args([
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "44100",
            "-ac", "2",
            "-f", "wav",
            "-",
        ])
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .context("Failed to start ffmpeg for audio extraction")?
        .wait_with_output()
        .context("Failed to read audio output")?;
    if !output.status.success() {
        anyhow::bail!("ffmpeg audio extraction failed");
    }
    Ok(output.stdout)
}

pub fn extract_audio_to_temp(video_path: &str) -> Result<(NamedTempFile, u64)> {
    let mut temp = NamedTempFile::new()?;
    let audio_data = extract_audio(video_path)?;
    temp.write_all(&audio_data)?;
    let size = audio_data.len() as u64;
    Ok((temp, size))
}