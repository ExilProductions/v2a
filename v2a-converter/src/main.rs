use clap::{Parser, Subcommand};
use v2a_converter::{Converter, V2AHeader};
use std::fs::File;
use std::io::BufReader;

#[derive(Parser)]
#[command(name = "v2a-converter")]
#[command(about = "Convert video to V2A format", long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    Convert {
        input: String,
        output: String,
        #[arg(short, long, default_value_t = num_cpus::get())]
        workers: usize,
        #[arg(long)]
        fps: Option<f32>,
    },
    Info {
        file: String,
    },
}

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Commands::Convert { input, output, workers, fps } => {
            let converter = Converter::new(workers);
            converter.convert(&input, &output)?;
            println!("Successfully converted {} to {}", input, output);
        }
        Commands::Info { file } => {
            let f = File::open(&file)?;
            let mut reader = BufReader::new(f);
            let header = V2AHeader::read(&mut reader)?;
            println!("V2A File: {}", file);
            println!("  Magic: {}", String::from_utf8_lossy(&header.magic));
            println!("  Version: {}", header.version);
            println!("  Frames: {}", header.frame_count);
            println!("  Original resolution: {}x{}", header.original_width, header.original_height);
            println!("  FPS: {:.2}", header.fps);
            println!("  Audio size: {} bytes", header.audio_size);
            let metadata = std::fs::metadata(&file)?;
            println!("  Total file size: {} bytes", metadata.len());
            println!("  Frame data size: {} bytes", metadata.len() - 32 - header.audio_size);
        }
    }
    Ok(())
}