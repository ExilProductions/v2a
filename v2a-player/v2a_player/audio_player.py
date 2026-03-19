import io
import struct
import threading
import time
from typing import Optional, Tuple

try:
    import pygame

    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False


class AudioPlayer:
    def __init__(self, wav_data: bytes):
        self.wav_data = wav_data
        self.player_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()
        self._volume = 1.0
        self._current_position = 0.0
        self._position_lock = threading.Lock()
        self._parse_wav_header()

    def _parse_wav_header(self):
        if len(self.wav_data) < 44:
            self.valid = False
            return

        if self.wav_data[0:4] != b"RIFF" or self.wav_data[8:12] != b"WAVE":
            self.valid = False
            return

        fmt_chunk_offset = 12

        while fmt_chunk_offset < len(self.wav_data) - 8:
            chunk_id = self.wav_data[fmt_chunk_offset : fmt_chunk_offset + 4]
            chunk_size = struct.unpack(
                "<I", self.wav_data[fmt_chunk_offset + 4 : fmt_chunk_offset + 8]
            )[0]
            if chunk_id == b"fmt ":
                break
            fmt_chunk_offset += 8 + chunk_size
        else:
            self.valid = False
            return

        fmt_data = self.wav_data[
            fmt_chunk_offset + 8 : fmt_chunk_offset + 8 + chunk_size
        ]
        if len(fmt_data) < 16:
            self.valid = False
            return
        self.audio_format = struct.unpack("<H", fmt_data[0:2])[0]
        self.num_channels = struct.unpack("<H", fmt_data[2:4])[0]
        self.sample_rate = struct.unpack("<I", fmt_data[4:8])[0]
        self.byte_rate = struct.unpack("<I", fmt_data[8:12])[0]
        self.block_align = struct.unpack("<H", fmt_data[12:14])[0]
        self.bits_per_sample = struct.unpack("<H", fmt_data[14:16])[0]

        data_chunk_offset = fmt_chunk_offset + 8 + chunk_size
        while data_chunk_offset < len(self.wav_data) - 8:
            chunk_id = self.wav_data[data_chunk_offset : data_chunk_offset + 4]
            chunk_size = struct.unpack(
                "<I", self.wav_data[data_chunk_offset + 4 : data_chunk_offset + 8]
            )[0]
            if chunk_id == b"data":
                self.audio_data = self.wav_data[
                    data_chunk_offset + 8 : data_chunk_offset + 8 + chunk_size
                ]
                self.audio_data_offset = data_chunk_offset + 8
                self.audio_data_size = chunk_size
                break
            data_chunk_offset += 8 + chunk_size
        else:
            self.valid = False
            return
        self.valid = True
        self.duration = len(self.audio_data) / self.byte_rate

    def is_valid(self) -> bool:
        return self.valid and PYGAME_AVAILABLE

    def start(self):
        if not self.is_valid() or self.player_thread is not None:
            return
        self.stop_event.clear()
        self.pause_event.set()
        self._current_position = 0.0
        self.player_thread = threading.Thread(target=self._playback_thread)
        self.player_thread.start()

    def stop(self):
        self.stop_event.set()
        if self.player_thread:
            self.player_thread.join(timeout=1.0)
            self.player_thread = None

    def pause(self):
        self.pause_event.clear()

    def resume(self):
        self.pause_event.set()

    def seek(self, position: float):
        with self._position_lock:
            self._current_position = max(0.0, min(position, self.duration))

    def set_volume(self, volume: float):
        self._volume = max(0.0, min(1.0, volume))

    def get_position(self) -> float:
        with self._position_lock:
            return self._current_position

    def _playback_thread(self):
        try:
            pygame.mixer.init(
                frequency=self.sample_rate,
                size=-self.bits_per_sample,
                channels=self.num_channels,
                buffer=4096,
            )

            start_byte = int(self._current_position * self.byte_rate)
            aligned_start = (start_byte // self.block_align) * self.block_align
            audio_subset = self.audio_data[aligned_start:]

            sound = pygame.mixer.Sound(buffer=bytes(audio_subset))
            channel = sound.play()
            channel.set_volume(self._volume)

            start_time = time.time() - (aligned_start / self.byte_rate)

            while not self.stop_event.is_set():
                self.pause_event.wait()
                if self.stop_event.is_set():
                    break

                with self._position_lock:
                    self._current_position = (time.time() - start_time) + (
                        aligned_start / self.byte_rate
                    )
                    if self._current_position > self.duration:
                        break

                if not channel.get_busy():
                    break
                time.sleep(0.01)

            if channel and channel.get_busy():
                channel.stop()
            pygame.mixer.quit()
        except Exception as e:
            print(f"Audio playback error: {e}")


class NullAudioPlayer:
    def __init__(self, wav_data: bytes):
        self.wav_data = wav_data

    def is_valid(self) -> bool:
        return False

    def start(self):
        pass

    def stop(self):
        pass

    def pause(self):
        pass

    def resume(self):
        pass

    def seek(self, position: float):
        pass

    def set_volume(self, volume: float):
        pass

    def get_position(self) -> float:
        return 0.0


def create_audio_player(wav_data: bytes):
    if PYGAME_AVAILABLE and len(wav_data) >= 44 and wav_data[0:4] == b"RIFF":
        player = AudioPlayer(wav_data)
        if player.is_valid():
            return player
    return NullAudioPlayer(wav_data)
