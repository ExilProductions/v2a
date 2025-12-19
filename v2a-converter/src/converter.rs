use crate::audio;
use crate::block::BlockProcessor;
use crate::video::{VideoInfo, FrameExtractor};
use crate::{V2AHeader, V2AFrame};
use anyhow::{Context, Result};
use crossbeam_channel::bounded;
use indicatif::{ProgressBar, ProgressStyle};
use std::fs::File;
use std::io::{BufWriter, Write};
use std::sync::Arc;
use std::thread;

pub struct Converter {
    num_workers: usize,
}

impl Converter {
    pub fn new(num_workers: usize) -> Self {
        Self { num_workers }
    }

    pub fn convert(&self, input_path: &str, output_path: &str) -> Result<()> {
        let info = VideoInfo::from_path(input_path)
            .context("Failed to get video info")?;
        println!("Video: {}x{} @ {:.2} fps, {} frames", info.width, info.height, info.fps, info.frame_count);
        let progress = ProgressBar::new(info.frame_count as u64);
        progress.set_style(ProgressStyle::default_bar()
            .template("[{elapsed_precise}] {bar:40.cyan/blue} {pos:>7}/{len:7} {msg}")
            .unwrap());
        progress.set_message("Extracting audio...");
        let audio_data = audio::extract_audio(input_path)
            .context("Audio extraction failed")?;
        let audio_size = audio_data.len() as u64;
        progress.set_message("Audio extracted");
        let file = File::create(output_path)
            .context("Failed to create output file")?;
        let mut writer = BufWriter::new(file);

        let header = V2AHeader::new(
            info.frame_count,
            info.width,
            info.height,
            info.fps,
            audio_size,
        );
        header.write(&mut writer)
            .context("Failed to write header")?;

        writer.write_all(&audio_data)
            .context("Failed to write audio data")?;
        progress.set_message("Audio written");

        let (raw_tx, raw_rx) = bounded::<(usize, Vec<u8>)>(self.num_workers * 2);
        let (processed_tx, processed_rx) = bounded::<(usize, V2AFrame)>(self.num_workers * 2);

        let writer_thread = thread::spawn(move || -> Result<()> {
            let mut next_frame = 0;
            let mut buffer = std::collections::BTreeMap::new();
            while let Ok((idx, frame)) = processed_rx.recv() {
                buffer.insert(idx, frame);
                while let Some(frame) = buffer.remove(&next_frame) {
                    frame.write_compressed(&mut writer)
                        .context("Failed to write compressed frame")?;
                    next_frame += 1;
                }
            }
            for (idx, frame) in buffer.into_iter() {
                if idx != next_frame {
                    anyhow::bail!("Missing frame {}, got {}", next_frame, idx);
                }
                frame.write_compressed(&mut writer)?;
                next_frame += 1;
            }
            writer.flush()?;
            Ok(())
        });

        let block_processor = Arc::new(BlockProcessor::new());
        let width = info.width;
        let height = info.height;
        let worker_handles: Vec<_> = (0..self.num_workers)
            .map(|_| {
                let raw_rx = raw_rx.clone();
                let processed_tx = processed_tx.clone();
                let block_processor = block_processor.clone();
                let progress = progress.clone();
                thread::spawn(move || -> Result<()> {
                    while let Ok((idx, rgb_data)) = raw_rx.recv() {
                        let frame = block_processor.process_frame(
                            &rgb_data,
                            width,
                            height,
                        );
                        processed_tx.send((idx, frame))
                            .context("Failed to send processed frame")?;
                        progress.inc(1);
                    }
                    Ok(())
                })
            })
            .collect();

        let mut extractor = FrameExtractor::new(input_path, info.width, info.height)
            .context("Failed to start frame extractor")?;
        let frame_size = (info.width * info.height * 3) as usize;
        let mut frame_buffer = vec![0; frame_size];
        let mut frame_index = 0;
        while extractor.read_frame(&mut frame_buffer)
            .context("Failed to read frame")?
        {
            raw_tx.send((frame_index, frame_buffer.clone()))
                .context("Failed to send raw frame")?;
            frame_index += 1;
        }
        drop(raw_tx);

        for handle in worker_handles {
            handle.join().unwrap()?;
        }
        drop(processed_tx);

        writer_thread.join().unwrap()?;
        progress.finish_with_message("Conversion complete");
        Ok(())
    }
}