use std::num::NonZeroUsize;
use std::sync::{Arc, Mutex};
use lru::LruCache;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Rgb {
    pub r: u8,
    pub g: u8,
    pub b: u8,
}

impl Rgb {
    pub fn new(r: u8, g: u8, b: u8) -> Self {
        Self { r, g, b }
    }

    fn distance_squared(&self, other: &Rgb) -> u32 {
        let dr = self.r as i32 - other.r as i32;
        let dg = self.g as i32 - other.g as i32;
        let db = self.b as i32 - other.b as i32;
        (dr * dr + dg * dg + db * db) as u32
    }
}

pub struct Ansi256Palette {
    colors: Vec<Rgb>,
    cache: Arc<Mutex<LruCache<Rgb, u8>>>,
}

impl Ansi256Palette {
    pub fn new() -> Self {
        let mut colors = Vec::with_capacity(256);
        let standard = [
            (0, 0, 0),
            (128, 0, 0),
            (0, 128, 0),
            (128, 128, 0),
            (0, 0, 128),
            (128, 0, 128),
            (0, 128, 128),
            (192, 192, 192),
            (128, 128, 128),
            (255, 0, 0),
            (0, 255, 0),
            (255, 255, 0),
            (0, 0, 255),
            (255, 0, 255),
            (0, 255, 255),
            (255, 255, 255),
        ];
        for &(r, g, b) in &standard {
            colors.push(Rgb::new(r, g, b));
        }
        let steps = [0, 95, 135, 175, 215, 255];
        for r in 0..6 {
            for g in 0..6 {
                for b in 0..6 {
                    colors.push(Rgb::new(steps[r], steps[g], steps[b]));
                }
            }
        }
        for i in 0..24 {
            let gray = 8 + i * 10;
            colors.push(Rgb::new(gray, gray, gray));
        }
        assert_eq!(colors.len(), 256);
        Self {
            colors,
            cache: Arc::new(Mutex::new(LruCache::new(NonZeroUsize::new(65536).unwrap()))),
        }
    }

    pub fn find_closest(&self, rgb: Rgb) -> u8 {
        {
            let mut cache = self.cache.lock().unwrap();
            if let Some(&index) = cache.get(&rgb) {
                return index;
            }
        }
        let mut best_index = 0;
        let mut best_dist = u32::MAX;
        for (i, palette_color) in self.colors.iter().enumerate() {
            let dist = rgb.distance_squared(palette_color);
            if dist < best_dist {
                best_dist = dist;
                best_index = i;
            }
        }
        let best_index = best_index as u8;
        let mut cache = self.cache.lock().unwrap();
        cache.put(rgb, best_index);
        best_index
    }

    pub fn get_color(&self, index: u8) -> Rgb {
        self.colors[index as usize]
    }
}

impl Default for Ansi256Palette {
    fn default() -> Self {
        Self::new()
    }
}
