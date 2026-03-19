import sys
import time
import threading
import select
import tty
import termios
from typing import Optional
from .reader import V2AReader
from .terminal import TerminalRenderer
from .audio_player import create_audio_player


class V2APlayer:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.reader: Optional[V2AReader] = None
        self.renderer: Optional[TerminalRenderer] = None
        self.audio_player = None
        self.playing = False
        self.paused = False
        self.current_frame = 0
        self.frame_delay = 0.0
        self.control_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.pause_lock = threading.Lock()
        self.original_termios = None
        self.volume = 1.0

    def load(self):
        self.reader = V2AReader(self.filepath)

        first_frame = self.reader.read_frame()
        if first_frame is None:
            raise ValueError("No frames in V2A file")
        self.reader.reset()

        self.renderer = TerminalRenderer()
        self.renderer.update_layout(first_frame.width, first_frame.height)

        if self.reader.audio:
            self.audio_player = create_audio_player(self.reader.audio)
            if self.audio_player.is_valid():
                self.audio_player.set_volume(self.volume)

        self.frame_delay = (
            1.0 / self.reader.frame_rate if self.reader.frame_rate > 0 else 0.1
        )

        print(
            f"Loaded: {self.reader.header.frame_count} frames, "
            f"{self.reader.frame_rate:.1f} fps, "
            f"{first_frame.width}x{first_frame.height} chars"
        )
        if self.audio_player and self.audio_player.is_valid():
            print("Audio: Available")
        else:
            print("Audio: Not available (install pygame for audio)")
        self._print_controls()

    def _print_controls(self):
        print("\nControls:")
        print("  SPACE - Pause/Resume")
        print("  Q     - Quit")
        print("  F     - Toggle fullscreen/resize")
        print("  <-    - Seek backward 5s")
        print("  ->    - Seek forward 5s")
        print("  UP    - Volume up 10%")
        print("  DOWN  - Volume down 10%")
        print("  .     - Step forward one frame")
        print("  ,     - Step backward one frame")
        print()

    def _setup_terminal(self):
        if not sys.stdin.isatty():
            return
        self.original_termios = termios.tcgetattr(sys.stdin)
        tty.setraw(sys.stdin.fileno())

    def _restore_terminal(self):
        if self.original_termios:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.original_termios)
            self.original_termios = None

    def _handle_input(self):
        while not self.stop_event.is_set():
            try:
                ready, _, _ = select.select([sys.stdin], [], [], 0.05)
                if ready:
                    ch = sys.stdin.read(1)
                    self._process_key(ch)
            except:
                break

    def _process_key(self, key: str):
        if key == " ":
            self.toggle_pause()
        elif key == "q" or key == "\x03":
            self.stop()
        elif key == "f":
            if self.reader:
                first_frame = None
                pos = self.reader.file.tell()
                self.reader.reset()
                first_frame = self.reader.read_frame()
                self.reader.reset()
                if first_frame:
                    self.renderer.update_layout(first_frame.width, first_frame.height)
                    self.renderer.needs_full_redraw = True
                    print(
                        f"\r\033[KResized to: {self.renderer.scaled_width}x{self.renderer.scaled_height}",
                        end="",
                        flush=True,
                    )
        elif key == "\x1b":
            try:
                next1 = sys.stdin.read(1)
                next2 = sys.stdin.read(1)
                if next1 == "[":
                    if next2 == "D":
                        self.seek_relative(-5.0)
                    elif next2 == "C":
                        self.seek_relative(5.0)
                    elif next2 == "A":
                        self.set_volume(self.volume + 0.1)
                    elif next2 == "B":
                        self.set_volume(self.volume - 0.1)
            except:
                pass
        elif key == ",":
            self.step_frame(-1)
        elif key == ".":
            self.step_frame(1)

    def toggle_pause(self):
        with self.pause_lock:
            self.paused = not self.paused
            if self.paused:
                if self.audio_player:
                    self.audio_player.pause()
                print("\r\033[KPAUSED", end="", flush=True)
            else:
                if self.audio_player:
                    self.audio_player.resume()
                print("\r\033[KPLAYING", end="", flush=True)

    def seek_relative(self, seconds: float):
        if not self.reader:
            return
        fps = self.reader.frame_rate
        if fps <= 0:
            return
        frame_offset = int(seconds * fps)
        new_frame = max(
            0,
            min(self.current_frame + frame_offset, self.reader.header.frame_count - 1),
        )

        if self.audio_player and self.audio_player.is_valid():
            audio_pos = new_frame / fps
            self.audio_player.seek(audio_pos)

        self.reader.seek_to_frame(new_frame)
        self.current_frame = new_frame
        self.renderer.needs_full_redraw = True
        print(
            f"\r\033[KSeeked to frame {self.current_frame}/{self.reader.header.frame_count}",
            end="",
            flush=True,
        )

    def set_volume(self, vol: float):
        self.volume = max(0.0, min(1.0, vol))
        if self.audio_player and self.audio_player.is_valid():
            self.audio_player.set_volume(self.volume)
        print(f"\r\033[KVolume: {int(self.volume * 100)}%", end="", flush=True)

    def step_frame(self, direction: int):
        with self.pause_lock:
            new_frame = self.current_frame + direction
            if 0 <= new_frame < self.reader.header.frame_count:
                self.reader.seek_to_frame(new_frame)
                self.current_frame = new_frame
                frame = self.reader.read_frame()
                if frame:
                    output = self.renderer.render_frame(
                        frame.pixel_pairs, frame.width, frame.height
                    )
                    sys.stdout.buffer.write(self.renderer.clear_video_area())
                    sys.stdout.buffer.write(output)
                    sys.stdout.buffer.flush()
                print(
                    f"\r\033[KFrame {self.current_frame}/{self.reader.header.frame_count}",
                    end="",
                    flush=True,
                )

    def _playback_loop(self):
        frame_count = self.reader.header.frame_count
        start_time = time.time()
        pause_offset = 0.0
        last_pause_time = None

        while not self.stop_event.is_set() and self.current_frame < frame_count:
            with self.pause_lock:
                if self.paused:
                    if last_pause_time is None:
                        last_pause_time = time.time()
                    time.sleep(0.01)
                    continue
                else:
                    if last_pause_time is not None:
                        pause_offset += time.time() - last_pause_time
                        last_pause_time = None

            if self.stop_event.is_set():
                break

            elapsed = time.time() - start_time - pause_offset
            expected_frame = int(elapsed / self.frame_delay)

            if self.current_frame > expected_frame:
                time.sleep(0.001)
                continue

            while (
                self.current_frame < expected_frame
                and self.current_frame < frame_count - 1
            ):
                frame = self.reader.read_frame()
                if frame is None:
                    break
                self.current_frame += 1

            if self.renderer.check_resize():
                sys.stdout.buffer.write(self.renderer.prepare_display())
                sys.stdout.buffer.flush()

            frame = self.reader.read_frame()
            if frame is None:
                break

            output = self.renderer.render_frame(
                frame.pixel_pairs, frame.width, frame.height
            )
            sys.stdout.buffer.write(self.renderer.clear_video_area())
            sys.stdout.buffer.write(output)
            sys.stdout.buffer.flush()

            self.current_frame += 1

            target_time = (
                start_time + pause_offset + (self.current_frame * self.frame_delay)
            )
            sleep_time = target_time - time.time()
            if sleep_time > 0:
                time.sleep(sleep_time)

    def play(self):
        if self.playing:
            return

        self.playing = True
        self.stop_event.clear()

        try:
            self._setup_terminal()

            if self.audio_player and self.audio_player.is_valid():
                self.audio_player.start()

            sys.stdout.buffer.write(self.renderer.prepare_display())
            sys.stdout.buffer.flush()

            if sys.stdin.isatty():
                self.control_thread = threading.Thread(target=self._handle_input)
                self.control_thread.start()
            else:
                self.control_thread = None

            self._playback_loop()

        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        if not self.playing:
            return

        self.stop_event.set()

        with self.pause_lock:
            if self.audio_player:
                self.audio_player.stop()

        if self.control_thread:
            self.control_thread.join(timeout=0.5)

        self._restore_terminal()

        if self.renderer:
            sys.stdout.buffer.write(self.renderer.restore_display())
            sys.stdout.buffer.flush()

        self.playing = False
        print(
            f"\nPlayback stopped at frame {self.current_frame}/{self.reader.header.frame_count if self.reader else '?'}"
        )

    def close(self):
        self.stop()
        if self.reader:
            self.reader.close()
