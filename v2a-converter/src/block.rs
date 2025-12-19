use crate::color::{Ansi256Palette, Rgb};
use crate::V2AFrame;

pub struct BlockProcessor {
    palette: Ansi256Palette,
}

impl BlockProcessor {
    pub fn new() -> Self {
        Self {
            palette: Ansi256Palette::new(),
        }
    }

    pub fn process_frame(
        &self,
        rgb_data: &[u8],
        original_width: u32,
        original_height: u32,
    ) -> V2AFrame {
        let block_width = (original_width / 2) as u16;
        let block_height = (original_height / 2) as u16;
        let mut frame = V2AFrame::new(block_width, block_height);
        let stride = (original_width * 3) as usize;
        for y in 0..block_height {
            let base_y = (y as u32) * 2;
            for x in 0..block_width {
                let base_x = (x as u32) * 2;
                let mut top_r = 0u32;
                let mut top_g = 0u32;
                let mut top_b = 0u32;
                let mut bottom_r = 0u32;
                let mut bottom_g = 0u32;
                let mut bottom_b = 0u32;
                for dy in 0..2 {
                    let row = base_y + dy;
                    let row_start = row as usize * stride;
                    for dx in 0..2 {
                        let col = base_x + dx;
                        let pixel_start = row_start + (col as usize) * 3;
                        let r = rgb_data[pixel_start] as u32;
                        let g = rgb_data[pixel_start + 1] as u32;
                        let b = rgb_data[pixel_start + 2] as u32;
                        if dy == 0 {
                            top_r += r;
                            top_g += g;
                            top_b += b;
                        } else {
                            bottom_r += r;
                            bottom_g += g;
                            bottom_b += b;
                        }
                    }
                }
                let top_avg = Rgb::new(
                    (top_r / 2) as u8,
                    (top_g / 2) as u8,
                    (top_b / 2) as u8,
                );
                let bottom_avg = Rgb::new(
                    (bottom_r / 2) as u8,
                    (bottom_g / 2) as u8,
                    (bottom_b / 2) as u8,
                );
                let top_idx = self.palette.find_closest(top_avg);
                let bottom_idx = self.palette.find_closest(bottom_avg);
                frame.pixel_pairs[(y as usize) * (block_width as usize) + (x as usize)] =
                    [top_idx, bottom_idx];
            }
        }
        frame
    }
}

impl Default for BlockProcessor {
    fn default() -> Self {
        Self::new()
    }
}