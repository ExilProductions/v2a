import argparse
import sys
import os


def main():

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from v2a_player.player import V2APlayer
    from v2a_player.reader import V2AReader

    parser = argparse.ArgumentParser(
        description="V2A Player - Terminal-based player for V2A video format",
        epilog="For more information, see README.md",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    info_parser = subparsers.add_parser(
        "info", help="Display information about V2A file"
    )
    info_parser.add_argument("file", help="V2A file to examine")

    play_parser = subparsers.add_parser("play", help="Play V2A video file")
    play_parser.add_argument("file", help="V2A file to play")

    args = parser.parse_args()

    if args.command == "info":
        info_command(args, V2AReader)
    elif args.command == "play":
        play_command(args, V2APlayer)
    else:
        parser.print_help()
        sys.exit(1)


def info_command(args, reader_class):
    try:
        with reader_class(args.file) as reader:
            print(f"File: {args.file}")
            print(f"  Magic: {reader.header.magic!r}")
            print(f"  Version: {reader.header.version}")
            print(f"  Frame count: {reader.header.frame_count}")
            print(
                f"  Original resolution: {reader.header.original_width}x{reader.header.original_height}"
            )
            print(f"  FPS: {reader.header.fps:.2f}")
            print(f"  Audio size: {reader.header.audio_size} bytes")

            first_frame = reader.read_frame()
            if first_frame:
                print(
                    f"  Frame dimensions: {first_frame.width}x{first_frame.height} characters"
                )
                print(f"  Pixel pairs: {len(first_frame.pixel_pairs)}")

            if reader.audio:
                print(f"  Audio: Available ({len(reader.audio)} bytes)")

                if len(reader.audio) >= 44:
                    try:
                        import struct

                        if reader.audio[0:4] == b"RIFF":
                            fmt = reader.audio[8:12]
                            if fmt == b"WAVE":
                                print(f"  Audio format: WAV")
                    except:
                        pass
            else:
                print(f"  Audio: Not present")

    except Exception as e:
        print(f"Error reading {args.file}: {e}", file=sys.stderr)
        sys.exit(1)


def play_command(args, player_class):
    if not os.path.exists(args.file):
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    try:
        player = player_class(args.file)
        player.load()

        print(f"Starting playback...")
        player.play()

    except KeyboardInterrupt:
        print("\nPlayback interrupted")
    except Exception as e:
        print(f"Error during playback: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
