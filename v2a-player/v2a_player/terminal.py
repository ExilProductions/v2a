import os
import shutil
import sys
import math
import struct
from typing import Tuple, Optional


def get_terminal_size() -> Tuple[int, int]:
    size = shutil.get_terminal_size()
    return (size.columns, size.lines)


def calculate_scaled_dimensions(
    src_width: int,
    src_height: int,
    max_width: Optional[int] = None,
    max_height: Optional[int] = None,
) -> Tuple[int, int]:
    if max_width is None or max_height is None:
        max_width, max_height = get_terminal_size()

    max_height = max_height - 2

    if src_width <= max_width and src_height <= max_height:
        return (src_width, src_height)

    width_scale = max_width / (2.0 * src_width)
    height_scale = max_height / src_height
    scale = min(width_scale, height_scale)

    scaled_width = int(2.0 * scale * src_width)
    scaled_height = int(scale * src_height)

    scaled_width = max(1, scaled_width)
    scaled_height = max(1, scaled_height)

    return (scaled_width, scaled_height)


def calculate_centering_offset(
    src_width: int,
    src_height: int,
    container_width: int,
    container_height: int,
) -> Tuple[int, int]:
    x = (container_width - src_width) // 2
    y = (container_height - src_height) // 2
    return (max(0, x), max(0, y))


def ansi_color_fg(r: int, g: int, b: int) -> str:
    return f"\x1b[38;2;{r};{g};{b}m"


def ansi_color_bg(r: int, g: int, b: int) -> str:
    return f"\x1b[48;2;{r};{g};{b}m"


def ansi_reset() -> str:
    return "\x1b[0m"


def ansi_clear_screen() -> str:
    return "\x1b[2J\x1b[H"


def ansi_move_cursor(row: int, col: int) -> str:
    return f"\x1b[{row};{col}H"


def ansi_hide_cursor() -> str:
    return "\x1b[?25l"


def ansi_show_cursor() -> str:
    return "\x1b[?25h"


def render_half_block(top_r: int, top_g: int, top_b: int, bottom_r: int, bottom_g: int, bottom_b: int) -> str:
    if top_r == bottom_r and top_g == bottom_g and top_b == bottom_b:
        return f"{ansi_color_fg(top_r, top_g, top_b)}█{ansi_reset()}"
    else:
        return f"{ansi_color_fg(top_r, top_g, top_b)}{ansi_color_bg(bottom_r, bottom_g, bottom_b)}▀{ansi_reset()}"


def build_frame_buffer(
    pixel_pairs, width: int, height: int, offset_x: int, offset_y: int
) -> bytearray:
    buffer = bytearray()
    for y in range(height):
        row = offset_y + 1 + y
        col = offset_x + 1
        buffer.extend(f"\x1b[{row};{col}H".encode())
        for x in range(width):
            idx = y * width + x
            pair = pixel_pairs[idx]
            top_r, top_g, top_b, bottom_r, bottom_g, bottom_b = pair
            if top_r == bottom_r and top_g == bottom_g and top_b == bottom_b:
                buffer.extend(f"\x1b[38;2;{top_r};{top_g};{top_b}m█\x1b[0m".encode())
            else:
                buffer.extend(f"\x1b[38;2;{top_r};{top_g};{top_b};48;2;{bottom_r};{bottom_g};{bottom_b}m▀\x1b[0m".encode())
    return buffer


class TerminalRenderer:
    def __init__(self):
        self.term_width, self.term_height = get_terminal_size()
        self.scaled_width = 0
        self.scaled_height = 0
        self.src_width = 0
        self.src_height = 0
        self.offset_x = 0
        self.offset_y = 0
        self.last_frame_buffer = None
        self.needs_full_redraw = True

    def update_layout(self, src_width: int, src_height: int):
        self.src_width = src_width
        self.src_height = src_height
        self.scaled_width, self.scaled_height = calculate_scaled_dimensions(
            src_width, src_height, self.term_width, self.term_height
        )
        self.offset_x, self.offset_y = calculate_centering_offset(
            self.scaled_width, self.scaled_height, self.term_width, self.term_height
        )
        self.needs_full_redraw = True

    def check_resize(self) -> bool:
        new_width, new_height = get_terminal_size()
        if new_width != self.term_width or new_height != self.term_height:
            self.term_width, self.term_height = new_width, new_height
            if self.src_width > 0 and self.src_height > 0:
                self.update_layout(self.src_width, self.src_height)
            return True
        return False

    def render_frame(
        self, frame_pixel_pairs, frame_width: int, frame_height: int
    ) -> bytes:
        if (self.scaled_width, self.scaled_height) != (frame_width, frame_height):
            return self._render_scaled_frame(
                frame_pixel_pairs, frame_width, frame_height
            )
        else:
            return self._render_exact_frame(
                frame_pixel_pairs, frame_width, frame_height
            )

    def _render_exact_frame(self, pixel_pairs, width: int, height: int) -> bytes:
        buffer = build_frame_buffer(
            pixel_pairs, width, height, self.offset_x, self.offset_y
        )
        return bytes(buffer)

    def _render_scaled_frame(
        self, pixel_pairs, src_width: int, src_height: int
    ) -> bytes:
        dst_width, dst_height = self.scaled_width, self.scaled_height
        buffer = bytearray()
        for dy in range(dst_height):
            row = self.offset_y + 1 + dy
            col = self.offset_x + 1
            buffer.extend(f"\x1b[{row};{col}H".encode())
            sy = int(dy * src_height / dst_height)
            for dx in range(dst_width):
                sx = int(dx * src_width / dst_width)
                idx = sy * src_width + sx
                pair = pixel_pairs[idx]
                top_r, top_g, top_b, bottom_r, bottom_g, bottom_b = pair
                if top_r == bottom_r and top_g == bottom_g and top_b == bottom_b:
                    buffer.extend(f"\x1b[38;2;{top_r};{top_g};{top_b}m█\x1b[0m".encode())
                else:
                    buffer.extend(f"\x1b[38;2;{top_r};{top_g};{top_b};48;2;{bottom_r};{bottom_g};{bottom_b}m▀\x1b[0m".encode())
        return bytes(buffer)

    def prepare_display(self) -> bytes:
        return (ansi_clear_screen() + ansi_hide_cursor()).encode()

    def restore_display(self) -> bytes:
        return (ansi_show_cursor() + ansi_clear_screen()).encode()

    def frame_prefix(self) -> bytes:
        return f"\x1b[{self.offset_y + 1};{self.offset_x + 1}H".encode()

    def clear_video_area(self) -> bytes:
        if self.scaled_width <= 0 or self.scaled_height <= 0:
            return b""
        buffer = bytearray()
        for row in range(self.offset_y + 1, self.offset_y + self.scaled_height + 1):
            buffer.extend(f"\x1b[{row};{self.offset_x + 1}H".encode())
            buffer.extend(b"\x1b[0m")
            buffer.extend(b" " * self.scaled_width)
        return bytes(buffer)
