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
        self.paused_event = threading.Event()
        self.paused_event.set()  
        self.original_termios = None
        
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
        
        self.frame_delay = 1.0 / self.reader.frame_rate if self.reader.frame_rate > 0 else 0.1
        
        print(f"Loaded: {self.reader.header.frame_count} frames, "
              f"{self.reader.frame_rate:.1f} fps, "
              f"{first_frame.width}x{first_frame.height} chars")
        if self.audio_player and self.audio_player.is_valid():
            print("Audio: Available")
        else:
            print("Audio: Not available (install pygame for audio)")
    
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
            
            ready, _, _ = select.select([sys.stdin], [], [], 0.1)
            if ready:
                ch = sys.stdin.read(1)
                self._process_key(ch)
    
    def _process_key(self, key: str):
        if key == ' ':
            self.toggle_pause()
        elif key == 'q' or key == '\x03':  
            self.stop()
        elif key == 'f':
            
            if self.reader:
                first_frame = None
                pos = self.reader.file.tell()
                self.reader.reset()
                first_frame = self.reader.read_frame()
                self.reader.reset()
                if first_frame:
                    self.renderer.update_layout(first_frame.width, first_frame.height)
                    print(f"\rResized to: {self.renderer.scaled_width}x{self.renderer.scaled_height}")
    
    def toggle_pause(self):
        self.paused = not self.paused
        if self.paused:
            self.paused_event.clear()
            if self.audio_player:
                self.audio_player.pause()
            print("\rPaused", end='')
        else:
            self.paused_event.set()
            if self.audio_player:
                self.audio_player.resume()
            print("\rPlaying", end='')
        sys.stdout.flush()
    
    def _playback_loop(self):
        frame_count = self.reader.header.frame_count
        start_time = time.time()
        expected_frame = 0
        
        while (not self.stop_event.is_set() and 
               self.current_frame < frame_count):
            
            self.paused_event.wait()
            if self.stop_event.is_set():
                break
            
            elapsed = time.time() - start_time
            expected_frame = int(elapsed / self.frame_delay)
            
            if self.current_frame > expected_frame:
                time.sleep(0.001)
                continue
            
            while self.current_frame < expected_frame and self.current_frame < frame_count - 1:
                
                frame = self.reader.read_frame()
                if frame is None:
                    break
                self.current_frame += 1
            
            if self.renderer.check_resize():
                sys.stdout.write(self.renderer.prepare_display())
                sys.stdout.flush()
            
            
            frame = self.reader.read_frame()
            if frame is None:
                break
            
            output = self.renderer.render_frame(frame.pixel_pairs, frame.width, frame.height)
            sys.stdout.write(self.renderer.clear_video_area() + self.renderer.frame_prefix() + output)
            sys.stdout.flush()
            
            self.current_frame += 1
            
            target_time = start_time + (self.current_frame * self.frame_delay)
            sleep_time = target_time - time.time()
            if sleep_time > 0:
                time.sleep(sleep_time)
    
    def play(self):
        if self.playing:
            return
        
        self.playing = True
        self.stop_event.clear()
        self.paused_event.set()
        
        try:
            
            self._setup_terminal()
            
            if self.audio_player and self.audio_player.is_valid():
                self.audio_player.start()
            
            sys.stdout.write(self.renderer.prepare_display())
            sys.stdout.flush()
            
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
        self.paused_event.set()  
        
        if self.audio_player:
            self.audio_player.stop()
        
        if self.control_thread:
            self.control_thread.join(timeout=0.5)
        
        self._restore_terminal()
        
        if self.renderer:
            sys.stdout.write(self.renderer.restore_display())
            sys.stdout.flush()
        
        self.playing = False
        print(f"\nPlayback stopped at frame {self.current_frame}/{self.reader.header.frame_count}")
    
    def close(self):
        self.stop()
        if self.reader:
            self.reader.close()
